"""Flyout fade machinery — the snapshot-composited opacity pipeline.

Fade is implemented without a QGraphicsEffect: a one-shot snapshot of the
flyout is captured outside paintEvent and the flyout's paint composites it
with the current opacity (see ``BaseFlyout.paintEvent`` in ``style.py``).
The hide fade is the same pipeline reversed, driven by a
``QVariantAnimation``.

``FlyoutFadeController`` owns ALL of the fade state (cache, opacity,
hide-fade animation, flags) and takes the flyout widget as an explicit
argument where it must touch it (grab/update/hide children) — the widget
itself stores nothing about the fade beyond the controller reference.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.config import get_flyout_timings

logger = logging.getLogger(__name__)


def resolve_flyout_animation(animation: str | None) -> str:
    """Resolve an animation mode the way :meth:`BaseFlyout.show_aligned` does.

    An explicit value wins; otherwise the process-wide
    ``FlyoutTimingConfig.default_flyout_animation`` applies; empty/None falls
    back to ``"none"``. Composite flyouts with their own show paths
    (``SimpleOptionsFlyout.show_below``, …) share this so they respect the
    same global + per-instance configuration as the base class.
    """
    mode = animation if animation is not None else (
        get_flyout_timings().default_flyout_animation or "none"
    )
    return mode if mode else "none"


class FlyoutFadeController:
    """Owns the fade snapshot/opacity state and the hide-fade animation.

    No widget state of its own: the flyout is passed explicitly where the
    controller must touch it (grab the snapshot, hide direct children,
    repaint). The show animation belongs to the placement side and is only
    read here (stopped when a hide fade starts).
    """

    #: Current fade opacity (1.0 = fully opaque).
    opacity: float = 1.0
    cache: QPixmap | None = None
    render_guard: bool = False
    hide_fade_in_progress: bool = False
    hide_animation: QVariantAnimation | None = None
    #: Set by show_aligned when the flyout was shown with a fade-bearing
    #: animation mode; hide() then fades out instead of vanishing. Reset on
    #: "none"/"slide" shows (and preserved across reposition()).
    fade_out_enabled: bool = False

    def capture(self, flyout: QWidget) -> None:
        """Snapshot the fully-opaque flyout for the current fade.

        Called outside paintEvent (on show/hide), so ``grab()`` cannot recurse
        into the fade paint path. ``render_guard`` protects the rare
        re-entrant call (e.g. hide() triggered from a paint handler).
        """
        if self.cache is not None or self.render_guard:
            return
        if flyout.width() <= 0 or flyout.height() <= 0:
            return
        # The snapshot must include the content: a previous fade-out (or a
        # first-show sync) may have hidden the children, and grab() of a
        # hidden child would capture an empty panel.
        for child in flyout.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            child.setHidden(False)
        self.render_guard = True
        try:
            self.cache = flyout.grab()
        finally:
            self.render_guard = False

    def clear(self) -> None:
        self.cache = None

    def set_opacity(self, flyout: QWidget, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value == self.opacity:
            return
        self.opacity = value
        self.sync_container_visibility(flyout)
        flyout.update()

    def sync_container_visibility(self, flyout: QWidget) -> None:
        """While fading, show only the pre-rendered snapshot.

        The flyout's paintEvent composites the grab() snapshot at the current
        opacity, but Qt still paints the live child widgets on top of it at
        *full* opacity — the panel/shadow faded while the content popped in
        binarily. Hiding every direct child (the container with all its
        content, plus any siblings like a glass-panel display widget) during
        the fade leaves only the snapshot visible (the snapshot includes the
        children); they are restored at 1.0 (where paintEvent no longer uses
        the snapshot, so live children take over seamlessly).
        """
        hidden = self.opacity < 1.0
        # isHidden() (each widget's own mark), not isVisible(): during the
        # first show the flyout itself is still hidden, so isVisible() is
        # False regardless and the sync would be skipped — then Qt would
        # reveal the children at full opacity the moment the flyout shows.
        for child in flyout.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            if child.isHidden() != hidden:
                child.setHidden(hidden)

    def on_fade_value_changed(self, flyout: QWidget, value: Any) -> None:
        self.set_opacity(flyout, float(value))

    def make_fade_animation(
        self,
        flyout: QWidget,
        duration: int,
        start: float,
        end: float,
        easing: QEasingCurve.Type,
    ) -> QVariantAnimation:
        fade_anim = QVariantAnimation(flyout)
        fade_anim.setDuration(int(duration))
        fade_anim.setStartValue(start)
        fade_anim.setEndValue(end)
        fade_anim.setEasingCurve(easing)
        fade_anim.valueChanged.connect(
            lambda value: self.on_fade_value_changed(flyout, value)
        )
        return fade_anim

    # -- hide fade ---------------------------------------------------------

    def should_fade_out(self, flyout: QWidget) -> bool:
        if not flyout.isVisible():
            return False
        result = bool(self.fade_out_enabled)
        logger.debug(
            "[flyout-fade] should_fade_out %s id=%s → %s",
            type(flyout).__name__, id(flyout), result,
        )
        return result

    def start_hide_fade(
        self,
        flyout: QWidget,
        *,
        on_finished: Callable[[], None],
        show_animation,
    ) -> None:
        """Fade the flyout out; ``on_finished`` runs after the real hide."""
        logger.debug(
            "[flyout-fade] start_hide_fade %s id=%s hide_animation=%s",
            type(flyout).__name__, id(flyout),
            "active" if self.hide_animation is not None else "none",
        )
        if show_animation is not None:
            try:
                show_animation.stop()
                show_animation.deleteLater()
            except RuntimeError:
                pass
            flyout._show_animation = None  # type: ignore[attr-defined]  # placement-owned attr
        # A mid-fade-in hide should continue from the current opacity rather
        # than popping back to fully opaque.
        current = self.opacity
        # Snapshot the current fully-opaque state for the fade-out composite.
        self.capture(flyout)
        # The flyout is going away; let clicks fall through while it fades.
        flyout.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self.hide_fade_in_progress = True

        timings = get_flyout_timings()
        anim = QVariantAnimation(flyout)
        anim.setDuration(timings.flyout_fade_out_duration_ms)
        anim.setStartValue(current)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InQuad)
        anim.valueChanged.connect(
            lambda value: self.on_fade_value_changed(flyout, value)
        )
        anim.finished.connect(on_finished)
        self.hide_animation = anim
        anim.start()

    def cancel(self, flyout: QWidget) -> None:
        logger.debug(
            "[flyout-fade] cancel %s id=%s hide_animation=%s",
            type(flyout).__name__, id(flyout),
            "active" if self.hide_animation is not None else "none",
        )
        if self.hide_animation is not None:
            self.hide_animation.stop()
            self.hide_animation.deleteLater()
            self.hide_animation = None
        self.hide_fade_in_progress = False
        self.clear()
        self.set_opacity(flyout, 1.0)
        # set_opacity early-returns when the opacity is already 1.0, which
        # would skip the visibility sync — a container left hidden by an
        # interrupted fade-out would then collapse the next show's
        # adjustSize() to shadow margins only (empty flyout). Restore
        # unconditionally: the fade pipeline hid these children, and a show
        # is starting.
        self.sync_container_visibility(flyout)

    def on_hide_fade_finished(self, flyout: QWidget, on_finished: Callable[[], None]) -> None:
        logger.debug(
            "[flyout-fade] on_hide_fade_finished %s id=%s",
            type(flyout).__name__, id(flyout),
        )
        if self.hide_animation is not None:
            self.hide_animation.deleteLater()
            self.hide_animation = None
        self.hide_fade_in_progress = False
        # Hide the flyout FIRST — before clearing snapshot / restoring
        # children.  A repaint between clear() and hide() would show
        # the flyout at full opacity for 1 frame.
        QWidget.hide(flyout)
        # Reset for the next show; paintEvent is bypassed once hidden.
        self.clear()
        self.opacity = 1.0
        # The fade-out hid every direct child (sync_container_visibility).
        # Restore them now, not on the next show: a subsequent show_aligned
        # calls cancel() → set_opacity(1.0), which early-returns on an
        # already-1.0 opacity and would leave the container hidden; the
        # hidden container then contributes no sizeHint to adjustSize() and
        # the flyout collapses to just its shadow margin (16x16) — an empty
        # flyout. Restoring here is invisible (the flyout is about to be
        # hidden), and the next show's adjustSize() sees the real content.
        self.sync_container_visibility(flyout)
        on_finished()


__all__ = ["FlyoutFadeController", "resolve_flyout_animation"]
