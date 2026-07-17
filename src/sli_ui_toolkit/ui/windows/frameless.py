from __future__ import annotations

import sys

from PySide6.QtCore import QChildEvent, QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtGui import QCursor, QHoverEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget


RESIZE_MARGIN = 4
# Qt unbound max when maximumWidth/Height were never set.
QWIDGETSIZE_MAX = 16777215


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


def apply_frameless(window: QWidget, *, resizable: bool = True) -> None:
    flags = window.windowFlags()
    flags |= Qt.WindowType.FramelessWindowHint
    window.setWindowFlags(flags)
    if resizable:
        window.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        window.setMouseTracking(True)
    _set_resize_filter(window, enabled=resizable)


def remove_frameless(window: QWidget) -> None:
    flags = window.windowFlags() & ~Qt.WindowType.FramelessWindowHint
    window.setWindowFlags(flags)
    _set_resize_filter(window, enabled=False)


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
        window.setMouseTracking(True)
        _set_resize_filter(window, enabled=True)
    else:
        _set_resize_filter(window, enabled=False)

    _win_refresh_native_frame(window, custom_decorations=enabled)


def _set_resize_filter(window: QWidget, *, enabled: bool) -> None:
    existing = window.findChild(_ResizeFilter)
    app = QApplication.instance()
    if not enabled:
        if existing is not None:
            existing.clear_cursor()
            existing.end_manual_resize()
            if app is not None:
                app.removeEventFilter(existing)
            window.removeEventFilter(existing)
            existing.setParent(None)
            existing.deleteLater()
        return
    if existing is None:
        f = _ResizeFilter(window)
        # App-level filter so title-bar / content children cannot steal the
        # edge zone. Installing on both app and window would double-fire.
        if app is not None:
            app.installEventFilter(f)
        else:
            window.installEventFilter(f)


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
    """Edge-resize hit testing for frameless windows.

    Listens to the target window and (via the QApplication filter) its
    descendants so title-bar / content widgets cannot steal the edge zone.
    Falls back to a software drag when ``QWindow.startSystemResize`` fails
    (common for modal dialogs on Wayland).
    """

    def __init__(self, target: QWidget):
        super().__init__(target)
        self._target = target
        self._cursor_armed = False
        self._manual_edges = 0
        self._manual_origin = QPoint()
        self._manual_geometry = QRect()
        self._ensure_mouse_tracking(target)

    def _ensure_mouse_tracking(self, root: QWidget) -> None:
        """Need move events on children, otherwise only bare chrome updates the cursor."""
        try:
            root.setMouseTracking(True)
            root.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            for child in root.findChildren(QWidget):
                child.setMouseTracking(True)
        except RuntimeError:
            pass

    def eventFilter(self, obj, event):
        target = getattr(self, "_target", None)
        if target is None:
            return False

        t = event.type()
        if t == QEvent.Type.Show and obj is target:
            self._ensure_mouse_tracking(target)
            return False
        if t == QEvent.Type.ChildAdded and obj is target and isinstance(event, QChildEvent):
            child = event.child()
            if isinstance(child, QWidget):
                try:
                    child.setMouseTracking(True)
                except RuntimeError:
                    pass
            return False
        if t in (
            QEvent.Type.Hide,
            QEvent.Type.Close,
            QEvent.Type.WindowDeactivate,
            QEvent.Type.ApplicationDeactivate,
        ):
            if obj is target or (
                t == QEvent.Type.ApplicationDeactivate and obj is QApplication.instance()
            ):
                self.end_manual_resize()
                self._clear_cursor()
            return False

        if not isinstance(obj, QWidget):
            return False

        try:
            owner = obj.window()
        except RuntimeError:
            return False
        if owner is not target:
            # Pointer moved to another top-level — drop any stuck resize cursor.
            if self._cursor_armed and not self._manual_edges:
                self._clear_cursor()
            return False

        if target.isMaximized() or target.isFullScreen():
            self.end_manual_resize()
            self._clear_cursor()
            return False

        if self._manual_edges and t == QEvent.Type.MouseMove and isinstance(
            event, QMouseEvent
        ):
            self._update_manual_resize(event.globalPosition().toPoint())
            event.accept()
            return True

        if self._manual_edges and t == QEvent.Type.MouseButtonRelease and isinstance(
            event, QMouseEvent
        ):
            if event.button() == Qt.MouseButton.LeftButton:
                self.end_manual_resize()
                event.accept()
                return True

        local = self._local_pos(obj, event)
        if local is None:
            if t in (QEvent.Type.Leave, QEvent.Type.HoverLeave) and obj is target:
                self._clear_cursor()
            return False

        if t in (QEvent.Type.HoverMove, QEvent.Type.MouseMove):
            if not self._manual_edges:
                self._update_cursor(local.x(), local.y())
            return False

        if t in (QEvent.Type.Leave, QEvent.Type.HoverLeave) and obj is target:
            if not self._manual_edges:
                self._clear_cursor()
            return False

        if t == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            value = _edges_for_pos(target.width(), target.height(), local.x(), local.y())
            if value == 0:
                return False
            if self._start_resize(value, event.globalPosition().toPoint()):
                event.accept()
                return True
        return False

    def _local_pos(self, obj: QWidget, event) -> QPoint | None:
        target = self._target
        if isinstance(event, QHoverEvent):
            point = event.position().toPoint()
        elif isinstance(event, QMouseEvent):
            point = event.position().toPoint()
        else:
            return None
        if obj is target:
            return point
        try:
            return obj.mapTo(target, point)
        except RuntimeError:
            return None

    def _start_resize(self, edges: int, global_pos: QPoint) -> bool:
        target = self._target
        handle = target.windowHandle()
        if handle is not None:
            try:
                if handle.startSystemResize(Qt.Edges(edges)):
                    return True
            except Exception:
                pass
        self._begin_manual_resize(edges, global_pos)
        return True

    def _begin_manual_resize(self, edges: int, global_pos: QPoint) -> None:
        target = self._target
        self._manual_edges = edges
        self._manual_origin = QPoint(global_pos)
        self._manual_geometry = QRect(target.geometry())
        target.grabMouse()
        self._update_cursor_for_edges(edges)

    def _update_manual_resize(self, global_pos: QPoint) -> None:
        target = self._target
        edges = self._manual_edges
        if not edges:
            return
        dx = global_pos.x() - self._manual_origin.x()
        dy = global_pos.y() - self._manual_origin.y()
        geo = QRect(self._manual_geometry)
        min_w = max(1, target.minimumWidth())
        min_h = max(1, target.minimumHeight())
        max_w = target.maximumWidth()
        max_h = target.maximumHeight()

        if edges & _LEFT:
            new_left = geo.left() + dx
            max_left = geo.right() - min_w + 1
            if max_w < QWIDGETSIZE_MAX:
                max_left = min(max_left, geo.right() - max_w + 1)
            new_left = min(new_left, max_left)
            geo.setLeft(new_left)
        elif edges & _RIGHT:
            new_width = geo.width() + dx
            new_width = max(min_w, new_width)
            if max_w < QWIDGETSIZE_MAX:
                new_width = min(max_w, new_width)
            geo.setWidth(new_width)

        if edges & _TOP:
            new_top = geo.top() + dy
            max_top = geo.bottom() - min_h + 1
            if max_h < QWIDGETSIZE_MAX:
                max_top = min(max_top, geo.bottom() - max_h + 1)
            new_top = min(new_top, max_top)
            geo.setTop(new_top)
        elif edges & _BOTTOM:
            new_height = geo.height() + dy
            new_height = max(min_h, new_height)
            if max_h < QWIDGETSIZE_MAX:
                new_height = min(max_h, new_height)
            geo.setHeight(new_height)

        if geo.width() < min_w:
            if edges & _LEFT:
                geo.setLeft(geo.right() - min_w + 1)
            else:
                geo.setWidth(min_w)
        if geo.height() < min_h:
            if edges & _TOP:
                geo.setTop(geo.bottom() - min_h + 1)
            else:
                geo.setHeight(min_h)

        target.setGeometry(geo)

    def end_manual_resize(self) -> None:
        if not self._manual_edges:
            return
        self._manual_edges = 0
        target = self._target
        if target is not None and target.mouseGrabber() is target:
            target.releaseMouse()

    def _update_cursor(self, x: int, y: int) -> None:
        value = _edges_for_pos(self._target.width(), self._target.height(), x, y)
        if value == 0:
            self._clear_cursor()
            return
        self._update_cursor_for_edges(value)

    def _update_cursor_for_edges(self, value: int) -> None:
        self._clear_peer_cursors()
        cursor = QCursor(_cursor_for_edges(value))
        self._target.setCursor(cursor)
        self._cursor_armed = True

    def _clear_peer_cursors(self) -> None:
        """Drop resize cursors left on other top-levels (modal open / Wayland)."""
        app = QApplication.instance()
        if app is None:
            return
        target = self._target
        for widget in app.topLevelWidgets():
            if widget is target:
                continue
            peer = widget.findChild(_ResizeFilter)
            if peer is not None and peer is not self:
                peer.clear_cursor()

    def _clear_cursor(self) -> None:
        if not self._cursor_armed:
            return
        target = self._target
        if target is not None:
            target.unsetCursor()
        self._cursor_armed = False

    def clear_cursor(self) -> None:
        """Public hook for callers that remove the filter while a cursor is set."""
        self._clear_cursor()

