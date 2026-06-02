"""ButtonDrawContext — единый объект данных для рисования вместо 18 параметров.

Аналог QStyleOption в Qt / ButtonStyle в Flutter.
Все данные, необходимые painter-примитивам, собраны в одном immutable объекте.
"""

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from ..states import StateSet


@dataclass(frozen=True)
class ButtonDrawContext:
    """Immutable контекст рисования кнопки — все необходимые данные в одном месте."""

    # Основное
    widget: QWidget
    painter: QPainter
    rect: QRectF

    # Состояния
    states: StateSet

    # Стиль
    variant: str = "default"
    corner_radius: int = 6

    # Контент (может быть None для иконки без текста)
    content: Any = None  # ButtonContent | None

    # Оверрайды
    override_bg_color: QColor | None = None
    custom_bg_color: QColor | None = None

    # Декорации
    badge_text: str | None = None
    show_underline: bool = False
    underline_color: Any = None
    show_strike_through: bool = False
    is_footer: bool = False
