"""StrikethroughLayer — диагональная линия (error/disabled индикатор)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPen

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ._base import Layer


class StrikethroughLayer(Layer):
    scope = "widget"

    def applies(self, ctx: DrawContext) -> bool:
        return ctx.show_strike_through

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        widget = ctx.widget
        color = QColor("#ff4444") if tm.is_dark() else QColor("#cc0000")
        color.setAlpha(180)
        ctx.painter.setPen(QPen(color, scaled_px(2)))
        inset = scaled_px(4)
        ctx.painter.drawLine(
            inset, widget.height() - inset, widget.width() - inset, inset
        )
