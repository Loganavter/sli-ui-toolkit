"""Painter layers — каждый слой решает одну задачу отрисовки.

Pipeline по умолчанию задаётся в painter.DEFAULT_LAYERS.
"""

from .background import BackgroundLayer
from .content import ContentLayer
from .badge import BadgeLayer
from .underline import UnderlineLayer
from .strikethrough import StrikethroughLayer

__all__ = [
    "BackgroundLayer",
    "ContentLayer",
    "BadgeLayer",
    "UnderlineLayer",
    "StrikethroughLayer",
]
