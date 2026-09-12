"""DividerLayer — whole-widget split divider rendering."""

from __future__ import annotations

from PySide6.QtCore import QLineF
from PySide6.QtGui import QColor, QPen

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ._base import Layer


class DividerLayer(Layer):
    scope = "widget"

    def applies(self, ctx: DrawContext) -> bool:
        controller = getattr(ctx.widget, "_controller", None)
        if controller is not None:
            return controller.divider is not None
        return getattr(ctx.widget, "_divider", None) is not None

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        controller = getattr(ctx.widget, "_controller", None)
        divider = controller.divider if controller is not None else getattr(ctx.widget, "_divider", None)
        split = controller.split if controller is not None else getattr(ctx.widget, "_split", None)
        rects = (
            list(controller.rects.values())
            if controller is not None
            else list(getattr(ctx.widget, "_region_rects", {}).values())
        )
        if divider is None or split is None or len(rects) < 2:
            return
        color = tm.try_get_color(divider.color_token)
        if color is None:
            color = tm.get_color(divider.fallback_token)
        p = ctx.painter
        p.save()
        p.setPen(QPen(QColor(color), float(divider.thickness)))
        margin = float(divider.margin)
        for line in split.dividers(rects):
            p.drawLine(_inset_line(line, margin))
        p.restore()


def _inset_line(line: QLineF, margin: float) -> QLineF:
    if abs(line.x1() - line.x2()) < 0.01:
        return QLineF(line.x1(), line.y1() + margin, line.x2(), line.y2() - margin)
    return QLineF(line.x1() + margin, line.y1(), line.x2() - margin, line.y2())
