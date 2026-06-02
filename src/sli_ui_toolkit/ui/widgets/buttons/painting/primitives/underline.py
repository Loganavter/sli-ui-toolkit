"""Примитив: рисование нижнего подчёркивания кнопки."""

from PyQt6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from ..context import ButtonDrawContext
from ...states import ButtonState


def draw_underline(ctx: ButtonDrawContext, tm: ThemeManager) -> None:
    """Рисует кастомное подчёркивание с опциональным цветом."""
    if not ctx.show_underline and ctx.underline_color is None:
        return

    if not ctx.widget.isEnabled():
        return

    from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

    style = read_widget_style(ctx.widget)

    resolved_underline = ctx.underline_color or style.underline_color
    has_explicit_color = resolved_underline is not None

    if not resolved_underline and ctx.show_underline:
        resolved_underline = style.accent_color if ctx.variant in {"primary", "accent"} else None

    if resolved_underline is None:
        return

    alpha = None
    if isinstance(resolved_underline, QColor):
        if has_explicit_color:
            alpha = min(resolved_underline.alpha(), 100)
        else:
            # Если нет явного цвета, использовать более видимый alpha
            alpha = resolved_underline.alpha() if resolved_underline.alpha() < 255 else 200

    scale = max(1.0, ctx.widget.rect().height() / 32.0)
    normalized_radius = ctx.corner_radius / scale if scale > 0 else ctx.corner_radius

    config = UnderlineConfig(
        thickness=1.0,
        vertical_offset=1.0,
        arc_radius=normalized_radius,
        alpha=alpha,
        color=resolved_underline,
    )
    draw_bottom_underline(ctx.painter, ctx.widget.rect(), tm, config)
