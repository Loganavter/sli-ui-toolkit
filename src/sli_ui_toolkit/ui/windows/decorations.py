"""Apply client-side decorations to a top-level dialog.

The dialog keeps its existing layout and content. A frameless, translucent
background is installed, a :class:`CustomTitleBar` is added above the
existing layout, and the dialog's own ``paintEvent`` is monkey-patched to
draw a rounded background — same approach the host app's main window uses
so dialogs render with identical shape and shadowing semantics.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QWidget

from .csd_helpers import (
    CsdRoundedBackground,
    TitleBarGeometryFilter,
    reapply_msgbox_transparency,
)
from .custom_title_bar import CustomTitleBar
from .rounded_body import (
    DEFAULT_CORNER_RADIUS,
    paint_rounded_window_background,
    resolve_window_bg_color,
)
from .window_chrome import WindowChrome, WindowChromeConfig, set_window_bg_color


class _CsdRoundedBackground(CsdRoundedBackground):
    pass


class _TitleBarGeometryFilter(TitleBarGeometryFilter):
    pass


def set_dialog_bg_color(dialog: QDialog, color: QColor) -> None:
    set_window_bg_color(dialog, color)


def decorate_dialog(
    dialog: QDialog,
    *,
    title: str = "",
    title_bar: CustomTitleBar | None = None,
    minimize_icon: Any = None,
    maximize_icon: Any = None,
    restore_icon: Any = None,
    close_icon: Any = None,
    show_minimize: bool = False,
    show_maximize: bool = False,
    show_close: bool = True,
    bg_color: QColor | None = None,
    corner_radius: int = DEFAULT_CORNER_RADIUS,
    resizable: bool = True,
    resize_margin: int | None = None,
) -> CustomTitleBar:
    """Install CSD on ``dialog`` and return the inserted title bar."""
    if title_bar is None:
        title_bar = CustomTitleBar(
            parent=dialog,
            title=title or dialog.windowTitle(),
            minimize_icon=minimize_icon,
            maximize_icon=maximize_icon,
            restore_icon=restore_icon,
            close_icon=close_icon,
            show_minimize=show_minimize,
            show_maximize=show_maximize,
            show_close=show_close,
        )
    elif title_bar.parent() is not dialog:
        title_bar.setParent(dialog)

    bg_token = "Window"
    if bg_color is not None:
        initial_color = QColor(bg_color)
    else:
        initial_color = resolve_window_bg_color(dialog, bg_token)

    reapply_msgbox_transparency(dialog)

    config = WindowChromeConfig(
        title=title or dialog.windowTitle(),
        title_bar=title_bar,
        corner_radius=corner_radius,
        bg_token=bg_token,
        resizable=resizable,
        resize_margin=resize_margin,
    )
    chrome = WindowChrome.install(dialog, config=config)
    if bg_color is not None:
        chrome.set_background_color(initial_color)
    return chrome.title_bar()
