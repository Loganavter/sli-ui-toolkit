"""BaseFlyout placement — show_aligned, reposition, overlay parenting.

The geometry of named-point alignment lives in ``geometry.py`` (pure
functions); this mixin drives it against the live widget: resolves the
animation mode, computes the final rect from the anchor, runs the
show animation, and re-runs placement for pinned flyouts.
"""

from __future__ import annotations

import math
from typing import Any, Callable, cast

import shiboken6

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QVariantAnimation,
)
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.config import get_flyout_timings
from sli_ui_toolkit.ui.in_window_surface import (
    attach_in_window_widget,
    place_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)

from .animation import resolve_flyout_animation
from .geometry import AnimationAxis, aligned_flyout_rect, slide_start_delta


class _FlyoutPlacementApi:
    """Mixin: show_aligned / reposition / overlay attachment.

    Not a QWidget itself — mixed into BaseFlyout; relies on instance state
    assigned in ``BaseFlyout.__init__`` (``overlay_layer``,
    ``_anchor_widget``, ``_last_align_kwargs``, ``_fade_out_enabled``,
    ``flyout_manager``) and on QWidget methods (adjustSize, setGeometry,
    show, raise_, isVisible).
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real assignments live in BaseFlyout.__init__ (widget.py), the
    # sibling mixins, or QWidget itself. Plain annotations only (no
    # `= value`) so nothing is created at import time. QWidget-provided
    # names are ``Any`` (a precise Callable would clash with QWidget's own
    # definition when the mixin precedes it in the MRO).
    overlay_layer: Any
    _anchor_widget: QWidget | None
    _last_align_kwargs: dict | None
    flyout_manager: Any
    container: Any
    _fade: Any
    _show_animation: Any
    SHADOW_RADIUS: int
    show: Any
    raise_: Any
    isVisible: Any
    parentWidget: Any
    setAttribute: Any
    adjustSize: Any
    setGeometry: Any
    size: Any

    def _ensure_overlay_parent(self, anchor_widget: QWidget):
        if anchor_widget is None:
            return
        if self.overlay_layer is None:
            self.overlay_layer = attach_in_window_widget(self, anchor_widget)  # type: ignore[arg-type]
        overlay = self.overlay_layer
        if overlay is not None and self.parentWidget() is not getattr(overlay, "host", None):
            was_visible = self.isVisible()
            overlay.attach(self)  # type: ignore[attr-defined]
            if was_visible:
                self.show()
                self.raise_()

    def show_aligned(
        self,
        anchor_widget: QWidget,
        anchor_point: str = "bottom-center",
        flyout_point: str = "top-center",
        *,
        position: str | None = None,
        offset: int = 5,
        animation: str | None = None,
        animation_duration_ms: int | None = None,
        animation_distance: int | None = None,
        animation_axis: AnimationAxis = "auto",
        easing: QEasingCurve.Type = QEasingCurve.Type.OutQuad,
        focus_reason: Qt.FocusReason | None = None,
    ):
        """Align a point on the flyout to a point on ``anchor_widget``.

        ``anchor_point`` and ``flyout_point`` are strings like ``"bottom-center"``,
        ``"top-left"``, ``"center-right"``. The vertical part (``top``/``center``/
        ``bottom``) and horizontal part (``left``/``center``/``right``) can appear
        in any order; a single token is treated as the other axis being ``center``.

        Defaults (``anchor="bottom-center"``, ``flyout="top-center"``) place the
        flyout directly under the anchor.

        For compatibility, callers may still pass the old ``position=`` values
        (``"top"``, ``"bottom"``, ``"left"``, ``"right"``, and corners).

        ``offset`` is the visible pixel gap between the anchor and the rendered
        flyout edge along the natural direction between the two points.

        ``animation`` defaults to ``None``, which resolves to the process-wide
        ``FlyoutTimingConfig.default_flyout_animation`` (itself ``"none"``
        unless a host sets it via ``configure_toolkit``) — so a host can
        animate every default flyout from one config value.

        Supported ``animation`` modes:
            * ``"none"`` — appears in place.
            * ``"slide"`` — slides in from the direction opposite to its offset.
            * ``"fade"`` — fades in (opacity 0 → 1) at the final position.
            * ``"slide-fade"`` — slides and fades in simultaneously.

        When the flyout is shown with ``"fade"`` or ``"slide-fade"``, the
        matching :meth:`hide` also fades out (see there) instead of vanishing
        instantly.

        ``animation_axis``:
            * ``"auto"`` — slide along the anchor→flyout vector (default).
            * ``"vertical"`` — slide only on Y (dropdown under a toolbar button).
            * ``"horizontal"`` — slide only on X.
            * ``"diagonal"`` — slide on both X and Y, each the full
              ``distance``/``animation_distance`` independently (not split
              across a single vector like ``"auto"``) — for a corner-aligned
              flyout where you want a clearly visible slide on both axes
              regardless of how the anchor/flyout sizes compare.
        """
        # A pending fade-out must not survive a re-show (e.g. a rapid
        # click-to-toggle reopen mid-animation).
        self._fade.cancel(self)
        self._last_align_kwargs = dict(
            anchor_widget=anchor_widget,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            position=position,
            offset=offset,
        )
        self._anchor_widget = anchor_widget
        # Determine keyboard-focus state of the trigger.
        # Prefer explicit focus_reason parameter, then the anchor widget's
        # persisted _last_focus_reason (survives CSD title bar clearing
        # _keyboard_focus), then _keyboard_focus itself.
        #
        # NavigationManager.last_keyboard_focus() is NOT a substitute here:
        # it's a single global slot that gets overwritten by ANY widget's
        # FocusIn, including the transient MainWindow focus that CSD title
        # bar handling produces between the trigger's click/Enter and this
        # call. The per-widget persisted attribute survives that because it
        # is scoped to the trigger widget itself.
        if focus_reason is not None:
            self._anchor_keyboard_focus = focus_reason not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
            )
        else:
            raw_reason = getattr(anchor_widget, "_last_focus_reason", None)
            if raw_reason is not None:
                self._anchor_keyboard_focus = raw_reason not in (
                    Qt.FocusReason.MouseFocusReason,
                    Qt.FocusReason.MenuBarFocusReason,
                )
            else:
                self._anchor_keyboard_focus = getattr(anchor_widget, "_keyboard_focus", False)
        self._ensure_overlay_parent(anchor_widget)

        self.flyout_manager.request_show(self)

        container_layout = self.container.layout()
        if container_layout is not None:
            container_layout.invalidate()
            container_layout.activate()
            self.container.updateGeometry()
        self.adjustSize()
        flyout_size = self.size()

        anchor_rect = surface_anchor_rect(
            self,  # type: ignore[arg-type]
            anchor_widget,
            self.overlay_layer,
        )
        if position is not None:
            final_rect = self._overlay_rect_relative_to_anchor(
                anchor_widget,
                flyout_size,
                position=position,
                offset=offset - self.SHADOW_RADIUS,
            )
            flyout_center = final_rect.center()
        else:
            final_rect = aligned_flyout_rect(
                anchor_rect,
                flyout_size,
                anchor_point=anchor_point,
                flyout_point=flyout_point,
                offset=offset,
                shadow_radius=self.SHADOW_RADIUS,
                available=surface_available_rect(
                    self,  # type: ignore[arg-type]
                    anchor_widget,
                    self.overlay_layer,
                    margin=0,
                ),
            )
            flyout_center = final_rect.center()

        dir_x = flyout_center.x() - anchor_rect.center().x()
        dir_y = flyout_center.y() - anchor_rect.center().y()
        length = math.hypot(dir_x, dir_y)
        if length > 0:
            ux, uy = dir_x / length, dir_y / length
        else:
            ux = uy = 0.0

        resolved_mode = resolve_flyout_animation(animation)
        # The close animation reflects the resolved mode (a reposition below
        # must not reset it).
        self._fade.fade_out_enabled = "fade" in resolved_mode
        # Repositioning an already-visible default-animated flyout (hover
        # flyouts that re-center on store changes) must not restart the show
        # animation — it would teleport the flyout to the slide start and
        # blink it to opacity 0. Stay put (instant) while keeping the close
        # animation. Explicit per-call animations still re-run.
        mode = "none" if (animation is None and self.isVisible()) else resolved_mode

        if mode == "none":
            self._fade.clear()
            self._fade.set_opacity(self, 1.0)
            self.setGeometry(final_rect)
            self.show()
            self.raise_()
            return

        timings = get_flyout_timings()
        duration = (
            animation_duration_ms
            if animation_duration_ms is not None
            else timings.flyout_animation_duration_ms
        )
        distance = (
            animation_distance
            if animation_distance is not None
            else timings.dropdown_drop_offset_px
        )
        if self._show_animation is not None:
            self._show_animation.stop()
            self._show_animation.deleteLater()
            self._show_animation = None

        want_slide = "slide" in mode
        want_fade = "fade" in mode

        if want_slide:
            slide_dx, slide_dy = slide_start_delta(
                final_rect,
                anchor_rect,
                distance=distance,
                animation_axis=animation_axis,
                shadow_radius=self.SHADOW_RADIUS,
                ux=ux,
                uy=uy,
                length=length,
            )
            start_pos = QPoint(
                final_rect.x() + slide_dx,
                final_rect.y() + slide_dy,
            )
        else:
            start_pos = QPoint(final_rect.x(), final_rect.y())

        self.setGeometry(QRect(start_pos, final_rect.size()))
        # Блокируем mouse-events до конца анимации — иначе flyout, проезжающий
        # под уже неподвижным курсором, подсвечивает «случайную» строку.
        # WA_TransparentForMouseEvents отключает доставку и виджету, и его
        # детям (см. Qt docs). Снимаем на animation finished + reconcile,
        # чтобы реальный hover применился по фактическому положению курсора.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        if want_fade:
            # self.show() below grants keyboard focus to the first row
            # (_grab_focus, via the overridden show()) — capture the
            # snapshot AFTER that so a keyboard-opened flyout's focus ring
            # is baked into the cache the fade-in composites. Capturing
            # before show() (as before) snapshots the flyout with no focus
            # yet granted, so the ring is invisible for the whole fade-in
            # and only starts showing once the fade finishes and cache is
            # cleared — visible as "ring missing on open, present on close".
            # No event-loop turn happens between show() and capture(), so
            # nothing paints to screen at full opacity in between.
            self.show()
            self._fade.capture(self)
            self._fade.set_opacity(self, 0.0)
        else:
            self.show()
        self.raise_()

        anim: QParallelAnimationGroup | QPropertyAnimation | QVariantAnimation
        if want_slide and want_fade:
            group = QParallelAnimationGroup(cast(QObject, self))
            pos_anim = QPropertyAnimation(cast(QObject, self), b"pos", cast(QObject, self))
            pos_anim.setDuration(int(duration))
            pos_anim.setStartValue(start_pos)
            pos_anim.setEndValue(QPoint(final_rect.x(), final_rect.y()))
            pos_anim.setEasingCurve(easing)
            fade_anim = self._fade.make_fade_animation(self, duration, 0.0, 1.0, easing)
            group.addAnimation(pos_anim)
            group.addAnimation(fade_anim)
            anim = group
        elif want_slide:
            anim = QPropertyAnimation(cast(QObject, self), b"pos", cast(QObject, self))
            anim.setDuration(int(duration))
            anim.setStartValue(start_pos)
            anim.setEndValue(QPoint(final_rect.x(), final_rect.y()))
            anim.setEasingCurve(easing)
        else:
            anim = self._fade.make_fade_animation(self, duration, 0.0, 1.0, easing)
        anim.finished.connect(self._on_show_animation_finished)
        self._show_animation = anim
        anim.start()

    def reposition(self) -> None:
        """Re-run the last :meth:`show_aligned` call, without animation.

        For ``pinned=True`` flyouts: the manager exempts them from
        auto-hide-on-anchor-move (unlike regular flyouts, which just close),
        so the host must call this from its own resize/move handlers to keep
        the HUD tracking its anchor. No-op if never shown, no longer visible,
        or the anchor widget was deleted.
        """
        kwargs = getattr(self, "_last_align_kwargs", None)
        if not kwargs or not self.isVisible():
            return
        anchor_widget = kwargs.get("anchor_widget")
        if anchor_widget is None:
            return
        try:
            if not anchor_widget.isVisible():
                return
        except RuntimeError:
            return
        # reposition() forces animation="none" (a no-animation replay), but
        # that must not reset the flyout's close animation — a fade-shown HUD
        # should still fade out on hide after being repositioned.
        fade_out = self._fade.fade_out_enabled
        self.show_aligned(
            anchor_widget,
            kwargs.get("anchor_point", "bottom-center"),
            kwargs.get("flyout_point", "top-center"),
            position=kwargs.get("position"),
            offset=kwargs.get("offset", 5),
            animation="none",
        )
        self._fade.fade_out_enabled = fade_out

    def _on_show_animation_finished(self) -> None:
        if self._show_animation is not None:
            self._show_animation.deleteLater()
            self._show_animation = None
        self._fade.clear()
        self._fade.set_opacity(self, 1.0)
        # set_opacity(1.0) just unhid the container that sync_container_
        # visibility hid for the fade — if that hide forced Qt to steal
        # focus off the row _grab_focus originally granted it to (hiding a
        # focused widget's ancestor always clears its focus), reclaim it now
        # that the row is visible again. Without this the focus ring shows
        # correctly during the fade (baked into the snapshot) and then
        # vanishes the instant the fade finishes and live children resume.
        target = getattr(self, "_grab_focus_target", None)
        if target is not None and shiboken6.isValid(target) and not target.hasFocus():
            reason = getattr(self, "_grab_focus_reason", Qt.FocusReason.OtherFocusReason)
            target.setFocus(reason)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        try:
            from sli_ui_toolkit.ui.widgets.helpers import hover_coordinator
            hover_coordinator().reconcile()
        except Exception:
            pass

    def _overlay_rect_relative_to_anchor(
        self,
        anchor_widget: QWidget,
        size: QSize,
        *,
        position: str,
        offset: int,
    ) -> QRect:
        if self.overlay_layer is not None and hasattr(
            self.overlay_layer, "place_rect_relative_to_anchor"
        ):
            return self.overlay_layer.place_rect_relative_to_anchor(
                anchor_widget,
                size,
                position=position,
                offset=offset,
            )
        return place_surface_rect(
            self,  # type: ignore[arg-type]
            anchor_widget,
            size,
            position=position,
            offset=offset,
            margin=0,
            overlay_layer=self.overlay_layer,
        )
