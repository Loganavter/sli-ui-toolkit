"""ContentLayer — единственное место, где painter трогает контент."""

from __future__ import annotations

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ._base import Layer


class ContentLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        return ctx.effective_content is not None

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        if ctx.region_path is None or not ctx.region_clip_content:
            ctx.effective_content.draw(ctx, tm)
            return
        p = ctx.painter
        p.save()
        p.setClipPath(ctx.effective_path)
        ctx.effective_content.draw(ctx, tm)
        p.restore()
