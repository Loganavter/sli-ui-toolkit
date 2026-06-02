"""Примитив: рисование зачёркивания (strikethrough) на кнопке."""

from PyQt6.QtGui import QColor, QPainter, QPen

from sli_ui_toolkit.theme import ThemeManager
from ..context import ButtonDrawContext


def draw_strikethrough(ctx: ButtonDrawContext, tm: ThemeManager) -> None:
    """Рисует диагональную линию через кнопку как визуальный индикатор ошибки/отключения."""
    if not ctx.show_strike_through:
        return

    painter = ctx.painter
    strike_color = QColor("#ff4444") if tm.is_dark() else QColor("#cc0000")
    strike_color.setAlpha(180)
    painter.setPen(QPen(strike_color, 2))
    painter.drawLine(4, ctx.widget.height() - 4, ctx.widget.width() - 4, 4)
