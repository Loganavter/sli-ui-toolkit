from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor, QHoverEvent, QMouseEvent
from PySide6.QtWidgets import QWidget


RESIZE_MARGIN = 4


def _win_refresh_native_frame(window: QWidget, custom_decorations: bool) -> None:
    if sys.platform != "win32":
        return
    handle = window.windowHandle()
    if handle is None:
        return
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return

    try:
        hwnd = wintypes.HWND(int(handle.winId()))
    except Exception:
        return

    user32 = ctypes.windll.user32

    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020

    if not custom_decorations:
        # Re-assert caption+thick frame so Aero Snap works after Qt stripped them.
        get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        get_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_long.restype = ctypes.c_ssize_t
        try:
            style = get_long(hwnd, GWL_STYLE)
            set_long(hwnd, GWL_STYLE, style | WS_CAPTION | WS_THICKFRAME)
        except Exception:
            pass

    # Win11 DWM corner preference: round natively, no-round in custom mode
    # (we paint our own rounded shape there).
    try:
        dwmapi = ctypes.windll.dwmapi
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_DEFAULT = 0
        DWMWCP_DONOTROUND = 1
        preference = ctypes.c_int(
            DWMWCP_DONOTROUND if custom_decorations else DWMWCP_DEFAULT
        )
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(preference),
            wintypes.DWORD(ctypes.sizeof(preference)),
        )
    except Exception:
        pass

    # Force DWM to recompute non-client area for the new flags.
    try:
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetWindowPos(
            hwnd,
            wintypes.HWND(0),
            0,
            0,
            0,
            0,
            SWP_FRAMECHANGED
            | SWP_NOMOVE
            | SWP_NOSIZE
            | SWP_NOZORDER
            | SWP_NOACTIVATE,
        )
    except Exception:
        pass


def apply_frameless(window: QWidget) -> None:
    flags = window.windowFlags()
    flags |= Qt.WindowType.FramelessWindowHint
    window.setWindowFlags(flags)
    window.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    if window.findChild(_ResizeFilter) is None:
        f = _ResizeFilter(window)
        window.installEventFilter(f)


def remove_frameless(window: QWidget) -> None:
    flags = window.windowFlags() & ~Qt.WindowType.FramelessWindowHint
    window.setWindowFlags(flags)
    f = window.findChild(_ResizeFilter)
    if f is not None:
        window.removeEventFilter(f)
        f.setParent(None)
        f.deleteLater()


def set_frameless_runtime(window: QWidget, enabled: bool) -> None:
    """Toggle FramelessWindowHint without recreating the native QWindow.

    QWidget.setWindowFlags() on a visible window triggers a hide/recreate/show
    cycle that the user perceives as the window "blinking" or "restarting".
    QWindow.setFlag (accessed via windowHandle()) updates the flags on the
    already-created platform window — no native surface recreation.

    Falls back to setWindowFlags if the window has not been shown yet
    (windowHandle() returns None pre-show; recreation is invisible then).
    """
    handle = window.windowHandle()
    if handle is not None:
        handle.setFlag(Qt.WindowType.FramelessWindowHint, enabled)
    else:
        flags = window.windowFlags()
        if enabled:
            flags |= Qt.WindowType.FramelessWindowHint
        else:
            flags &= ~Qt.WindowType.FramelessWindowHint
        window.setWindowFlags(flags)

    if enabled:
        window.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if window.findChild(_ResizeFilter) is None:
            f = _ResizeFilter(window)
            window.installEventFilter(f)
    else:
        f = window.findChild(_ResizeFilter)
        if f is not None:
            window.removeEventFilter(f)
            f.setParent(None)
            f.deleteLater()

    _win_refresh_native_frame(window, custom_decorations=enabled)


_LEFT = int(Qt.Edge.LeftEdge.value)
_RIGHT = int(Qt.Edge.RightEdge.value)
_TOP = int(Qt.Edge.TopEdge.value)
_BOTTOM = int(Qt.Edge.BottomEdge.value)


def _edges_for_pos(rect_w: int, rect_h: int, x: int, y: int) -> int:
    m = RESIZE_MARGIN
    value = 0
    if x <= m:
        value |= _LEFT
    elif x >= rect_w - m:
        value |= _RIGHT
    if y <= m:
        value |= _TOP
    elif y >= rect_h - m:
        value |= _BOTTOM
    return value


def _cursor_for_edges(value: int) -> Qt.CursorShape:
    left = bool(value & _LEFT)
    right = bool(value & _RIGHT)
    top = bool(value & _TOP)
    bottom = bool(value & _BOTTOM)
    if (top and left) or (bottom and right):
        return Qt.CursorShape.SizeFDiagCursor
    if (top and right) or (bottom and left):
        return Qt.CursorShape.SizeBDiagCursor
    if left or right:
        return Qt.CursorShape.SizeHorCursor
    return Qt.CursorShape.SizeVerCursor


class _ResizeFilter(QObject):
    def __init__(self, target: QWidget):
        super().__init__(target)
        self._target = target
        self._has_override_cursor = False

    def eventFilter(self, obj, event):
        if obj is not self._target:
            return False
        if self._target.isMaximized() or self._target.isFullScreen():
            self._clear_cursor()
            return False

        t = event.type()
        if t == QEvent.Type.HoverMove and isinstance(event, QHoverEvent):
            self._update_cursor(event.position().toPoint().x(), event.position().toPoint().y())
        elif t == QEvent.Type.HoverLeave:
            self._clear_cursor()
        elif t == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint()
                value = _edges_for_pos(self._target.width(), self._target.height(), pos.x(), pos.y())
                if value != 0:
                    handle = self._target.windowHandle()
                    if handle is not None:
                        try:
                            handle.startSystemResize(Qt.Edges(value))
                            event.accept()
                            return True
                        except Exception:
                            pass
        return False

    def _update_cursor(self, x: int, y: int) -> None:
        value = _edges_for_pos(self._target.width(), self._target.height(), x, y)
        if value == 0:
            self._clear_cursor()
            return
        cursor = QCursor(_cursor_for_edges(value))
        if self._has_override_cursor:
            self._target.setCursor(cursor)
        else:
            self._target.setCursor(cursor)
            self._has_override_cursor = True

    def _clear_cursor(self) -> None:
        if self._has_override_cursor:
            self._target.unsetCursor()
            self._has_override_cursor = False
