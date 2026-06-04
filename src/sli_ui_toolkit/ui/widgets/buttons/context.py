"""DrawContext — immutable объект данных для одного цикла отрисовки кнопки."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from .state import StateSet
from .variants import VariantSpec


@dataclass(frozen=True)
class DrawContext:
    widget: QWidget
    painter: QPainter
    rect: QRectF

    states: StateSet
    variant: VariantSpec
    corner_radius: int

    content: Any = None  # Content | None — см. content.py

    override_bg_color: QColor | None = None
    custom_bg_color: QColor | None = None
    override_border_color: QColor | None = None

    badge_text: str | None = None
    show_underline: bool = False
    underline_color: Any = None
    underline_thickness: float | None = None
    show_strike_through: bool = False
    is_footer: bool = False

    icon_size_px: int = 22
    scroll_value: int | None = None
    scroll_value_always_visible: bool = False
