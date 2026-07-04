"""BackgroundLayer — фон + рамка, с поддержкой footer-path (плоский верх / скруглённый низ)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ..specs import CornerRadii, is_uniform_radii
from ..state import ButtonState
from ..variants import derive_custom_palette, resolve_background_layers

from ._base import Layer


def _clamp_radii(rect: QRectF, radii: CornerRadii) -> tuple[float, float, float, float]:
    max_r = min(rect.width(), rect.height()) / 2.0
    tl, tr, br, bl = (max(0.0, float(r)) for r in radii)
    return (min(tl, max_r), min(tr, max_r), min(br, max_r), min(bl, max_r))


def rounded_rect_path(rect: QRectF, radii: CornerRadii) -> QPainterPath:
    """Build a closed path representing a rectangle with per-corner radii.

    Order: (top-left, top-right, bottom-right, bottom-left), clockwise.
    Identical pixel output to ``QPainter.drawRoundedRect`` when all four
    corners are equal.
    """
    tl, tr, br, bl = _clamp_radii(rect, radii)
    path = QPainterPath()
    path.moveTo(rect.left() + tl, rect.top())
    path.lineTo(rect.right() - tr, rect.top())
    if tr > 0:
        path.arcTo(rect.right() - 2 * tr, rect.top(), 2 * tr, 2 * tr, 90.0, -90.0)
    path.lineTo(rect.right(), rect.bottom() - br)
    if br > 0:
        path.arcTo(rect.right() - 2 * br, rect.bottom() - 2 * br, 2 * br, 2 * br, 0.0, -90.0)
    path.lineTo(rect.left() + bl, rect.bottom())
    if bl > 0:
        path.arcTo(rect.left(), rect.bottom() - 2 * bl, 2 * bl, 2 * bl, 270.0, -90.0)
    path.lineTo(rect.left(), rect.top() + tl)
    if tl > 0:
        path.arcTo(rect.left(), rect.top(), 2 * tl, 2 * tl, 180.0, -90.0)
    path.closeSubpath()
    return path


def _footer_path(rect: QRectF, radius: int) -> QPainterPath:
    """Плоский верх, скруглённый низ (uniform bottom radius)."""
    return rounded_rect_path(rect, (0, 0, int(radius), int(radius)))


def _footer_path_radii(rect: QRectF, radii: CornerRadii) -> QPainterPath:
    """Footer-вариант с независимыми нижними углами (верх всегда плоский)."""
    return rounded_rect_path(rect, (0, 0, int(radii[2]), int(radii[3])))


def _fill_outer(p: QPainter, rect: QRectF, radii: CornerRadii) -> None:
    if is_uniform_radii(radii):
        r = radii[0]
        p.drawRoundedRect(rect, r, r)
    else:
        p.drawPath(rounded_rect_path(rect, radii))


def _stroke_outer(p: QPainter, rect: QRectF, radii: CornerRadii) -> None:
    if is_uniform_radii(radii):
        r = radii[0]
        p.drawRoundedRect(rect, r, r)
    else:
        p.drawPath(rounded_rect_path(rect, radii))


class BackgroundLayer(Layer):
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        backgrounds, border_color = self._resolve(ctx, tm)
        override_border = ctx.effective_override_border
        if override_border is not None:
            border_color = override_border

        outer_radii: CornerRadii = ctx.corner_radii
        # AA-inset is only needed when stroking a border. When no border is
        # drawn (e.g., ghost variant), filling to the very edge avoids a
        # visible 0.5px gap on HiDPI when the button sits flush against the
        # window edge.
        has_border = border_color is not None
        if has_border:
            widget_rect = ctx.rect.adjusted(0.5, 0.5, -0.5, -0.5)
        else:
            widget_rect = QRectF(ctx.rect)
        path = _footer_path_radii(widget_rect, outer_radii) if ctx.is_footer else None

        region_rect = ctx.effective_rect
        is_subregion = (
            ctx.region_id is not None
            and region_rect is not None
            and region_rect != ctx.rect
        )

        for bg in backgrounds:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)

            if is_subregion:
                # Clip per-region fill to the outer (per-corner) capsule and the
                # region's own path so non-rectangular regions stay honest. A
                # region may also declare its own corner_radii which replaces the
                # plain rect path inherited from the outer clip.
                if path is not None:
                    outer = path
                else:
                    outer = rounded_rect_path(widget_rect, outer_radii)
                region_radii = ctx.region_corner_radii
                if region_radii is not None and ctx.region_path is None:
                    region_path = rounded_rect_path(region_rect, region_radii)
                else:
                    region_path = ctx.effective_path
                p.save()
                p.setClipPath(outer)
                p.setClipPath(region_path, Qt.ClipOperation.IntersectClip)
                p.drawPath(region_path)
                p.restore()
            elif path is not None:
                p.drawPath(path)
            else:
                _fill_outer(p, widget_rect, outer_radii)

        if border_color is not None and not is_subregion:
            p.setPen(QPen(border_color, 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if path is not None:
                p.drawPath(path)
            else:
                _stroke_outer(p, widget_rect, outer_radii)

    @staticmethod
    def _resolve(ctx: DrawContext, tm: ThemeManager) -> tuple[list[QColor], QColor | None]:
        """Возвращает (background layers, border) для текущего состояния."""
        states = ctx.effective_states
        variant = ctx.effective_variant
        override_bg = ctx.effective_override_bg
        custom_bg = ctx.effective_custom_bg

        # 1. Override — программное переопределение фона (CalendarDayButton).
        if override_bg is not None:
            return [override_bg], None

        # 2. Custom bg — выводим полный палет из произвольного цвета под variant.
        if custom_bg is not None:
            pal = derive_custom_palette(custom_bg, variant.name)
            if ButtonState.DISABLED in states:
                return [pal.disabled], None
            if ButtonState.PRESSED in states:
                backgrounds = [pal.normal, pal.pressed]
            elif ButtonState.HOVERED in states:
                backgrounds = [pal.normal, pal.hover]
            else:
                backgrounds = [pal.normal]
            border = pal.border if ctx.widget.isEnabled() else None
            return [bg for bg in backgrounds if bg.alpha() > 0], border

        # 3. Variant — стандартная resolve-логика + border из темы.
        backgrounds = resolve_background_layers(variant, states, tm)
        border = None
        if ctx.widget.isEnabled():
            theme_border = tm.try_get_color(f"{variant.token_prefix}.border")
            if theme_border is not None:
                border = QColor(theme_border)
        return backgrounds, border
