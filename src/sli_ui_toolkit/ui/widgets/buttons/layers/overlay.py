"""OverlayPainterLayer — адаптер для функции/коллбэка кастомного оверлея."""

from __future__ import annotations

import inspect
from typing import Callable, Literal

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ._base import Layer

OverlayPainterCallback = (
    Callable[[QPainter, QRectF], None]
    | Callable[[QPainter, DrawContext], None]
    | Callable[[QPainter, DrawContext, ThemeManager], None]
)


class OverlayPainterLayer(Layer):
    """Widget-scoped layer that executes a custom overlay painter callback."""

    scope: Literal["region", "widget"] = "widget"

    def __init__(self, painter_fn: OverlayPainterCallback) -> None:
        self._painter_fn = painter_fn
        try:
            sig = inspect.signature(painter_fn)
            self._param_count = len(sig.parameters)
        except (ValueError, TypeError):
            self._param_count = 2

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        p = ctx.painter
        p.save()
        try:
            if self._param_count == 3:
                self._painter_fn(p, ctx, tm)  # type: ignore[call-arg]
            elif self._param_count == 1:
                self._painter_fn(p)  # type: ignore[call-arg]
            else:
                self._painter_fn(p, ctx.rect)  # type: ignore[call-arg]
        finally:
            p.restore()
