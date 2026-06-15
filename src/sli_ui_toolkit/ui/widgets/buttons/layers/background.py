"""BackgroundLayer — фон + рамка, с поддержкой footer-path (плоский верх / скруглённый низ)."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ..state import ButtonState
from ..variants import derive_custom_palette, resolve_background

from ._base import Layer


def _footer_path(rect: QRectF, radius: int) -> QPainterPath:
    """Плоский верх, скруглённый низ."""
    path = QPainterPath()
    path.moveTo(rect.left(), rect.top())
    path.lineTo(rect.right(), rect.top())
    path.arcTo(rect.right() - 2 * radius, rect.bottom() - 2 * radius,
               2 * radius, 2 * radius, 0, -90)
    path.arcTo(rect.left(), rect.bottom() - 2 * radius,
               2 * radius, 2 * radius, 270, -90)
    path.closeSubpath()
    return path


class BackgroundLayer(Layer):
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg, border_color = self._resolve(ctx, tm)
        override_border = ctx.effective_override_border
        if override_border is not None:
            border_color = override_border

        radius = max(0, ctx.corner_radius)
        # Whole-widget rounded shape (used for footer-path and as a clip when
        # the region rect is a sub-area of the widget).
        widget_rect = ctx.rect.adjusted(0.5, 0.5, -0.5, -0.5)
        path = _footer_path(widget_rect, radius) if ctx.is_footer else None

        region_rect = ctx.effective_rect
        is_subregion = (
            ctx.region_id is not None
            and region_rect is not None
            and region_rect != ctx.rect
        )

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)

        if is_subregion:
            # Clip per-region fill to the outer rounded capsule and the
            # region's own path so non-rectangular regions stay honest.
            outer = QPainterPath()
            if path is not None:
                outer = path
            else:
                outer.addRoundedRect(widget_rect, radius, radius)
            region_path = ctx.effective_path
            p.save()
            p.setClipPath(outer)
            p.setClipPath(region_path, Qt.ClipOperation.IntersectClip)
            p.drawPath(region_path)
            p.restore()
        elif path is not None:
            p.drawPath(path)
        else:
            p.drawRoundedRect(widget_rect, radius, radius)

        if border_color is not None and not is_subregion:
            p.setPen(QPen(border_color, 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if path is not None:
                p.drawPath(path)
            else:
                p.drawRoundedRect(widget_rect, radius, radius)

    @staticmethod
    def _resolve(ctx: DrawContext, tm: ThemeManager) -> tuple[QColor, QColor | None]:
        """Возвращает (bg, border) для текущего состояния. border=None если рамка не нужна."""
        states = ctx.effective_states
        variant = ctx.effective_variant
        override_bg = ctx.effective_override_bg
        custom_bg = ctx.effective_custom_bg

        # 1. Override — программное переопределение фона (CalendarDayButton).
        if override_bg is not None:
            return override_bg, None

        # 2. Custom bg — выводим полный палет из произвольного цвета под variant.
        if custom_bg is not None:
            pal = derive_custom_palette(custom_bg, variant.name)
            if ButtonState.DISABLED in states:
                return pal.disabled, None
            if ButtonState.PRESSED in states:
                bg = pal.pressed
            elif ButtonState.HOVERED in states:
                bg = pal.hover
            else:
                bg = pal.normal
            border = pal.border if ctx.widget.isEnabled() else None
            return bg, border

        # 3. Variant — стандартная resolve-логика + border из темы.
        bg = resolve_background(variant, states, tm)
        border = None
        if ctx.widget.isEnabled():
            theme_border = tm.try_get_color(f"{variant.token_prefix}.border")
            if theme_border is not None:
                border = QColor(theme_border)
        return bg, border
