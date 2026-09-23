"""Outer border stroke for region-composed buttons (widget scope).

``BackgroundLayer`` deliberately skips the border stroke for any region whose
rect differs from the button rect (see ``BUTTON_API.md`` "whole-button"
borders) — which means a fully region-composed button (cover + text rows,
segmented capsules) can never show an outline: ``setBorderColor()`` only
writes the override property and nothing ever strokes it.

``BorderLayer`` closes exactly that gap: for region-composed buttons with an
explicit widget-level border override (``Button.setBorderColor``), it strokes
one outer rounded rect on top of the region fills. Scope is intentionally
narrow:

- plain (non-region) buttons are untouched — ``BackgroundLayer`` keeps its
  own stroke path;
- variant theme borders (``{prefix}.border``) are NOT picked up here; region
  fills already carry variant styling, and silently adding variant edges to
  every region button would change existing visuals. An outline on a region
  button is always an explicit host opt-in via ``setBorderColor``;
- ``setBorderColor(None)`` keeps meaning "no outline" (used e.g. to suppress
  inherited edges);
- like ``BackgroundLayer``, an explicit override always wins: it strokes even
  on disabled / ``bg_locked`` buttons (the override is the host saying "this
  edge matters"). Clear it with ``setBorderColor(None)`` when the edge must
  follow the disabled wash instead.

Outline width honors the ``borderWidth`` dynamic property (``float >= 1``,
default ``1.0``) — the same property ``BackgroundLayer`` reads for plain
buttons — so ``setProperty("borderWidth", 2)`` gives a 2px leader edge.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ..specs import CornerRadii
from ._base import Layer, outline_width
from .background import _footer_path_radii, rounded_rect_path


def _outer_corner_radii(ctx: DrawContext) -> CornerRadii:
    return ctx.corner_radii


class BorderLayer(Layer):
    """Widget-scope outer outline for region-composed buttons."""

    scope = "widget"

    def applies(self, ctx: DrawContext) -> bool:
        widget = ctx.widget
        controller = getattr(widget, "_controller", None)
        regions = getattr(controller, "regions", ()) or ()
        if not regions:
            return False
        try:
            override = getattr(widget, "_border_color_override", None)
        except Exception:
            override = None
        return override is not None

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        try:
            border = getattr(ctx.widget, "_border_color_override", None)
        except Exception:
            border = None
        if border is None:
            return
        if not isinstance(border, QColor):
            try:
                border = QColor(border)
            except Exception:
                return
        width = outline_width(ctx.widget)
        inset = width / 2.0
        p = ctx.painter
        if not isinstance(p, QPainter):
            return
        p.save()
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(border, width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(ctx.rect).adjusted(inset, inset, -inset, -inset)
            radii = _outer_corner_radii(ctx)
            if ctx.is_footer:
                p.drawPath(_footer_path_radii(rect, radii))
            else:
                p.drawPath(rounded_rect_path(rect, radii))
        finally:
            p.restore()
