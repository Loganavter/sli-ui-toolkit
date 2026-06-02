"""Примитив: рисование фона кнопки."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtCore import QRectF

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from ..context import ButtonDrawContext
from ...tokens import TokenResolver


def draw_background_and_border(
    ctx: ButtonDrawContext,
    resolver: TokenResolver,
    tm: ThemeManager,
) -> None:
    """Рисует фон + границу кнопки с учётом состояния и варианта.

    Разрешает цвет через TokenResolver, затем рисует закругленный прямоугольник.
    """
    painter = ctx.painter
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    style = read_widget_style(ctx.widget)

    # Разрешить цвет фона через TokenResolver
    bg_color = resolver.resolve_background(
        ctx.variant,
        ctx.states,
        override_bg=ctx.override_bg_color,
        custom_bg=ctx.custom_bg_color,
    )

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(bg_color)

    radius = max(0, ctx.corner_radius)
    rect_f = ctx.rect.adjusted(0.5, 0.5, -0.5, -0.5)

    if ctx.is_footer:
        painter.drawRoundedRect(rect_f, radius, radius)
    else:
        painter.drawRoundedRect(rect_f, radius, radius)

    prefix = {"default": "button.toggle", "accent": "button.default", "delete": "button.delete",
              "primary": "button.primary", "surface": "button.dialog.default"}.get(ctx.variant, "button.toggle")
    border_key = f"{prefix}.border"
    border_color = tm.try_get_color(border_key)
    if border_color is not None:
        painter.setPen(QPen(QColor(border_color), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect_f, radius, radius)
