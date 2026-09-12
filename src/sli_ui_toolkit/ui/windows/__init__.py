"""Top-level window helpers: client-side decorations, frameless mode."""

from .custom_title_bar import CustomTitleBar
from .decorations import decorate_dialog
from .frameless import apply_frameless, remove_frameless, set_frameless_runtime


__all__ = [
    "CustomTitleBar",
    "apply_frameless",
    "remove_frameless",
    "set_frameless_runtime",
    "decorate_dialog",
]
