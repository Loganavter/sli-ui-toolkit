"""Helpers for top-level Qt popup surfaces (ContextMenu popup mode)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

POPUP_WINDOW_FLAGS = (
    Qt.WindowType.Popup
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.NoDropShadowWindowHint
)


def configure_popup_widget(widget: QWidget) -> None:
    """Apply standard popup window attributes for toolkit chrome widgets."""
    widget.setWindowFlags(POPUP_WINDOW_FLAGS)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def _ensure_window_handle(widget: QWidget):
    handle = widget.windowHandle()
    if handle is not None:
        return handle
    # Creating a native window is required on Wayland before transientParent
    # can be set. Prefer an existing handle when Qt already mapped the widget.
    widget.winId()
    return widget.windowHandle()


def bind_popup_transient_parent(widget: QWidget, anchor: QWidget | None) -> None:
    """Associate *widget* with *anchor*'s top-level window for Wayland xdg_popup.

    Parentless popups are placed by the compositor (often screen-center). Keep
    the QWidget parent and set ``QWindow.transientParent`` explicitly once the
    native handles exist.

    On Windows, do **not** force ``winId()`` / ``setTransientParent`` against a
    translucent frameless host: that combination permanently breaks DWM alpha
    compositing for in-window siblings of the host (soft shadows paint as
    solid black until process restart). Global geometry from
    ``place_popup_at_global`` is enough there.
    """
    if anchor is None:
        return
    try:
        host = anchor.window()
    except RuntimeError:
        return
    if host is None or host is widget:
        return

    if sys.platform.startswith("win") and host.testAttribute(
        Qt.WidgetAttribute.WA_TranslucentBackground
    ):
        return

    try:
        host_handle = _ensure_window_handle(host)
        popup_handle = _ensure_window_handle(widget)
    except RuntimeError:
        return
    if host_handle is None or popup_handle is None:
        return
    if popup_handle.transientParent() is not host_handle:
        popup_handle.setTransientParent(host_handle)


def screen_available_rect(
    widget: QWidget | None = None,
    *,
    margin: int = 4,
    global_pos: QPoint | None = None,
) -> QRect:
    screen = None
    if global_pos is not None:
        try:
            screen = QGuiApplication.screenAt(global_pos)
        except Exception:
            screen = None
    if screen is None and widget is not None:
        try:
            screen = widget.screen()
        except RuntimeError:
            screen = None
    if screen is None and widget is not None:
        try:
            screen = QGuiApplication.screenAt(widget.frameGeometry().center())
        except Exception:
            screen = None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QRect(0, 0, 1, 1)
    return screen.availableGeometry().adjusted(margin, margin, -margin, -margin)


def clamp_popup_rect(
    rect: QRect,
    widget: QWidget | None = None,
    *,
    margin: int = 4,
    global_pos: QPoint | None = None,
) -> QRect:
    available = screen_available_rect(widget, margin=margin, global_pos=global_pos)
    if available.width() <= 0 or available.height() <= 0:
        return rect
    width = min(rect.width(), available.width())
    height = min(rect.height(), available.height())
    x = max(available.left(), min(rect.x(), available.right() - width + 1))
    y = max(available.top(), min(rect.y(), available.bottom() - height + 1))
    return QRect(x, y, width, height)


def place_popup_at_global(
    widget: QWidget,
    global_pos: QPoint,
    *,
    margin: int = 4,
) -> QRect:
    """Move *widget* to *global_pos* and clamp to the available screen area."""
    widget.adjustSize()
    size = widget.size()
    if not size.isValid() or size.width() < 1 or size.height() < 1:
        size = widget.sizeHint()
    target = clamp_popup_rect(
        QRect(global_pos, size),
        widget,
        margin=margin,
        global_pos=global_pos,
    )
    widget.setGeometry(target)
    return target


def popup_contains_global(
    widget: QWidget,
    global_pos,
    *,
    opaque_panel: QWidget,
) -> bool:
    """Return whether *global_pos* lies inside the opaque panel of a popup."""
    if not widget.isVisible():
        return False
    try:
        top_left = opaque_panel.mapToGlobal(QPoint(0, 0))
        return QRect(top_left, opaque_panel.size()).contains(global_pos)
    except RuntimeError:
        return False
