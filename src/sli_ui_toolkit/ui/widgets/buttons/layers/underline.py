"""UnderlineLayer — кастомное подчёркивание (явный цвет/accent fallback)."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from ..context import DrawContext
from ._base import Layer


class UnderlineLayer(Layer):
    scope = "widget"

    @staticmethod
    def _gate(ctx: DrawContext) -> bool:
        return bool(ctx.show_underline)

    def applies(self, ctx: DrawContext) -> bool:
        return self._gate(ctx)

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        if not self._gate(ctx):
            return
        widget = ctx.widget
        style = read_widget_style(widget)

        resolved = ctx.underline_color or style.underline_color
        has_explicit = resolved is not None
        if not resolved:
            resolved = style.accent_color or tm.get_color("accent")
        if resolved is None:
            return

        alpha = None
        if isinstance(resolved, QColor):
            if has_explicit:
                alpha = resolved.alpha()
            else:
                alpha = resolved.alpha() if resolved.alpha() < 255 else 200

        radius = max(0, ctx.corner_radius)
        scale = max(1.0, widget.rect().height() / 32.0)
        normalized_radius = radius / scale if scale > 0 else radius

        thickness = (
            ctx.underline_thickness if ctx.underline_thickness is not None else 1.0
        )
        thickness = max(0.0, float(thickness))

        tongue_reach = ctx.underline_tongue_reach
        if tongue_reach is not None:
            tongue_reach = tongue_reach / scale if scale > 0 else tongue_reach

        fade = ctx.underline_fade
        if fade is None:
            from sli_ui_toolkit.ui.widgets.buttons.feedback import get_default_underline_fade

            fade = get_default_underline_fade()

        cfg = UnderlineConfig(
            thickness=thickness,
            vertical_offset=0.0,
            arc_radius=normalized_radius,
            alpha=alpha,
            color=resolved,
            tongue_reach=tongue_reach,
            ring=bool(ctx.underline_ring),
            fade=bool(fade),
        )
        rect: QRectF | QRect = ctx.rect
        if hasattr(rect, "toAlignedRect"):
            rect = rect.toAlignedRect()
        draw_bottom_underline(ctx.painter, rect, tm, cfg)
