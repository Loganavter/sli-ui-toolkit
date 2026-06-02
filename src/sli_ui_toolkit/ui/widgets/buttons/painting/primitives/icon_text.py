"""Примитив: рисование иконки с текстом рядом."""

from PyQt6.QtCore import Qt, QRect

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from ..context import ButtonDrawContext
from ...states import ButtonState


def draw_icon_and_text(ctx: ButtonDrawContext, text: str,
                       tm: ThemeManager) -> None:
    """Рисует иконку с текстом слева от неё (горизонтальный layout)."""
    button = ctx.widget
    painter = ctx.painter

    # Получить текущую иконку в зависимости от состояния
    if hasattr(button, '_icon_checked') and hasattr(button, '_icon_unchecked'):
        is_checked = ButtonState.CHECKED in ctx.states
        current_icon = button._icon_checked if is_checked else button._icon_unchecked
    else:
        return

    if current_icon is None or not text:
        return

    style = read_widget_style(button)
    icon_size = getattr(button, '_icon_size_px', 22)
    icon_px = int(style.icon_size_px or min(icon_size, 16))

    icon = resolve_icon(current_icon)
    pixmap = icon.pixmap(icon_px, icon_px)

    # Calculate layout: [icon] + gap + [text]
    gap = 6
    text_width = painter.fontMetrics().horizontalAdvance(text)
    total_width = icon_px + gap + text_width
    start_x = (button.width() - total_width) // 2
    icon_y = (button.height() - icon_px) // 2

    # Draw icon
    painter.drawPixmap(start_x, icon_y, pixmap)

    # Draw text
    text_color = style.foreground_color or tm.get_color("dialog.text")
    painter.setPen(text_color)
    text_x = start_x + icon_px + gap
    text_rect = QRect(text_x, 0, button.width() - text_x, button.height())
    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
