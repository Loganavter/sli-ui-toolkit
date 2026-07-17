"""Top-level window helpers: client-side decorations, frameless mode."""

from .custom_title_bar import CustomTitleBar
from .decorations import decorate_dialog, set_dialog_bg_color
from .frameless import apply_frameless, remove_frameless, set_frameless_runtime
from .presets import TitleBarPresets
from .title_bar_menu import (
    TitleBarMenu,
    TitleBarMenuStrip,
)
from .window_chrome import WindowChrome, WindowChromeConfig, set_window_bg_color
from .window_controls import WindowControlsConfig, WindowControlsHandle


__all__ = [
    "CustomTitleBar",
    "TitleBarMenu",
    "TitleBarMenuStrip",
    "TitleBarPresets",
    "WindowChrome",
    "WindowChromeConfig",
    "WindowControlsConfig",
    "WindowControlsHandle",
    "apply_frameless",
    "decorate_dialog",
    "remove_frameless",
    "set_dialog_bg_color",
    "set_frameless_runtime",
    "set_window_bg_color",
]
