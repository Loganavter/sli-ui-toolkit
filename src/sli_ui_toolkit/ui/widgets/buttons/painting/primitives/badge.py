"""Примитив: рисование badge (значка) на кнопке."""

from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtCore import QRect

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from ..context import ButtonDrawContext
from ...states import ButtonState


def draw_badge(ctx: ButtonDrawContext, tm: ThemeManager) -> None:
    """Рисует numerical badge в правом верхнем углу кнопки."""
    if ctx.badge_text is None:
        return

    painter = ctx.painter
    style = read_widget_style(ctx.widget)

    text_color = style.foreground_color or tm.get_color("dialog.text")
    # Если кнопка checked, уменьшим видимость badge
    if ButtonState.CHECKED in ctx.states:
        text_color.setAlpha(140)

    font = QFont()
    font.setBold(True)
    font.setPixelSize(9)
    painter.setFont(font)
    painter.setPen(text_color)

    text_rect = QRect(ctx.widget.width() - 14, 1, 12, 10)
    painter.drawText(text_rect, ctx.badge_text)
