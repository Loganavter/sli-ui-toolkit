"""Wayland-safe drag tracking for ``MarqueeBandOverlay``."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.core.debug_flags import any_flag
from sli_ui_toolkit.ui.widgets.overlays.marquee_band_overlay import MarqueeBandOverlay

import logging

logger = logging.getLogger(__name__)

# Canonical toolkit var for marquee-band gesture traces (start/finish
# geometry). Call-time check, ``[marquee]`` prefix on every line, off by
# default even under host ``--debug``. Never mutates logger levels at
# import time.
_MARQUEE_DEBUG_VARS = ("SLI_MARQUEE_DEBUG",)


def _marquee_debug_enabled() -> bool:
    """True when marquee gesture tracing was opted in via env."""
    return any_flag(*_MARQUEE_DEBUG_VARS)


def _marquee_debug(message: str, *args) -> None:
    """Env-gated marquee trace line (already carries its ``[marquee]`` prefix)."""
    if _marquee_debug_enabled():
        logger.debug(message, *args)


def map_content_rect_to_window(
    content: QWidget,
    content_rect: QRect,
    *,
    window: QWidget | None = None,
    clip_widget: QWidget | None = None,
) -> QRect:
    """Map a content-local rect into ``window`` (default ``content.window()``).

    When ``clip_widget`` is set (e.g. a scroll viewport), the band is intersected
    with that widget's area expressed in content coordinates first.
    """
    rect = QRect(content_rect)
    if clip_widget is not None:
        # Global round-trip works even when clip is not an ancestor of content
        # (siblings under a common window, scroll viewport + host, etc.).
        clip_in_content = content.mapFromGlobal(
            clip_widget.mapToGlobal(QPoint(0, 0))
        )
        rect = QRect(clip_in_content, clip_widget.size()).intersected(rect)
    if rect.isEmpty():
        return QRect()
    host = window if window is not None else content.window()
    if host is None:
        return QRect()
    top_left = content.mapTo(host, rect.topLeft())
    return QRect(top_left, rect.size())


class MarqueeBandGesture(QObject):
    """Tracks a left-button drag and drives a ``MarqueeBandOverlay``.

    Does **not** call ``grabMouse`` (no-op / warning on Wayland for in-window
    widgets). While active, installs a short-lived ``QApplication`` event filter
    and maps with ``globalPosition()`` → content ``mapFromGlobal``.

    Host owns hit-testing and selection state; this only owns the band + gesture.
    """

    def __init__(
        self,
        content: QWidget,
        *,
        parent: QObject | None = None,
        clip_widget: QWidget | None = None,
        min_drag_px: int = 3,
        on_update: Callable[[QRect], None] | None = None,
        on_finish: Callable[[QRect], None] | None = None,
    ):
        super().__init__(parent if parent is not None else content)
        self._content = content
        self._clip_widget = clip_widget
        self._min_drag_px = max(1, int(min_drag_px))
        self._on_update = on_update
        self._on_finish = on_finish
        self._overlay: MarqueeBandOverlay | None = None
        self._origin: QPoint | None = None
        self._app_filter = False
        self._accent: QColor | None = None

    @property
    def active(self) -> bool:
        return self._origin is not None

    @property
    def overlay(self) -> MarqueeBandOverlay | None:
        return self._overlay

    @property
    def app_filter_installed(self) -> bool:
        return self._app_filter

    def set_accent(self, color: QColor) -> None:
        self._accent = QColor(color)
        if self._overlay is not None:
            self._overlay.set_accent(self._accent)

    def set_clip_widget(self, clip_widget: QWidget | None) -> None:
        self._clip_widget = clip_widget

    def set_on_update(self, callback: Callable[[QRect], None] | None) -> None:
        self._on_update = callback

    def set_on_finish(self, callback: Callable[[QRect], None] | None) -> None:
        self._on_finish = callback

    def start(self, content_pos: QPoint) -> bool:
        """Begin a band at ``content_pos`` (content-local). Returns False if no window."""
        overlay = self._ensure_overlay()
        _marquee_debug(
            "[marquee] gesture.start pos=%s overlay=%r window=%r",
            content_pos, overlay, self._content.window(),
        )
        if overlay is None:
            return False
        self._origin = QPoint(content_pos)
        self._set_band_from_content_rect(QRect(self._origin, self._origin))
        self._install_app_filter()
        if self._on_update is not None:
            self._on_update(QRect(self._origin, self._origin).normalized())
        return True

    def cancel(self) -> None:
        """Hide the band without calling ``on_finish``."""
        self._origin = None
        self._hide_band()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        del watched
        if not self._app_filter or self._origin is None:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        et = event.type()
        if et == QEvent.Type.MouseMove and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            pos = self._content.mapFromGlobal(event.globalPosition().toPoint())
            self._update_at(pos)
            return True
        if (
            et == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            pos = self._content.mapFromGlobal(event.globalPosition().toPoint())
            self._finish_at(pos)
            # Pass the release through (return False): the matching press
            # went through the window before the child filter consumed it,
            # so consuming the release here would leave Qt press-tracking
            # stuck on "LeftButton held" — later moves grab-route to the
            # press receiver with no hit-testing and no Enter events
            # (gallery hover capsule + delete badge stay dead until some
            # other balanced click; see inv-gallery-hover-loss-2026-09-26).
            # _finish_at already removed the app filter, so this only
            # lets normal delivery continue — no double handling.
            return False
        return False

    def _ensure_overlay(self) -> MarqueeBandOverlay | None:
        host_window = self._content.window()
        if host_window is None:
            return None
        if self._overlay is None:
            self._overlay = MarqueeBandOverlay(host_window)
            if self._accent is not None:
                self._overlay.set_accent(self._accent)
        elif self._overlay.parentWidget() is not host_window:
            self._overlay.setParent(host_window)
            if self._accent is not None:
                self._overlay.set_accent(self._accent)
        return self._overlay

    def _set_band_from_content_rect(self, content_rect: QRect) -> None:
        overlay = self._ensure_overlay()
        if overlay is None:
            return
        overlay.set_band(
            map_content_rect_to_window(
                self._content,
                content_rect,
                clip_widget=self._clip_widget,
            )
        )

    def _hide_band(self) -> None:
        self._remove_app_filter()
        if self._overlay is not None:
            self._overlay.set_band(None)

    def _update_at(self, content_pos: QPoint) -> None:
        if self._origin is None:
            return
        rect = QRect(self._origin, content_pos).normalized()
        self._set_band_from_content_rect(rect)
        if self._on_update is not None:
            self._on_update(rect)

    def _finish_at(self, content_pos: QPoint) -> None:
        if self._origin is None:
            return
        origin = self._origin
        self._origin = None
        rect = QRect(origin, content_pos).normalized()
        _marquee_debug("[marquee] gesture.finish rect=%s", rect)
        self._hide_band()
        if self._on_finish is not None:
            if rect.width() < self._min_drag_px and rect.height() < self._min_drag_px:
                self._on_finish(QRect())
            else:
                self._on_finish(rect)

    def _install_app_filter(self) -> None:
        if self._app_filter:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._app_filter = True

    def _remove_app_filter(self) -> None:
        if not self._app_filter:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._app_filter = False
