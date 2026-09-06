"""Public frameless-mode install/toggle API."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from .platform_win import _win_refresh_native_frame
from .resize_filter import _ResizeFilter, _resize_debug


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
    Maximized/fullscreen windows collapse the band to 0 (see
    ``resolve_csd_band``).
    """
    orig_resize = window.resize
    orig_set_geometry = window.setGeometry

    def _resize(width: int, height: int) -> None:
        from sli_ui_toolkit.ui.windows.frameless.geometry import resolve_csd_band

        eff = resolve_csd_band(window)
        # ``resolve_csd_band`` already collapses to 0 in maximized/fullscreen;
        # fall back to the captured band when the window is not yet maximized
        # but property hasn't been set.
        if eff == 0 and not (window.isMaximized() or window.isFullScreen()):
            eff = band
        orig_resize(width + 2 * eff, height + 2 * eff)

    def _set_geometry(x: int, y: int, width: int, height: int) -> None:
        from sli_ui_toolkit.ui.windows.frameless.geometry import resolve_csd_band

        eff = resolve_csd_band(window)
        if eff == 0 and not (window.isMaximized() or window.isFullScreen()):
            eff = band
        orig_set_geometry(x, y, width + 2 * eff, height + 2 * eff)

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
