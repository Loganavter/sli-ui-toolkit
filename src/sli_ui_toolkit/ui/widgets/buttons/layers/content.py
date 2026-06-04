"""ContentLayer — единственное место, где painter трогает контент."""

from __future__ import annotations

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ._base import Layer


class ContentLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        return ctx.content is not None

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        ctx.content.draw(ctx, tm)
