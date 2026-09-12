"""DrawContext — immutable объект данных для одного цикла отрисовки кнопки."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

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
    corner_radii: tuple[int, int, int, int] = (0, 0, 0, 0)

    content: Any = None  # Content | None — см. content.py

    override_bg_color: QColor | None = None
    custom_bg_color: QColor | None = None
    override_border_color: QColor | None = None
    hover_color: QColor | None = None
    hover_compose: str = "replace"
    bg_locked: bool = False
    hovered_region_id: str | None = None

    badge_text: str | None = None
    show_underline: bool = False
    underline_color: Any = None
    underline_thickness: float | None = None
    show_strike_through: bool = False
    is_footer: bool = False

    icon_size_px: int = 22
    content_padding: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    # Internal spacing for IconTextContent (icon ↔ label) — not a region split.
    gap_px: int = 6
    content_align: Qt.AlignmentFlag = (
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
    )

    # Region-aware fields. When `region_id` is set, layers should prefer these
    # over their whole-widget counterparts. Default None keeps single-region
    # consumers transparent.
    region_id: str | None = None
    region_rect: QRectF | None = None
    region_path: QPainterPath | None = None
    region_fill_path: QPainterPath | None = None
    region_states: StateSet | None = None
    region_content: Any = None
    region_variant: VariantSpec | None = None
    region_override_bg_color: QColor | None = None
    region_custom_bg_color: QColor | None = None
    region_override_border_color: QColor | None = None
    region_hover_color: QColor | None = None
    region_hover_compose: str | None = None
    region_bg_locked: bool | None = None
    region_group: str | None = None
    region_icon_size_px: int | None = None
    region_corner_radii: tuple[int, int, int, int] | None = None
    region_clip_content: bool = True
    region_ripple_rect: QRectF | None = None

    def scoped_to(
        self,
        *,
        region_id: str,
        rect: QRectF,
        path: QPainterPath | None = None,
        fill_path: QPainterPath | None = None,
        states: StateSet,
        content: Any = None,
        variant: VariantSpec | None = None,
        override_bg_color: QColor | None = None,
        custom_bg_color: QColor | None = None,
        override_border_color: QColor | None = None,
        hover_color: QColor | None = None,
        hover_compose: str | None = None,
        bg_locked: bool | None = None,
        group: str | None = None,
        icon_size_px: int | None = None,
        corner_radii: tuple[int, int, int, int] | None = None,
        clip_content: bool = True,
        ripple_rect: QRectF | None = None,
    ) -> "DrawContext":
        return replace(
            self,
            region_id=region_id,
            region_rect=rect,
            region_path=path,
            region_fill_path=fill_path if fill_path is not None else path,
            region_states=states,
            region_content=content,
            region_variant=variant,
            region_override_bg_color=override_bg_color,
            region_custom_bg_color=custom_bg_color,
            region_override_border_color=override_border_color,
            region_hover_color=hover_color,
            region_hover_compose=hover_compose,
            region_bg_locked=bg_locked,
            region_group=group,
            region_icon_size_px=icon_size_px,
            region_corner_radii=corner_radii,
            region_clip_content=clip_content,
            region_ripple_rect=ripple_rect if ripple_rect is not None else rect,
        )

    @property
    def effective_ripple_rect(self) -> QRectF:
        return self.region_ripple_rect if self.region_ripple_rect is not None else self.effective_rect

    # ---------------- effective accessors ----------------
    # Layers use these to be region-aware without caring whether a region is
    # active. Whole-widget layers (badge, strikethrough) ignore them.

    @property
    def effective_rect(self) -> QRectF:
        return self.region_rect if self.region_rect is not None else self.rect

    @property
    def effective_path(self) -> QPainterPath:
        if self.region_path is not None:
            return QPainterPath(self.region_path)
        path = QPainterPath()
        path.addRect(self.effective_rect)
        return path

    @property
    def effective_fill_path(self) -> QPainterPath:
        if self.region_fill_path is not None:
            return QPainterPath(self.region_fill_path)
        return self.effective_path

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
    def effective_hover_color(self) -> QColor | None:
        return (
            self.region_hover_color
            if self.region_hover_color is not None
            else self.hover_color
        )

    @property
    def effective_hover_compose(self) -> str:
        compose = (
            self.region_hover_compose
            if self.region_hover_compose is not None
            else self.hover_compose
        )
        return compose if compose in ("replace", "stack") else "replace"

    @property
    def effective_bg_locked(self) -> bool:
        if self.region_bg_locked is not None:
            return bool(self.region_bg_locked)
        return bool(self.bg_locked)

    @property
    def effective_group(self) -> str | None:
        return self.region_group

    @property
    def effective_icon_size_px(self) -> int:
        return (
            self.region_icon_size_px
            if self.region_icon_size_px is not None
            else self.icon_size_px
        )
