"""Windows-only native-frame plumbing for frameless windows (DWM/ctypes)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QWidget


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
