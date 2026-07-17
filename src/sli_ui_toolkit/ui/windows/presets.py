from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtGui import QIcon

from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar
from sli_ui_toolkit.ui.windows.title_bar_menu import TitleBarMenu, TitleBarMenuStrip
from sli_ui_toolkit.ui.windows.window_controls import WindowControlsConfig


class TitleBarPresets:
    @staticmethod
    def dialog(
        title: str,
        *,
        parent=None,
        close_icon: Any = None,
        show_close: bool = True,
    ) -> CustomTitleBar:
        return CustomTitleBar(
            parent=parent,
            title=title,
            show_minimize=False,
            show_maximize=False,
            show_close=show_close,
            close_icon=close_icon,
        )

    @staticmethod
    def app_shell(
        title: str,
        *,
        parent=None,
        menus: Sequence[TitleBarMenu] | TitleBarMenuStrip | None = None,
        controls: WindowControlsConfig | None = None,
        icon: QIcon | None = None,
        minimize_icon: Any = None,
        maximize_icon: Any = None,
        restore_icon: Any = None,
        close_icon: Any = None,
    ) -> CustomTitleBar:
        cfg = controls or WindowControlsConfig()
        bar = CustomTitleBar(
            parent=parent,
            title=title,
            icon=icon,
            minimize_icon=cfg.minimize_icon if minimize_icon is None else minimize_icon,
            maximize_icon=cfg.maximize_icon if maximize_icon is None else maximize_icon,
            restore_icon=cfg.restore_icon if restore_icon is None else restore_icon,
            close_icon=cfg.close_icon if close_icon is None else close_icon,
            show_minimize=cfg.show_minimize,
            show_maximize=cfg.show_maximize,
            show_close=cfg.show_close,
        )
        if menus is not None:
            strip = menus if isinstance(menus, TitleBarMenuStrip) else TitleBarMenuStrip(menus)
            bar.set_menu_strip(strip)
        return bar
