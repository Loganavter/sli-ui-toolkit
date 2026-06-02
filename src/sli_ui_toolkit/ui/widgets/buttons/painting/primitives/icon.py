"""Примитив: рисование иконки (standard, hover-value, scroll-value modes)."""

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from ..context import ButtonDrawContext
from ...states import ButtonState


def draw_icon(ctx: ButtonDrawContext, tm: ThemeManager) -> None:
    """Рисует иконку с поддержкой режимов: standard, hover-value, scroll-value.

    Режимы определяются автоматически на основе наличия данных в кнопке.
    """
    button = ctx.widget
    painter = ctx.painter

    # Получить текущую иконку в зависимости от состояния
    if hasattr(button, '_icon_checked') and hasattr(button, '_icon_unchecked'):
        is_checked = ButtonState.CHECKED in ctx.states
        current_icon = button._icon_checked if is_checked else button._icon_unchecked
    else:
        return

    if current_icon is None:
        return

    style = read_widget_style(button)
    icon_size = getattr(button, '_icon_size_px', 22)

    # Determine mode based on scroll capability
    has_scroll = hasattr(button, '_has_scroll') and button._has_scroll
    has_toggle = hasattr(button, '_has_toggle') and button._has_toggle

    if has_scroll:
        scroll_value = getattr(button, '_scroll_value', 0)
        scroll_value_always_visible = has_scroll and not has_toggle

        if scroll_value_always_visible:
            _draw_icon_standard(painter, button, current_icon, scroll_value,
                              scroll_value_always_visible, has_toggle,
                              style, tm, icon_size)
        else:
            _draw_icon_with_hover_value(painter, button, current_icon,
                                       scroll_value, style, tm, icon_size)
    else:
        _draw_icon_standard(painter, button, current_icon, None, False, False,
                          style, tm, icon_size)


def _draw_icon_standard(painter, widget: QWidget, current_icon, scroll_value,
                        scroll_value_always_visible, is_toggle_scroll, style,
                        tm: ThemeManager, icon_size: int) -> None:
    """Draw icon centered, optionally with scroll value below."""
    actual_icon_size = (
        max(12, int(style.icon_size_px or icon_size) - 4)
        if scroll_value_always_visible
        else int(style.icon_size_px or icon_size)
    )
    icon_pixmap = resolve_icon(current_icon).pixmap(actual_icon_size, actual_icon_size)

    opacity = 0.4 if is_toggle_scroll and scroll_value == 0 else 1.0
    painter.setOpacity(opacity)
    x = (widget.width() - actual_icon_size) // 2

    if scroll_value is not None and scroll_value_always_visible:
        value_h = 12
        gap = 2
        y = max(1, (widget.height() - actual_icon_size - value_h - gap) // 2)
    else:
        y = (widget.height() - actual_icon_size) // 2

    painter.drawPixmap(x, y, icon_pixmap)
    painter.setOpacity(1.0)

    if scroll_value is not None and scroll_value_always_visible:
        _draw_scroll_value_below(painter, widget, scroll_value, tm, style)


def _draw_icon_with_hover_value(painter, widget: QWidget, current_icon,
                               scroll_value, style, tm: ThemeManager,
                               icon_size: int) -> None:
    """Draw icon with scroll value indicator (hover mode)."""
    hover_icon_size = max(12, int(style.icon_size_px or icon_size) - 6)
    icon_pixmap = resolve_icon(current_icon).pixmap(hover_icon_size, hover_icon_size)
    h = widget.height()
    value_h = 10
    gap = 2
    icon_y = max(1, (h - hover_icon_size - value_h - gap) // 2)
    value_y = icon_y + hover_icon_size + gap

    opacity = 0.4 if scroll_value == 0 else 1.0
    painter.setOpacity(opacity)
    painter.drawPixmap(int((widget.width() - hover_icon_size) / 2), icon_y, icon_pixmap)
    painter.setOpacity(1.0)

    if scroll_value == 0:
        hidden_icon = get_named_icon("divider_hidden")
        eye_pixmap = resolve_icon(hidden_icon).pixmap(11, 11)
        center_x = widget.width() // 2
        painter.drawPixmap(center_x - 5, value_y, eye_pixmap)
    else:
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(style.foreground_color or tm.get_color("dialog.text"))
        text_rect = QRect(0, value_y, widget.width(), value_h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(scroll_value))


def _draw_scroll_value_below(painter, widget: QWidget, value: int,
                            tm: ThemeManager, style) -> None:
    """Draw scroll value text below icon."""
    font = QFont()
    font.setPixelSize(9)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(style.foreground_color or QColor(tm.get_color("dialog.text")))
    value_h = 12
    value_y = widget.height() - value_h - 1
    text_rect = QRect(0, value_y, widget.width(), value_h)
    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(value))
