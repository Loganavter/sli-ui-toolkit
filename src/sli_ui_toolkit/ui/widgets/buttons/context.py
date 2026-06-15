"""DrawContext — immutable объект данных для одного цикла отрисовки кнопки."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from .state import StateSet
from .variants import VariantSpec


@dataclass(frozen=True)
class DrawContext:
    widget: QWidget
    painter: QPainter
    rect: QRectF

    states: StateSet
    variant: VariantSpec
    corner_radius: int

    content: Any = None  # Content | None — см. content.py

    override_bg_color: QColor | None = None
    custom_bg_color: QColor | None = None
    override_border_color: QColor | None = None

    badge_text: str | None = None
    show_underline: bool = False
    underline_color: Any = None
    underline_thickness: float | None = None
    show_strike_through: bool = False
    is_footer: bool = False

    icon_size_px: int = 22
    scroll_value: int | None = None
    scroll_value_always_visible: bool = False

    # Region-aware fields. When `region_id` is set, layers should prefer these
    # over their whole-widget counterparts. Default None keeps single-region
    # consumers transparent.
    region_id: str | None = None
    region_rect: QRectF | None = None
    region_states: StateSet | None = None
    region_content: Any = None
    region_variant: VariantSpec | None = None
    region_override_bg_color: QColor | None = None
    region_custom_bg_color: QColor | None = None
    region_override_border_color: QColor | None = None
    region_show_underline: bool | None = None
    region_underline_color: Any = None
    region_underline_thickness: float | None = None
    region_icon_size_px: int | None = None

    def scoped_to(
        self,
        *,
        region_id: str,
        rect: QRectF,
        states: StateSet,
        content: Any = None,
        variant: VariantSpec | None = None,
        override_bg_color: QColor | None = None,
        custom_bg_color: QColor | None = None,
        override_border_color: QColor | None = None,
        show_underline: bool | None = None,
        underline_color: Any = None,
        underline_thickness: float | None = None,
        icon_size_px: int | None = None,
    ) -> "DrawContext":
        return replace(
            self,
            region_id=region_id,
            region_rect=rect,
            region_states=states,
            region_content=content,
            region_variant=variant,
            region_override_bg_color=override_bg_color,
            region_custom_bg_color=custom_bg_color,
            region_override_border_color=override_border_color,
            region_show_underline=show_underline,
            region_underline_color=underline_color,
            region_underline_thickness=underline_thickness,
            region_icon_size_px=icon_size_px,
        )

    # ---------------- effective accessors ----------------
    # Layers use these to be region-aware without caring whether a region is
    # active. Whole-widget layers (badge, strikethrough) ignore them.

    @property
    def effective_rect(self) -> QRectF:
        return self.region_rect if self.region_rect is not None else self.rect

    @property
    def effective_states(self) -> StateSet:
        return self.region_states if self.region_states is not None else self.states

    @property
    def effective_content(self) -> Any:
        return self.region_content if self.region_content is not None else self.content

    @property
    def effective_variant(self) -> VariantSpec:
        return self.region_variant if self.region_variant is not None else self.variant

    @property
    def effective_override_bg(self) -> QColor | None:
        return (
            self.region_override_bg_color
            if self.region_override_bg_color is not None
            else self.override_bg_color
        )

    @property
    def effective_custom_bg(self) -> QColor | None:
        return (
            self.region_custom_bg_color
            if self.region_custom_bg_color is not None
            else self.custom_bg_color
        )

    @property
    def effective_override_border(self) -> QColor | None:
        return (
            self.region_override_border_color
            if self.region_override_border_color is not None
            else self.override_border_color
        )

    @property
    def effective_show_underline(self) -> bool:
        return (
            self.region_show_underline
            if self.region_show_underline is not None
            else self.show_underline
        )

    @property
    def effective_underline_color(self) -> Any:
        return (
            self.region_underline_color
            if self.region_underline_color is not None
            else self.underline_color
        )

    @property
    def effective_underline_thickness(self) -> float | None:
        return (
            self.region_underline_thickness
            if self.region_underline_thickness is not None
            else self.underline_thickness
        )

    @property
    def effective_icon_size_px(self) -> int:
        return (
            self.region_icon_size_px
            if self.region_icon_size_px is not None
            else self.icon_size_px
        )
