"""Button capabilities — independent, composable behavior modules.

Each capability encapsulates one piece of button functionality (scroll, long-press, menu)
and can be attached/detached without touching the widget core.
"""

from .base import ButtonCapability
from .scroll import ScrollCapability, ValuePopupContent
from .long_press import LongPressCapability
from .menu import MenuCapability

__all__ = [
    "ButtonCapability",
    "ScrollCapability",
    "ValuePopupContent",
    "LongPressCapability",
    "MenuCapability",
]
