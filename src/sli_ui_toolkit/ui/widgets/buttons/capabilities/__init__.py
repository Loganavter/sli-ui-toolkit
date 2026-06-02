"""Button capabilities — independent, composable behavior modules.

Each capability encapsulates one piece of button functionality (scroll, long-press, menu, etc.)
and can be attached/detached without touching the widget core.

Inspired by: MUI slots, Headless UI capabilities, Qt plugins.
"""

from .base import ButtonCapability
from .scroll import ScrollCapability
from .long_press import LongPressCapability
from .menu import MenuCapability
from .tint import TintCapability

__all__ = [
    "ButtonCapability",
    "ScrollCapability",
    "LongPressCapability",
    "MenuCapability",
    "TintCapability",
]
