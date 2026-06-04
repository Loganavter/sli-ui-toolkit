"""StrikethroughLayer — диагональная линия (error/disabled индикатор)."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPen

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ._base import Layer


class StrikethroughLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        return ctx.show_strike_through

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        widget = ctx.widget
        color = QColor("#ff4444") if tm.is_dark() else QColor("#cc0000")
        color.setAlpha(180)
        ctx.painter.setPen(QPen(color, 2))
        ctx.painter.drawLine(4, widget.height() - 4, widget.width() - 4, 4)
