"""In-paint marquee selection state (content-local, host-painted).

THE single marquee mechanism in the toolkit. It replaces the deleted
``MarqueeBandGesture`` + ``MarqueeBandOverlay`` pair (window-level overlay
child + content-to-window rect mapping).

Split of responsibilities:

- :class:`MarqueeState` owns drag tracking only: origin, band rect (both
  in **content coordinates**, identity — no window mapping), the
  short-lived ``QApplication`` event filter, and the ``on_update`` /
  ``on_finish`` callbacks. It never creates a widget and never imports
  app code.
- The HOST owns the visual: it keeps the current ``band_rect``, paints
  it with :func:`paint_marquee_band` in its own ``paintEvent``, and
  repaints only the region-limited damage from
  :func:`marquee_dirty_rect` (old ∪ new, ±1px).

Routing/motion match the deleted gesture exactly: moves with the left
button held are consumed (``True``); the left-button release finishes
the gesture and then passes through (``False``) so Qt press-tracking
never desyncs (see inv-gallery-hover-loss-2026-09-26); non-left
press/release while active is ignored (context-menu interleaving
witness, no cancel).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.core.debug_flags import any_flag

import logging

logger = logging.getLogger(__name__)

# Canonical toolkit var for marquee state traces. Call-time check,
# ``[marquee]`` prefix on every line, off by default even under host
# ``--debug``. Records reach the host log only through the ``on_trace``
# callback (the state never mutates logger levels at import time, and
# hosts without logging configured simply pass ``on_trace=None``).
_MARQUEE_DEBUG_VARS = ("SLI_MARQUEE_DEBUG",)

#: Default band accent (gallery-proven look). Hosts override per instance
#: via :meth:`MarqueeState.set_accent`.
DEFAULT_MARQUEE_ACCENT = QColor("#0078D4")

#: Fill opacity of the band (gallery look).
_MARQUEE_FILL_ALPHA = 48
#: 1px border opacity of the band (gallery look).
_MARQUEE_BORDER_ALPHA = 200


def _marquee_debug_enabled() -> bool:
    """True when marquee tracing was opted in via env."""
    return any_flag(*_MARQUEE_DEBUG_VARS)


def paint_marquee_band(
    painter: QPainter,
    rect: QRect,
    accent: QColor | None = None,
) -> None:
    """Paint the marquee band look into the host's paint device.

    Gallery look: ``accent`` fill at alpha 48 plus a 1px border at
    alpha 200. No-op on empty/invalid ``rect``. The host calls this
    from its own ``paintEvent`` with its content-local band rect.
    """
    if rect.isEmpty() or not rect.isValid():
        return
    base = QColor(accent) if accent is not None else QColor(DEFAULT_MARQUEE_ACCENT)
    fill = QColor(base)
    fill.setAlpha(_MARQUEE_FILL_ALPHA)
    border = QColor(base)
    border.setAlpha(_MARQUEE_BORDER_ALPHA)
    painter.fillRect(rect, fill)
    painter.setPen(QPen(border, 1))
    painter.drawRect(rect.adjusted(0, 0, -1, -1))


def marquee_dirty_rect(old: QRect, new: QRect, pad: int = 1) -> QRect:
    """Region-limited repaint area for a band change (old ∪ new, ±``pad``).

    Pure helper: the host repaints only this instead of the whole
    content on every mousemove. Either side may be empty (band shown /
    cleared); both empty yields an empty rect (nothing to repaint).
    """
    if old.isEmpty() and new.isEmpty():
        return QRect()
    if old.isEmpty():
        base = QRect(new)
    elif new.isEmpty():
        base = QRect(old)
    else:
        base = old.united(new)
    if base.isEmpty():
        return QRect()
    return base.adjusted(-pad, -pad, pad, pad)


class MarqueeState(QObject):
    """Tracks a left-button drag as a content-local rect; host paints it.

    Does **not** call ``grabMouse`` (no-op / warning on Wayland for
    in-window widgets). While active, installs a short-lived
    ``QApplication`` event filter and maps with ``globalPosition()``
    → host ``mapFromGlobal``.

    Host owns hit-testing, selection state, and ALL painting; this only
    owns the gesture geometry + filter lifetime.
    """

    def __init__(
        self,
        host: QWidget,
        parent: QObject | None = None,
        min_drag_px: int = 3,
        on_update: Callable[[QRect], None] | None = None,
        on_finish: Callable[[QRect], None] | None = None,
        on_trace: Callable[[str], None] | None = None,
    ):
        super().__init__(parent if parent is not None else host)
        self._host = host
        self._min_drag_px = max(1, int(min_drag_px))
        self._on_update = on_update
        self._on_finish = on_finish
        self._on_trace = on_trace
        self._origin: QPoint | None = None
        self._band = QRect()
        self._app_filter = False
        self._accent = QColor(DEFAULT_MARQUEE_ACCENT)

    @property
    def active(self) -> bool:
        return self._origin is not None

    @property
    def app_filter_installed(self) -> bool:
        return self._app_filter

    @property
    def band_rect(self) -> QRect:
        """Current band in host (content) coordinates; empty when idle."""
        return QRect(self._band)

    def accent(self) -> QColor:
        return QColor(self._accent)

    def set_accent(self, color: QColor) -> None:
        self._accent = QColor(color)

    def set_clip_widget(self, clip_widget: QWidget | None) -> None:
        """No-op kept for call-site compatibility.

        The deleted overlay path clipped a window-mapped rect to a
        scroll viewport; the in-paint band lives in content coordinates
        and needs no clipping, so this accepts and ignores its argument.
        """
        del clip_widget

    def set_on_update(self, callback: Callable[[QRect], None] | None) -> None:
        self._on_update = callback

    def set_on_finish(self, callback: Callable[[QRect], None] | None) -> None:
        self._on_finish = callback

    def _trace(self, message: str, *args) -> None:
        """Env-gated trace line via ``on_trace`` (already ``[marquee]``-prefixed)."""
        if self._on_trace is not None and _marquee_debug_enabled():
            try:
                self._on_trace(message % args if args else message)
            except Exception:
                pass

    def start(self, content_pos: QPoint) -> bool:
        """Begin a band at ``content_pos`` (host-local). Always True."""
        was_active = self._origin is not None
        self._trace(
            "[marquee] state.start pos=%s was_active=%s",
            content_pos, was_active,
        )
        self._origin = QPoint(content_pos)
        self._band = QRect(self._origin, self._origin).normalized()
        self._install_app_filter()
        if self._on_update is not None:
            self._on_update(QRect(self._band))
        return True

    def update_at(self, content_pos: QPoint) -> QRect:
        """Extend the band to ``content_pos``; returns the content rect.

        Identity mapping (content in = content out); empty when idle.
        """
        if self._origin is None:
            return QRect()
        rect = QRect(self._origin, QPoint(content_pos)).normalized()
        self._band = QRect(rect)
        if self._on_update is not None:
            self._on_update(QRect(rect))
        return rect

    def finish_at(self, content_pos: QPoint) -> QRect:
        """Finish the band at ``content_pos``; returns the content rect.

        Tiny drags (narrower AND shorter than ``min_drag_px``) finish as
        an empty rect. Always clears the band + filter and fires
        ``on_finish``.
        """
        if self._origin is None:
            return QRect()
        origin = self._origin
        self._origin = None
        self._band = QRect()
        rect = QRect(origin, QPoint(content_pos)).normalized()
        tiny = rect.width() < self._min_drag_px and rect.height() < self._min_drag_px
        self._trace(
            "[marquee] state.finish rect=%s tiny=%s min_drag_px=%d",
            rect, tiny, self._min_drag_px,
        )
        self._remove_app_filter()
        result = QRect() if tiny else rect
        if self._on_finish is not None:
            self._on_finish(QRect(result))
        return result

    def cancel(self) -> QRect:
        """Abandon the band without calling ``on_finish``.

        Returns the cleared band so the host can repaint that region.
        """
        cleared = QRect(self._band)
        self._trace(
            "[marquee] state.cancel was_active=%s had_filter=%s band=%s",
            self._origin is not None, self._app_filter, cleared,
        )
        self._origin = None
        self._band = QRect()
        self._remove_app_filter()
        return cleared

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        del watched
        if not self._app_filter or self._origin is None:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        et = event.type()
        if et == QEvent.Type.MouseButtonPress and event.button() != Qt.MouseButton.LeftButton:
            # Interleaving witness: right/middle press (context menu) while
            # a left-drag band is active. The state stays active on purpose
            # (no cancel here) — this line proves the overlap in the log.
            self._trace(
                "[marquee] state.press-ignored-while-active button=%s origin=%s",
                event.button(), self._origin,
            )
            return False
        if (
            et == QEvent.Type.MouseButtonRelease
            and event.button() != Qt.MouseButton.LeftButton
        ):
            self._trace(
                "[marquee] state.release-ignored-while-active button=%s origin=%s",
                event.button(), self._origin,
            )
            return False
        if et == QEvent.Type.MouseMove and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            pos = self._host.mapFromGlobal(event.globalPosition().toPoint())
            self.update_at(pos)
            return True
        if (
            et == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            pos = self._host.mapFromGlobal(event.globalPosition().toPoint())
            self.finish_at(pos)
            # Pass the release through (return False): the matching press
            # went through the window before the child filter consumed it,
            # so consuming the release here would leave Qt press-tracking
            # stuck on "LeftButton held" — later moves grab-route to the
            # press receiver with no hit-testing and no Enter events
            # (gallery hover capsule + delete badge stay dead until some
            # other balanced click; see inv-gallery-hover-loss-2026-09-26).
            # finish_at already removed the app filter, so this only
            # lets normal delivery continue — no double handling.
            return False
        return False

    def _install_app_filter(self) -> None:
        if self._app_filter:
            self._trace("[marquee] state.install-filter skip (already installed)")
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._app_filter = True
        self._trace("[marquee] state.install-filter ok")

    def _remove_app_filter(self) -> None:
        if not self._app_filter:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._app_filter = False
        self._trace("[marquee] state.remove-filter ok")
