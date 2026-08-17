from __future__ import annotations

import logging
import os
import sys

import shiboken6
from PySide6.QtCore import QChildEvent, QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtGui import QCursor, QHoverEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget


RESIZE_MARGIN = 4
# Qt unbound max when maximumWidth/Height were never set.
QWIDGETSIZE_MAX = 16777215


def _resize_debug(message: str, *args) -> None:
    """Env-gated trace for the frameless resize hit-testing/drag pipeline.

    ``SLI_RESIZE_DEBUG=1`` turns it on; output lands in the host app's
    ``log.txt`` (``sli_ui_toolkit`` logger has the same handlers). Each line
    is tagged ``[resize-debug]`` so it can be grepped independently of other
    debug output.
    """
    flag = os.environ.get("SLI_RESIZE_DEBUG", "").strip().lower()
    if flag in ("", "0", "false", "no", "off"):
        return
    try:
        # Explicit opt-in trace: the host's logger levels must not gate it
        # (the toolkit logger sits at INFO/WARNING unless the app enables
        # debug mode). Bump only the sli_ui_toolkit tree, never the app's.
        parent = logging.getLogger("sli_ui_toolkit")
        if parent.level > logging.INFO:
            parent.setLevel(logging.INFO)
        log = logging.getLogger("sli_ui_toolkit.resize")
        if log.level > logging.INFO:
            log.setLevel(logging.INFO)
        log.info("[resize-debug] " + (message % args if args else message))
    except Exception:
        pass


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


def apply_frameless(
    window: QWidget, *, resizable: bool = True, outer_band: int | None = None
) -> None:
    flags = window.windowFlags()
    flags |= Qt.WindowType.FramelessWindowHint
    window.setWindowFlags(flags)
    if resizable:
        window.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        window.setMouseTracking(True)
    if outer_band:
        # Outer resize band: the surface carries ``outer_band`` transparent
        # pixels beyond the visible body, so the edge-resize zone can be
        # grabbed from outside the body like a native frame.
        window.setProperty("_csd_outer_band", int(outer_band))
    _set_resize_filter(window, enabled=resizable)
    if outer_band:
        _patch_outer_band_geometry(window, int(outer_band))


def _patch_outer_band_geometry(window: QWidget, band: int) -> None:
    """Re-expand ``resize``/``setGeometry`` by 2*band so the app keeps
    thinking in *content* size while the window surface carries the outer
    resize band (transparent — the visible body is inset by ``band``).

    The frameless manual-resize drag bypasses this patch by calling the
    base-class setter directly (see ``_update_manual_resize``).
    """
    orig_resize = window.resize
    orig_set_geometry = window.setGeometry

    def _resize(width: int, height: int) -> None:
        orig_resize(width + 2 * band, height + 2 * band)

    def _set_geometry(x: int, y: int, width: int, height: int) -> None:
        orig_set_geometry(x, y, width + 2 * band, height + 2 * band)

    window.resize = _resize  # type: ignore[method-assign]
    window.setGeometry = _set_geometry  # type: ignore[method-assign]
    # Keep the bound originals alive (they reference the C++ object).
    window._csd_outer_band_patch = (orig_resize, orig_set_geometry)  # type: ignore[attr-defined]


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
        # The filter is a QObject child of the window and dies with it, but
        # the app-level registration is NOT removed automatically — after
        # the window is destroyed every app event would still invoke the
        # dead filter (shiboken "already deleted" storm). The target's
        # ``destroyed`` fires before its children are deleted, so unhook
        # and release the override cursor there.
        def _on_window_destroyed(*_args) -> None:
            _resize_debug(
                "window %s destroyed: unhooking resize filter",
                type(window).__name__,
            )
            try:
                f.clear_cursor()
            except Exception:
                pass
            try:
                if app is not None:
                    app.removeEventFilter(f)
            except Exception:
                pass

        window.destroyed.connect(_on_window_destroyed)
        _resize_debug(
            "filter installed on %s (title=%r) margin=%d visible=%s",
            type(window).__name__,
            window.windowTitle(),
            f._resize_margin,
            window.isVisible(),
        )


_LEFT = int(Qt.Edge.LeftEdge.value)
_RIGHT = int(Qt.Edge.RightEdge.value)
_TOP = int(Qt.Edge.TopEdge.value)
_BOTTOM = int(Qt.Edge.BottomEdge.value)


def _edges_for_pos(
    rect_w: int, rect_h: int, x: int, y: int, margin: int = RESIZE_MARGIN
) -> int:
    m = margin
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
        # Snapshot the module-level margin at install: dialogs re-install
        # their chrome with a different margin (WindowChrome.install mutates
        # the process-wide RESIZE_MARGIN), and that must not retroactively
        # change this window's edge hit zones.
        band = 0
        try:
            band = int(target.property("_csd_outer_band") or 0)
        except Exception:
            band = 0
        # The CSD outer band extends the window surface beyond the visible
        # body, so the edge zone [0, margin] straddles the visible edge —
        # RESIZE_MARGIN pixels inside the body plus ``band`` outside it.
        self._resize_margin = int(RESIZE_MARGIN) + band
        self._cursor_armed = False
        # Edges the resize cursor is currently showing (0 = none). Coalescing
        # key: hover/move events re-arrive at the same edge position several
        # times per pointer position (Wayland re-delivers hover after a cursor
        # shape change), and re-setting the cursor on every event churns the
        # shape and repaints — the "cursor flickers frantically on the edge"
        # symptom. Only arm/change when the value actually differs.
        self._armed_edges = 0
        # True while OUR QApplication override cursor is on the top of the
        # override stack. The edge affordance uses the app-level override
        # cursor (not per-widget setCursor): child widgets with their own
        # cursor (buttons, combos, spinboxes, title-bar window controls)
        # re-apply it in their own hover handlers *after* this app filter,
        # so a window/child setCursor can never win — the override cursor
        # beats every widget cursor until it is restored.
        self._override_pushed = False
        self._manual_edges = 0
        self._manual_origin = QPoint()
        self._manual_geometry = QRect()
        self._native_resizing = False
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
        try:
            if not shiboken6.isValid(target):
                # The window was destroyed; the destroyed->unhook may not
                # have run before this queued event reached the filter.
                return False
        except Exception:
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
                _resize_debug(
                    "abort event %s on %s (was manual=%d native=%s)",
                    t,
                    type(target).__name__,
                    self._manual_edges,
                    self._native_resizing,
                )
                self.end_manual_resize()
                self._native_resizing = False
                self._clear_cursor(f"abort event {t}")
            return False

        if not isinstance(obj, QWidget):
            return False

        try:
            owner = obj.window()
        except RuntimeError:
            return False
        if owner is not target:
            # Do NOT clear blindly: overlapping top-levels share events —
            # occluded widgets of the window underneath (mouse tracking is
            # forced on) keep delivering HoverMove/MouseMove while the
            # pointer is over the window on top. Treating every such event
            # as "pointer moved away" clears the armed resize cursor while
            # the pointer is still on OUR edge (the arm→clear→arm flicker).
            # Re-evaluate from the real pointer position instead: clears
            # only when the pointer genuinely left our window.
            if not self._manual_edges:
                self._refresh_cursor_from_global()
            return False

        if target.isMaximized() or target.isFullScreen():
            self.end_manual_resize()
            self._native_resizing = False
            self._clear_cursor("window maximized/fullscreen")
            return False

        if self._manual_edges and t == QEvent.Type.MouseMove and isinstance(
            event, QMouseEvent
        ):
            self._update_manual_resize(event.globalPosition().toPoint())
            event.accept()
            return True

        if t == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            if event.button() == Qt.MouseButton.LeftButton:
                resizing = self._manual_edges or self._native_resizing
                _resize_debug(
                    "release on %s: manual=%d native=%s target=%dx%d",
                    type(target).__name__,
                    self._manual_edges,
                    self._native_resizing,
                    target.width(),
                    target.height(),
                )
                if self._manual_edges:
                    self.end_manual_resize()
                self._native_resizing = False
                if resizing:
                    # Re-snap hover + edge cursor to the real pointer position:
                    # after a live resize (native or manual) the window may
                    # have moved under the pointer, and no motion event fires
                    # until the user moves the mouse — leaving a stuck resize
                    # cursor / stale hover. The press was consumed, so consume
                    # the release too.
                    self._finish_resize_at(event.globalPosition().toPoint())
                    event.accept()
                    return True
            return False

        local = self._local_pos(obj, event)
        if local is None:
            if t in (QEvent.Type.Leave, QEvent.Type.HoverLeave) and obj is target:
                self._refresh_cursor_from_global()
            return False

        if t in (QEvent.Type.HoverMove, QEvent.Type.MouseMove):
            if not self._manual_edges:
                self._update_cursor(local.x(), local.y(), via=obj)
            return False

        if t in (QEvent.Type.Leave, QEvent.Type.HoverLeave) and obj is target:
            if not self._manual_edges:
                # Do NOT clear blindly: with WA_Hover on the whole tree, Qt
                # delivers HoverLeave to the target whenever the pointer
                # moves from it onto a WA_Hover child (children cover the
                # whole window) — the pointer can still be inside the edge
                # zone. Re-evaluate from the real cursor position instead;
                # that clears only when the pointer really left the window.
                self._refresh_cursor_from_global()
            return False

        if t == QEvent.Type.Resize and obj is target:
            # Keep the edge zone live while the window changes size (native
            # compositor drag, programmatic resize, layout-driven grow). The
            # pointer position may be stale during a compositor grab, but the
            # release handler below re-snaps it with the real position.
            # Skipped during a software drag: that path owns the cursor
            # (always the resize shape) until ``end_manual_resize``.
            if not self._manual_edges:
                self._refresh_cursor_from_global()
            return False

        if t == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            value = _edges_for_pos(
                target.width(), target.height(), local.x(), local.y(),
                self._resize_margin,
            )
            try:
                is_native_child = bool(
                    obj.testAttribute(Qt.WidgetAttribute.WA_NativeWindow)
                )
            except Exception:
                is_native_child = False
            _resize_debug(
                "press obj=%s%s native=%s local=%s mapped=%s target=%dx%d "
                "margin=%d -> edges=%d visible=%s max=%s",
                type(obj).__name__,
                "" if obj is target else f" (child of {type(target).__name__})",
                is_native_child,
                event.position().toPoint(),
                local,
                target.width(),
                target.height(),
                self._resize_margin,
                value,
                target.isVisible(),
                target.isMaximized() or target.isFullScreen(),
            )
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
                if handle.startSystemResize(Qt.Edge(edges)):
                    self._native_resizing = True
                    _resize_debug(
                        "startSystemResize edges=%d -> OK (native resize)",
                        edges,
                    )
                    return True
                _resize_debug(
                    "startSystemResize edges=%d -> False, falling back to manual",
                    edges,
                )
            except Exception as exc:
                _resize_debug(
                    "startSystemResize edges=%d raised %r, falling back to manual",
                    edges,
                    exc,
                )
        else:
            _resize_debug("no windowHandle yet, manual resize edges=%d", edges)
        self._begin_manual_resize(edges, global_pos)
        return True

    def _begin_manual_resize(self, edges: int, global_pos: QPoint) -> None:
        target = self._target
        self._manual_edges = edges
        self._manual_origin = QPoint(global_pos)
        self._manual_geometry = QRect(target.geometry())
        target.grabMouse()
        _resize_debug(
            "begin manual resize edges=%d grabber=%s target=%dx%d",
            edges,
            target.mouseGrabber() is target,
            target.width(),
            target.height(),
        )
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

        # Bypass the instance-level geometry patch (WindowChrome re-expands
        # ``setGeometry``/``resize`` by the outer band so the app thinks in
        # content size) — the manual drag computes the *window frame* rect
        # and must set it verbatim.
        from PySide6.QtWidgets import QWidget

        QWidget.setGeometry(target, geo)
        # The pointer is grabbed by this window during the software drag, so
        # children never receive HoverMove/MouseMove and the app-wide
        # HoverCoordinator never reconciles — button hover would stay stale
        # while the window (and the widgets under the cursor) move. Reconcile
        # from the real event position so hover tracks the live geometry.
        self._reconcile_hover(global_pos)
        _resize_debug(
            "manual move -> target=%dx%d min=%dx%d",
            target.width(),
            target.height(),
            target.minimumWidth(),
            target.minimumHeight(),
        )

    def end_manual_resize(self) -> None:
        if not self._manual_edges:
            return
        _resize_debug("end manual resize (was edges=%d)", self._manual_edges)
        self._manual_edges = 0
        target = self._target
        if target is not None and target.mouseGrabber() is target:
            target.releaseMouse()

    def _update_cursor(self, x: int, y: int, via=None) -> None:
        target = self._target
        width = target.width()
        height = target.height()
        via_name = type(via).__name__ if via is not None else "?"
        # ``_edges_for_pos`` treats any position past ``width - RESIZE_MARGIN``
        # as an edge — without a bounds check the resize cursor stays armed for
        # positions outside the window (stale global pos after a live resize).
        if x < 0 or y < 0 or x >= width or y >= height:
            self._clear_cursor(f"out of bounds at ({x}, {y}) via {via_name}")
            return
        value = _edges_for_pos(width, height, x, y, self._resize_margin)
        if value == 0:
            self._clear_cursor(f"out of zone at ({x}, {y}) via {via_name}")
            return
        if value == self._armed_edges and self._cursor_armed:
            # Already showing the right shape — Qt re-delivers hover events
            # several times per pointer position (and a cursor-shape change
            # triggers more on Wayland); re-setting the cursor on every one
            # of them churns the shape + repaints and visibly flickers.
            # The app-level override cursor is already pushed, so nothing
            # can have overridden the shape underneath — no re-arm needed.
            return
        _resize_debug(
            "arm resize cursor at (%d, %d) in %dx%d margin=%d -> edges=%d via %s",
            x,
            y,
            width,
            height,
            self._resize_margin,
            value,
            via_name,
        )
        self._update_cursor_for_edges(value)

    def _refresh_cursor_from_global(self) -> None:
        """Re-evaluate the edge-zone cursor from the current pointer position."""
        target = self._target
        if target is None or not target.isVisible():
            return
        local = target.mapFromGlobal(QCursor.pos())
        self._update_cursor(local.x(), local.y())

    def _finish_resize_at(self, global_pos: QPoint) -> None:
        """Snap edge cursor + hover to the real pointer after a live resize."""
        target = self._target
        if target is None:
            return
        local = target.mapFromGlobal(global_pos)
        self._update_cursor(local.x(), local.y())
        self._reconcile_hover(global_pos)

    def _reconcile_hover(self, global_pos: QPoint) -> None:
        """Refresh app-wide button hover from a real pointer position.

        Used while the pointer is grabbed by a live-resize drag, when no
        hover/move events reach the widgets.
        """
        target = self._target
        try:
            from sli_ui_toolkit.ui.widgets.helpers.hover_coordinator import (
                hover_coordinator,
            )

            hover_coordinator().reconcile(global_pos, source_window=target)
        except Exception:
            pass

    def _update_cursor_for_edges(self, value: int) -> None:
        cursor = QCursor(_cursor_for_edges(value))
        # Only one resize cursor may be "showing" app-wide: clear peers'
        # armed state (and their override-stack entries) before pushing ours,
        # so the override stack stays exactly one entry deep and each
        # filter's flags stay in sync with the stack.
        self._clear_peer_cursors()
        self._push_override_cursor(cursor)
        self._cursor_armed = True
        self._armed_edges = value

    def _push_override_cursor(self, cursor: QCursor) -> None:
        """Put ``cursor`` on top of the app-wide override stack.

        The override cursor is the only mechanism that beats child widgets
        re-applying their own cursor in their hover handlers (which run
        after this app-level filter, so window/child ``setCursor`` from here
        always loses and flickers). Peers were cleared first (see
        ``_update_cursor_for_edges``), so a restore-then-push keeps exactly
        one stack entry per arm.
        """
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        if self._override_pushed:
            try:
                app.restoreOverrideCursor()
            except Exception:
                pass
        try:
            app.setOverrideCursor(cursor)
            self._override_pushed = True
        except Exception:
            pass

    def _clear_peer_cursors(self) -> None:
        """Drop resize cursors left on other top-levels (modal open / Wayland)."""
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return
        target = self._target
        for widget in app.topLevelWidgets():
            if widget is target:
                continue
            peer = widget.findChild(_ResizeFilter)
            if peer is not None and peer is not self:
                peer._clear_cursor("superseded by another window")

    def _clear_cursor(self, reason: str = "") -> None:
        if not self._cursor_armed:
            return
        _resize_debug("clear resize cursor (%s)", reason or "unspecified")
        if self._override_pushed:
            app = QApplication.instance()
            if isinstance(app, QApplication):
                try:
                    app.restoreOverrideCursor()
                except Exception:
                    pass
            self._override_pushed = False
        self._cursor_armed = False
        self._armed_edges = 0

    def clear_cursor(self) -> None:
        """Public hook for callers that remove the filter while a cursor is set."""
        self._clear_cursor()

