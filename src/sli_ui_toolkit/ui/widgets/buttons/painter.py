"""Painter — пайплайн слоёв. Единственная точка отрисовки кнопки.

Default-pipeline задан в DEFAULT_LAYERS; Button может передать свой список через layers=.

Также экспортируется `ButtonPainter` — compat shim со старой статической `paint(...)`-сигнатурой
для downstream-кода, который опирался на публичный реэкспорт.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter

from sli_ui_toolkit.theme import ThemeManager

from .context import DrawContext
from .layers import (
    BackgroundLayer,
    ContentLayer,
    BadgeLayer,
    RippleLayer,
    UnderlineLayer,
    StrikethroughLayer,
    DividerLayer,
)
from .layers._base import Layer


def default_layers() -> list[Layer]:
    return [
        BackgroundLayer(),
        RippleLayer(),
        ContentLayer(),
        BadgeLayer(),
        UnderlineLayer(),
        DividerLayer(),
        StrikethroughLayer(),
    ]


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

        for scoped_ctx in iter_regions(ctx):
            for layer in self._layers:
                if getattr(layer, "scope", "region") != "region":
                    continue
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
        scroll_value: int | None = None,
        scroll_value_always_visible: bool = False,
        underline_color=None,
        underline_thickness: float | None = None,
        show_underline: bool = False,
        icon_size: int = 22,
        show_strike_through: bool = False,
        override_bg_color=None,
        custom_bg_color=None,
        is_footer: bool = False,
    ) -> None:
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
        if is_scrolling: states.add(ButtonState.SCROLLING)
        if not widget.isEnabled(): states.add(ButtonState.DISABLED)

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
            scroll_value=scroll_value,
            scroll_value_always_visible=scroll_value_always_visible,
        )
        Painter(ThemeManager.get_instance()).paint(ctx)
