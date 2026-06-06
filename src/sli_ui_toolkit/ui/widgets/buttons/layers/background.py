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
        if ctx.override_border_color is not None:
            border_color = ctx.override_border_color

        radius = max(0, ctx.corner_radius)
        rect_f = ctx.rect.adjusted(0.5, 0.5, -0.5, -0.5)
        path = _footer_path(rect_f, radius) if ctx.is_footer else None

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        if path is not None:
            p.drawPath(path)
        else:
            p.drawRoundedRect(rect_f, radius, radius)

        if border_color is not None:
            p.setPen(QPen(border_color, 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if path is not None:
                p.drawPath(path)
            else:
                p.drawRoundedRect(rect_f, radius, radius)

    @staticmethod
    def _resolve(ctx: DrawContext, tm: ThemeManager) -> tuple[QColor, QColor | None]:
        """Возвращает (bg, border) для текущего состояния. border=None если рамка не нужна."""
        # 1. Override — программное переопределение фона (CalendarDayButton).
        if ctx.override_bg_color is not None:
            return ctx.override_bg_color, None

        # 2. Custom bg — выводим полный палет из произвольного цвета под variant.
        if ctx.custom_bg_color is not None:
            pal = derive_custom_palette(ctx.custom_bg_color, ctx.variant.name)
            states = ctx.states
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
        bg = resolve_background(ctx.variant, ctx.states, tm)
        border = None
        if ctx.widget.isEnabled():
            theme_border = tm.try_get_color(f"{ctx.variant.token_prefix}.border")
            if theme_border is not None:
                border = QColor(theme_border)
        return bg, border
