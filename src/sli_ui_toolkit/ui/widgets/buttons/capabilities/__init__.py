"""Button capabilities — independent, composable behavior modules.

Each capability encapsulates one piece of button functionality (long-press, menu, ...)
and can be attached/detached without touching the widget core. Apps can define their
own capabilities the same way — see ``ButtonCapability``.
"""

from .base import ButtonCapability
from .long_press import LongPressCapability
from .menu import MenuCapability

__all__ = [
    "ButtonCapability",
    "LongPressCapability",
    "MenuCapability",
]
