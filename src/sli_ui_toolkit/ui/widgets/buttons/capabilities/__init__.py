"""Button capabilities — independent, composable behavior modules.

Each capability encapsulates one piece of button functionality (long-press, ...)
and can be attached/detached without touching the widget core. Apps can define their
own capabilities the same way — see ``ButtonCapability``.
"""

from .base import ButtonCapability
from .long_press import LongPressCapability

__all__ = [
    "ButtonCapability",
    "LongPressCapability",
]
