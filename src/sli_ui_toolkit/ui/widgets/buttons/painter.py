"""Painter — пайплайн слоёв. Единственная точка отрисовки кнопки.

Default-pipeline задан в DEFAULT_LAYERS; Button может передать свой список через layers=.

Также экспортируется `ButtonPainter` — compat shim со старой статической `paint(...)`-сигнатурой
для downstream-кода, который опирался на публичный реэкспорт.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter

from sli_ui_toolkit.deprecations import BUTTON_PAINTER_PAINT, warn_deprecated
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

from .context import DrawContext
from .specs import _to_corner_radii, normalize_corner_radii
from .variants import get_variant
from .layers import (
    BackgroundLayer,
    ContentLayer,
    BadgeLayer,
    RippleLayer,
    UnderlineLayer,
    StrikethroughLayer,
    DividerLayer,
    FocusLayer,
)
from .layers._base import Layer


_CTX_CACHE: dict[int, DrawContext] = {}
_REGION_ORDER_CACHE: dict[int, list] = {}


def _ctx_cache_key(button) -> tuple:
    # Includes fields that affect DrawContext besides painter/rect; state is the hot path.
    return (
        id(button),
        frozenset(button._states),
        button._variant,
        button._corner_radius_px,
        button._icon_size_px,
        button._badge,
        button._show_underline,
        button._is_footer,
        getattr(button, "_hovered_region", None),
        getattr(button, "_bg_locked", False),
    )


def make_draw_context(button, qpainter: QPainter) -> DrawContext:
    """``DrawContext`` for the button's own paint pass, from its live state."""
    # P2: cache DrawContext per button state (excluding painter/rect)
    key = _ctx_cache_key(button)
    cached = getattr(button, "_draw_ctx_cache", None)
    if isinstance(cached, dict):
        hit = cached.get(key)
        if hit is not None:
            # Reuse cached variant/content etc, only swap painter+rect (paint-specific)
            from dataclasses import replace as _replace

            return _replace(hit, painter=qpainter, rect=QRectF(button.rect()), widget=button)
    # corner_radius_px is design px — scale at the paint boundary so a
    # circular swatch stays circular when the widget itself scales
    # (sizeHint/setFixedSize already use scaled_px, so a raw radius here
    # would round a 42px circle down to a 14px-corner square).
    scaled_radius = max(0, scaled_px(button._corner_radius_px))
    ctx = DrawContext(
        widget=button,
        painter=qpainter,
        rect=QRectF(button.rect()),
        states=frozenset(button._states),
        variant=get_variant(button._variant),
        corner_radius=scaled_radius,
        corner_radii=normalize_corner_radii(
            None,
            button._scaled_corner_radii(),
            fallback=scaled_radius,
        ),
        content=button._build_content(),
        override_bg_color=button._override_bg_color,
        custom_bg_color=button._custom_bg_color,
        override_border_color=button._border_color_override,
        hover_color=getattr(button, "_hover_color", None),
        hover_compose=getattr(button, "_hover_compose", "replace"),
        bg_locked=bool(getattr(button, "_bg_locked", False)),
        hovered_region_id=getattr(button, "_hovered_region", None),
        badge_text=str(button._badge) if button._badge is not None else None,
        show_underline=button._show_underline,
        underline_color=button._underline_config_color,
        underline_thickness=button._underline_thickness,
        underline_tongue_reach=button._underline_tongue_reach,
        underline_ring=button._underline_ring,
        underline_fade=button._underline_fade,
        show_strike_through=button._is_strike_through(),
        is_footer=button._is_footer,
        icon_size_px=button._icon_size_px,
        content_padding=button._content_padding,
        gap_px=button._gap_px,
        content_align=button._content_align,
    )
    if not isinstance(cached, dict):
        try:
            button._draw_ctx_cache = {}  # type: ignore[attr-defined]
            cached = button._draw_ctx_cache  # type: ignore[attr-defined]
        except Exception:
            return ctx
    # bound cache size per button
    if len(cached) > 32:
        cached.clear()
    cached[key] = ctx
    return ctx


def iter_button_regions(button, ctx: DrawContext):
    """Per-region scoped draw contexts for a multi-region button, in z-order."""
    if not button._controller.rects:
        button._controller.recompute_rects()
        button._sync_region_aliases()
    # P2: cache region z-order sort (invalidate when regions list identity changes)
    cache = getattr(button, "_region_order_cache", None)
    # regions list object identity changes on set_regions/set_spec
    regions_id = id(button._controller.regions)
    if isinstance(cache, dict) and cache.get("id") == regions_id and "order" in cache:
        ordered_regions = cache["order"]
    else:
        ordered_regions = sorted(
            enumerate(button._controller.regions),
            key=lambda item: (item[1].z_index, item[0]),
        )
        try:
            button._region_order_cache = {"id": regions_id, "order": ordered_regions}  # type: ignore[attr-defined]
        except Exception:
            pass
    for _index, region in ordered_regions:
        rect = button._controller.rects.get(region.id)
        if rect is None:
            continue
        states = frozenset(button._controller.states(region.id))
        yield ctx.scoped_to(
            region_id=region.id,
            rect=rect,
            path=button._controller.paths.get(region.id),
            fill_path=button._controller.fill_paths.get(region.id),
            states=states,
            content=button._build_region_content(region),
            variant=get_variant(region.variant or button._variant),
            override_bg_color=region.override_bg_color,
            custom_bg_color=region.custom_bg_color,
            override_border_color=region.override_border_color,
            hover_color=(
                region.hover_color
                if region.hover_color is not None
                else getattr(button, "_hover_color", None)
            ),
            hover_compose=region.hover_compose or getattr(button, "_hover_compose", "replace"),
            bg_locked=bool(region.bg_locked) or bool(getattr(button, "_bg_locked", False)),
            group=region.group,
            icon_size_px=region.icon_size_px,
            corner_radii=(
                tuple(0 if v == 0 else scaled_px(v) for v in _to_corner_radii(region.corner_radii))
                if region.corner_radii is not None
                else None
            ),
            clip_content=(
                region.clip_content
                if region.clip_content is not None
                else not bool(region.group)
            ),
            ripple_rect=button._controller.ripple_rect(region.id),
        )


def default_layers() -> list[Layer]:
    return [
        BackgroundLayer(),
        RippleLayer(),
        ContentLayer(),
        BadgeLayer(),
        UnderlineLayer(),
        DividerLayer(),
        StrikethroughLayer(),
        FocusLayer(),
    ]


def _cluster_scoped_regions(scoped_list: list[DrawContext]) -> list[list[DrawContext]]:
    """Group ``group=`` siblings into one paint cluster; leave others alone.

    Within a cluster, layers run outer-major (all backgrounds, then ripple,
    then content) so a shared group ripple is not covered by a sibling's
    BackgroundLayer. Ungrouped / stacked ``z_index`` regions stay
    region-major via singleton clusters, preserving overlay stacking.
    """
    clusters: list[list[DrawContext]] = []
    assigned_groups: set[str] = set()
    for scoped in scoped_list:
        group = scoped.region_group
        if group:
            if group in assigned_groups:
                continue
            assigned_groups.add(group)
            clusters.append(
                [s for s in scoped_list if s.region_group == group]
            )
        else:
            clusters.append([scoped])
    return clusters


class Painter:
    def __init__(self, tm: ThemeManager, layers: list[Layer] | None = None):
        self._tm = tm
        self._layers = layers if layers is not None else default_layers()

    @property
    def layers(self) -> list[Layer]:
        return self._layers

    def paint(self, ctx: DrawContext) -> None:
        iter_regions = getattr(ctx.widget, "iter_regions", None)
        if iter_regions is None:
            for layer in self._layers:
                if layer.applies(ctx):
                    layer.draw(ctx, self._tm)
            return

        region_layers = [
            layer
            for layer in self._layers
            if getattr(layer, "scope", "region") == "region"
        ]
        for cluster in _cluster_scoped_regions(list(iter_regions(ctx))):
            for layer in region_layers:
                for scoped_ctx in cluster:
                    if layer.applies(scoped_ctx):
                        layer.draw(scoped_ctx, self._tm)

        for layer in self._layers:
            if getattr(layer, "scope", "region") != "widget":
                continue
            if layer.applies(ctx):
                layer.draw(ctx, self._tm)


class ButtonPainter:
    """Compat shim: сохраняет старый публичный API ButtonPainter.paint(widget, painter, **kwargs).

    Делегирует новому Painter. Не используется внутри toolkit'а — только для downstream.
    """

    @staticmethod
    def paint(
        widget,
        painter: QPainter,
        icon_unchecked=None,
        icon_checked=None,
        text: str = "",
        rows=None,
        rows_compact: bool = False,
        is_checked: bool = False,
        is_pressed: bool = False,
        is_hovered: bool = False,
        is_scrolling: bool = False,
        badge_text: str | None = None,
        underline_color=None,
        underline_thickness: float | None = None,
        show_underline: bool = False,
        icon_size: int = 22,
        show_strike_through: bool = False,
        override_bg_color=None,
        custom_bg_color=None,
        is_footer: bool = False,
    ) -> None:
        warn_deprecated(BUTTON_PAINTER_PAINT, stacklevel=2)
        from .content import TextContent, RowsContent, IconContent, IconTextContent
        from .state import ButtonState
        from .variants import get_variant
        from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

        style = read_widget_style(widget, default_icon_size=icon_size)
        variant = get_variant(style.variant)

        states = set()
        if is_hovered: states.add(ButtonState.HOVERED)
        if is_pressed: states.add(ButtonState.PRESSED)
        if is_checked: states.add(ButtonState.CHECKED)
        if not widget.isEnabled(): states.add(ButtonState.DISABLED)

        content: RowsContent | IconTextContent | TextContent | IconContent | None
        if rows:
            content = RowsContent(rows=rows, compact=rows_compact)
        elif text and icon_unchecked:
            content = IconTextContent(icon=icon_unchecked, text=text)
        elif text:
            content = TextContent(text=text)
        elif icon_unchecked or icon_checked:
            content = IconContent(icon_unchecked=icon_unchecked, icon_checked=icon_checked)
        else:
            content = None

        ctx = DrawContext(
            widget=widget,
            painter=painter,
            rect=QRectF(widget.rect()),
            states=frozenset(states),
            variant=variant,
            corner_radius=max(
                0,
                int(style.corner_radius_px if style.corner_radius_px is not None else 6),
            ),
            content=content,
            override_bg_color=override_bg_color,
            custom_bg_color=custom_bg_color,
            badge_text=badge_text,
            show_underline=show_underline,
            underline_color=underline_color,
            underline_thickness=underline_thickness,
            show_strike_through=show_strike_through,
            is_footer=is_footer,
            icon_size_px=icon_size,
        )
        Painter(ThemeManager.get_instance()).paint(ctx)
