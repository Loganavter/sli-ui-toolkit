"""Примитив: рисование текста в кнопке."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtCore import QRect

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from ..context import ButtonDrawContext


def draw_text_only(
    ctx: ButtonDrawContext,
    text: str,
    tm: ThemeManager,
) -> None:
    """Рисует только текст, без иконки.

    Поддерживает многострочный текст (разделённый \n).
    """
    painter = ctx.painter
    style = read_widget_style(ctx.widget)

    text_color = style.foreground_color or tm.get_color("dialog.text")
    painter.setPen(text_color)

    # Поддержка многострочного текста
    lines = text.split('\n') if '\n' in text else [text]
    if len(lines) > 1:
        fm = painter.fontMetrics()
        line_height = fm.lineSpacing()
        total_height = line_height * len(lines)
        start_y = (ctx.widget.height() - total_height) // 2

        for i, line in enumerate(lines):
            line_rect = QRect(0, start_y + i * line_height, ctx.widget.width(), line_height)
            painter.drawText(line_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, line)
    else:
        painter.drawText(ctx.widget.rect(), Qt.AlignmentFlag.AlignCenter, text)
