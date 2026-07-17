"""BackgroundLayer — фон + рамка, с поддержкой footer-path (плоский верх / скруглённый низ)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ..specs import CornerRadii, is_uniform_radii
from ..state import ButtonState, StateSet
from ..variants import (
    VariantSpec,
    derive_custom_palette,
    resolve_background_layers,
    _with_scaled_alpha,
)

from ._base import Layer

# Ambient group hover strength when hover_compose="stack".
_AMBIENT_HOVER_FACTOR = 0.45


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


@dataclass(frozen=True)
class BgResolveParams:
    """Testable inputs for background layer composition."""

    states: StateSet
    variant: VariantSpec
    override_bg: QColor | None = None
    custom_bg: QColor | None = None
    override_border: QColor | None = None
    hover_color: QColor | None = None
    hover_compose: str = "replace"
    bg_locked: bool = False
    region_id: str | None = None
    hovered_region_id: str | None = None
    group: str | None = None
    widget_enabled: bool = True


def _variant_standard_hover(variant: VariantSpec, tm: ThemeManager) -> QColor | None:
    if variant.resolve_bg is not None:
        # Custom resolvers (e.g. ghost) return the hover result for HOVERED-only.
        color = variant.resolve_bg(frozenset({ButtonState.HOVERED}), tm)
        return color if color.alpha() > 0 else None
    prefix = variant.token_prefix
    key = f"{prefix}.background.hover"
    color = tm.try_get_color(key)
    return QColor(color) if color is not None else None


def _variant_standard_pressed(variant: VariantSpec, tm: ThemeManager) -> QColor | None:
    if variant.resolve_bg is not None:
        color = variant.resolve_bg(frozenset({ButtonState.PRESSED}), tm)
        return color if color.alpha() > 0 else None
    prefix = variant.token_prefix
    key = f"{prefix}.background.pressed"
    color = tm.try_get_color(key)
    return QColor(color) if color is not None else None


def _variant_normal(variant: VariantSpec, tm: ThemeManager) -> QColor:
    layers = resolve_background_layers(variant, frozenset(), tm)
    if layers:
        return layers[0]
    # Custom resolvers like ghost intentionally return no idle fill. Falling
    # back to toggle.normal made idle ghost controls (tab close, etc.) look
    # permanently tinted against their host surface.
    if variant.resolve_bg is not None:
        return QColor(0, 0, 0, 0)
    return QColor(tm.get_color("button.toggle.background.normal"))


def resolve_button_background(
    params: BgResolveParams,
    tm: ThemeManager,
) -> tuple[list[QColor], QColor | None]:
    """Compose ordered background paint layers + optional border.

    Base source (first paint layer):
      override_bg (exact) → custom_bg normal → variant normal

    When ``bg_locked``, only the base is returned (calendar flat selected/disabled).

    Otherwise hover/pressed overlays follow ``hover_compose`` and optional
    ``hover_color`` (see BUTTON_API “Background sources”).
    """
    states = params.states
    variant = params.variant
    border: QColor | None = None
    custom_pal = None

    # --- base ---
    if params.override_bg is not None:
        base = QColor(params.override_bg)
    elif params.custom_bg is not None:
        custom_pal = derive_custom_palette(params.custom_bg, variant.name)
        if ButtonState.DISABLED in states:
            return [custom_pal.disabled], None
        base = custom_pal.normal
        if params.widget_enabled:
            border = custom_pal.border
    else:
        if ButtonState.DISABLED in states:
            return resolve_background_layers(variant, states, tm), None
        base = _variant_normal(variant, tm)
        if params.widget_enabled:
            theme_border = tm.try_get_color(f"{variant.token_prefix}.border")
            if theme_border is not None:
                border = QColor(theme_border)

    if params.override_border is not None:
        border = params.override_border

    if params.bg_locked:
        return ([base] if base.alpha() > 0 else []), None

    layers: list[QColor] = [base] if base.alpha() > 0 else []
    use_variant_checked = (
        ButtonState.CHECKED in states
        and params.override_bg is None
        and params.custom_bg is None
    )
    use_stack = (
        params.hover_compose == "stack"
        and bool(params.group)
        and ButtonState.PRESSED not in states
        and ButtonState.DISABLED not in states
    )
    # Pure theme CHECKED (±hover) without custom hover_color/stack: keep
    # resolve_background_layers fidelity (checked / checked.hover tokens).
    if (
        use_variant_checked
        and params.hover_color is None
        and not use_stack
    ):
        theme_layers = [
            c
            for c in resolve_background_layers(variant, states, tm)
            if c.alpha() > 0
        ]
        return theme_layers, border

    # CHECKED with custom hover_color or stack: checked overlay on base, then
    # the same compose hover rules as unchecked regions.
    if use_variant_checked:
        checked_only = resolve_background_layers(
            variant, frozenset({ButtonState.CHECKED}), tm
        )
        for overlay in checked_only[1:]:
            if overlay.alpha() > 0:
                layers.append(overlay)

    hover_layers: list[QColor] = []

    if ButtonState.HOVERED in states and ButtonState.DISABLED not in states:
        standard_hover: QColor | None
        if custom_pal is not None and params.override_bg is None:
            standard_hover = custom_pal.hover
        else:
            standard_hover = _variant_standard_hover(variant, tm)

        local_hover = (
            QColor(params.hover_color)
            if params.hover_color is not None
            else standard_hover
        )

        if use_stack:
            if standard_hover is not None and standard_hover.alpha() > 0:
                hover_layers.append(
                    _with_scaled_alpha(standard_hover, _AMBIENT_HOVER_FACTOR)
                )
            is_pointer = (
                params.region_id is not None
                and params.region_id == params.hovered_region_id
            )
            if is_pointer and local_hover is not None and local_hover.alpha() > 0:
                hover_layers.append(local_hover)
        elif ButtonState.PRESSED not in states:
            if local_hover is not None and local_hover.alpha() > 0:
                hover_layers.append(local_hover)

    layers.extend(hover_layers)

    if ButtonState.PRESSED in states and ButtonState.DISABLED not in states:
        if custom_pal is not None and params.override_bg is None:
            pressed = custom_pal.pressed
        else:
            pressed = _variant_standard_pressed(variant, tm)
        if pressed is not None and pressed.alpha() > 0:
            layers.append(pressed)

    return [c for c in layers if c.alpha() > 0], border


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
                if region_radii is not None:
                    region_path = rounded_rect_path(region_rect, region_radii)
                else:
                    # Use the fill-only path (controller.fill_paths), not the
                    # hit-test path (controller.paths/ctx.region_path): plain
                    # rect regions get a hairline overlap there so adjacent
                    # same-group fills don't leave an antialiased seam at
                    # non-pixel-aligned split boundaries. The outer clip below
                    # still trims overflow at the button's true edges, so
                    # this only affects inner region-to-region seams.
                    region_path = ctx.effective_fill_path
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
        return resolve_button_background(
            BgResolveParams(
                states=ctx.effective_states,
                variant=ctx.effective_variant,
                override_bg=ctx.effective_override_bg,
                custom_bg=ctx.effective_custom_bg,
                override_border=ctx.effective_override_border,
                hover_color=ctx.effective_hover_color,
                hover_compose=ctx.effective_hover_compose,
                bg_locked=ctx.effective_bg_locked,
                region_id=ctx.region_id,
                hovered_region_id=ctx.hovered_region_id,
                group=ctx.effective_group,
                widget_enabled=ctx.widget.isEnabled(),
            ),
            tm,
        )
