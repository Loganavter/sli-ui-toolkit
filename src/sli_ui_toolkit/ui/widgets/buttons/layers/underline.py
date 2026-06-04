"""UnderlineLayer — кастомное подчёркивание (явный цвет/accent fallback/scroll-style)."""

from __future__ import annotations

from PyQt6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from ..context import DrawContext
from ._base import Layer


class UnderlineLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        return bool(
            ctx.show_underline
            or ctx.underline_color is not None
            or ctx.scroll_value is not None
        )

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        widget = ctx.widget
        style = read_widget_style(widget)

        resolved = ctx.underline_color or style.underline_color
        has_explicit = resolved is not None
        if not resolved and (ctx.show_underline or ctx.scroll_value is not None):
            resolved = style.accent_color or tm.get_color("accent")
        if resolved is None:
            return

        alpha = None
        if isinstance(resolved, QColor):
            if has_explicit:
                alpha = min(resolved.alpha(), 100)
            else:
                alpha = resolved.alpha() if resolved.alpha() < 255 else (
                    40 if ctx.scroll_value is not None else 200
                )

        radius = max(0, ctx.corner_radius)
        scale = max(1.0, widget.rect().height() / 32.0)
        normalized_radius = radius / scale if scale > 0 else radius

        cfg = UnderlineConfig(
            thickness=(
                ctx.underline_thickness
                if ctx.underline_thickness is not None
                else (2.0 if ctx.scroll_value is not None else 1.0)
            ),
            vertical_offset=0.0,
            arc_radius=normalized_radius,
            alpha=alpha,
            color=resolved,
        )
        draw_bottom_underline(ctx.painter, widget.rect(), tm, cfg)
