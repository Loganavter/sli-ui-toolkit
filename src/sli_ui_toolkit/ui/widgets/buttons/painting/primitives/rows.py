"""Примитив: рисование многострочного контента (rows)."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter
from PyQt6.QtCore import QRect

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from ..context import ButtonDrawContext


def draw_rows(
    ctx: ButtonDrawContext,
    rows: list,  # list[ButtonRow]
    tm: ThemeManager,
    compact: bool = False,
    row_gap: int = 2,
) -> None:
    """Рисует несколько строк текста с индивидуальным стилем каждой.

    compact=True: центрирует блок строк по вертикали кнопки (для месяцев/годов).
    compact=False: распределяет строки по ratio высоты (исходное поведение).
    """
    if not rows:
        return

    painter = ctx.painter
    style = read_widget_style(ctx.widget)
    widget_height = ctx.widget.height()
    widget_width = ctx.widget.width()

    def _font_for(row) -> QFont:
        font = QFont()
        font.setPixelSize(row.size)
        if row.weight == "bold":
            font.setBold(True)
        if getattr(row, "italic", False):
            font.setItalic(True)
        if getattr(row, "strikethrough", False):
            font.setStrikeOut(True)
        return font

    if compact:
        # Compact mode: вычислить реальные высоты и центрировать
        line_heights = [QFontMetrics(_font_for(row)).lineSpacing() for row in rows]

        total_h = sum(line_heights) + row_gap * max(0, len(rows) - 1)
        y_offset = max(0, (widget_height - total_h) // 2)

        for row, lh in zip(rows, line_heights):
            painter.setFont(_font_for(row))
            color = row.color or style.foreground_color or tm.get_color("dialog.text")
            painter.setPen(color)
            h_align = getattr(row, "h_align", Qt.AlignmentFlag.AlignHCenter)
            painter.drawText(
                QRect(0, y_offset, widget_width, lh),
                h_align | Qt.AlignmentFlag.AlignVCenter,
                row.text,
            )
            y_offset += lh + row_gap
    else:
        # Ratio mode: распределить по ratio
        y_offset = 0
        for row in rows:
            row_height = int(widget_height * row.ratio)
            if row_height <= 0:
                continue

            painter.setFont(_font_for(row))
            color = row.color or style.foreground_color or tm.get_color("dialog.text")
            painter.setPen(color)
            h_align = getattr(row, "h_align", Qt.AlignmentFlag.AlignHCenter)
            painter.drawText(
                QRect(0, y_offset, widget_width, row_height),
                h_align | Qt.AlignmentFlag.AlignVCenter,
                row.text,
            )
            y_offset += row_height
