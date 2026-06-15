"""UnderlineLayer — кастомное подчёркивание (явный цвет/accent fallback/scroll-style)."""

from __future__ import annotations

import warnings

from PyQt6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from ..context import DrawContext
from ._base import Layer


_MAX_UNDERLINE_THICKNESS = 3.0


def _clamp_underline_thickness(thickness: float) -> float:
    normalized = max(0.0, float(thickness))
    if normalized > _MAX_UNDERLINE_THICKNESS:
        warnings.warn(
            (
                "Button underline thickness is capped at "
                f"{_MAX_UNDERLINE_THICKNESS:.1f}px; got {normalized:.1f}px."
            ),
            RuntimeWarning,
            stacklevel=3,
        )
        return _MAX_UNDERLINE_THICKNESS
    return normalized


class UnderlineLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        return bool(
            ctx.effective_show_underline
            or ctx.effective_underline_color is not None
            or ctx.scroll_value is not None
        )

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        widget = ctx.widget
        style = read_widget_style(widget)

        resolved = ctx.effective_underline_color or style.underline_color
        has_explicit = resolved is not None
        if not resolved and (ctx.effective_show_underline or ctx.scroll_value is not None):
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

        thickness = (
            ctx.effective_underline_thickness
            if ctx.effective_underline_thickness is not None
            else (2.0 if ctx.scroll_value is not None else 1.0)
        )
        thickness = _clamp_underline_thickness(thickness)

        cfg = UnderlineConfig(
            thickness=thickness,
            vertical_offset=0.0,
            arc_radius=normalized_radius,
            alpha=alpha,
            color=resolved,
        )
        rect = ctx.effective_rect
        if hasattr(rect, "toAlignedRect"):
            rect = rect.toAlignedRect()
        draw_bottom_underline(ctx.painter, rect, tm, cfg)
