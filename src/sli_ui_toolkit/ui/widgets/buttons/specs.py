"""Declarative button control specifications.

These dataclasses describe what a button control is. Runtime state lives in the
controller, and painting lives in the renderer/layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

from .content import ButtonRow
from .regions import ButtonRegion, Divider, SingleRegionSplit, SplitLayout


ActionCallback = Callable[[str, Any], None]


CornerRadii = tuple[int, int, int, int]


def normalize_corner_radii(
    corner_radius: int | None,
    corner_radii: CornerRadii | None,
    fallback: int = 0,
) -> CornerRadii:
    if corner_radii is not None:
        tl, tr, br, bl = corner_radii
        return (int(tl), int(tr), int(br), int(bl))
    base = int(corner_radius) if corner_radius is not None else fallback
    return (base, base, base, base)


def is_uniform_radii(radii: CornerRadii) -> bool:
    return radii[0] == radii[1] == radii[2] == radii[3]


@dataclass(frozen=True)
class ShapeSpec:
    corner_radius: int | None = None
    size: tuple[int, int] = (36, 36)
    icon_size: int = 22
    corner_radii: CornerRadii | None = None

    def qsize(self) -> QSize:
        return QSize(int(self.size[0]), int(self.size[1]))

    def resolved_corner_radii(self, fallback: int = 0) -> CornerRadii:
        return normalize_corner_radii(self.corner_radius, self.corner_radii, fallback)


@dataclass(frozen=True)
class ContentSpec:
    icon: Any = None
    text: str = ""
    rows: tuple[ButtonRow, ...] = ()

    @classmethod
    def from_region(cls, region: ButtonRegion) -> "ContentSpec":
        return cls(
            icon=region.icon,
            text=region.text,
            rows=tuple(region.rows or ()),
        )


@dataclass(frozen=True)
class RegionStyle:
    variant: str | None = None
    custom_bg_color: QColor | None = None
    override_bg_color: QColor | None = None
    override_border_color: QColor | None = None
    show_underline: bool | None = None
    underline_color: Any = None
    underline_thickness: float | None = None
    icon_size_px: int | None = None
    show_strike_through: bool = False

    @classmethod
    def from_region(cls, region: ButtonRegion) -> "RegionStyle":
        return cls(
            variant=region.variant,
            custom_bg_color=region.custom_bg_color,
            override_bg_color=region.override_bg_color,
            override_border_color=region.override_border_color,
            show_underline=region.show_underline,
            underline_color=region.underline_color,
            underline_thickness=region.underline_thickness,
            icon_size_px=region.icon_size_px,
            show_strike_through=region.show_strike_through,
        )


@dataclass(frozen=True)
class BehaviorSpec:
    kind: str
    action: str | None = None
    data: Any = None
    callback: ActionCallback | None = None


@dataclass(frozen=True)
class ClickBehavior(BehaviorSpec):
    kind: str = "click"


@dataclass(frozen=True)
class ToggleBehavior(BehaviorSpec):
    kind: str = "toggle"


@dataclass(frozen=True)
class LongPressBehavior(BehaviorSpec):
    delay_ms: int = 600
    kind: str = "long_press"


@dataclass(frozen=True)
class MenuBehavior(BehaviorSpec):
    items: tuple[tuple[str, Any], ...] = ()
    kind: str = "menu"


@dataclass(frozen=True)
class RegionSpec:
    id: str
    content: ContentSpec = field(default_factory=ContentSpec)
    behaviors: tuple[BehaviorSpec, ...] = ()
    style: RegionStyle = field(default_factory=RegionStyle)
    weight: float = 1.0
    enabled: bool = True
    badge: int | str | None = None
    cursor: Any = None
    rect_fn: Any = None
    path_fn: Any = None
    z_index: int = 0
    group: str | None = None

    @classmethod
    def from_region(cls, region: ButtonRegion) -> "RegionSpec":
        behaviors: list[BehaviorSpec] = [ClickBehavior()]
        if region.toggle:
            behaviors.append(ToggleBehavior())
        if region.long_press:
            behaviors.append(LongPressBehavior(delay_ms=region.long_press_ms))
        if region.menu:
            behaviors.append(MenuBehavior(items=tuple(region.menu)))
        return cls(
            id=region.id,
            content=ContentSpec.from_region(region),
            behaviors=tuple(behaviors),
            style=RegionStyle.from_region(region),
            weight=region.weight,
            enabled=region.enabled,
            badge=region.badge,
            cursor=region.cursor,
            rect_fn=region.rect_fn,
            path_fn=region.path_fn,
            z_index=region.z_index,
            group=region.group,
        )

    def to_region(self) -> ButtonRegion:
        toggle = any(isinstance(b, ToggleBehavior) for b in self.behaviors)
        long_press = next(
            (b for b in self.behaviors if isinstance(b, LongPressBehavior)),
            None,
        )
        menu = next((b for b in self.behaviors if isinstance(b, MenuBehavior)), None)
        return ButtonRegion(
            id=self.id,
            weight=self.weight,
            icon=self.content.icon,
            text=self.content.text,
            rows=list(self.content.rows) or None,
            toggle=toggle,
            long_press=long_press is not None,
            long_press_ms=long_press.delay_ms if long_press else 600,
            menu=list(menu.items) if menu else None,
            badge=self.badge,
            variant=self.style.variant,
            custom_bg_color=self.style.custom_bg_color,
            override_bg_color=self.style.override_bg_color,
            override_border_color=self.style.override_border_color,
            show_underline=self.style.show_underline,
            underline_color=self.style.underline_color,
            underline_thickness=self.style.underline_thickness,
            icon_size_px=self.style.icon_size_px,
            show_strike_through=self.style.show_strike_through,
            enabled=self.enabled,
            cursor=self.cursor,
            rect_fn=self.rect_fn,
            path_fn=self.path_fn,
            z_index=self.z_index,
            group=self.group,
        )


@dataclass(frozen=True)
class ButtonSpec:
    regions: tuple[RegionSpec, ...]
    split: SplitLayout = field(default_factory=SingleRegionSplit)
    divider: Divider | None = None
    shape: ShapeSpec = field(default_factory=ShapeSpec)
    variant: str = "default"
    density: str = "normal"
    defer_click: bool = False
    wheel_requires_focus: bool = False

    @classmethod
    def from_regions(
        cls,
        regions: list[ButtonRegion],
        *,
        split: SplitLayout | None = None,
        divider: Divider | None = None,
        shape: ShapeSpec | None = None,
        variant: str = "default",
        density: str = "normal",
        defer_click: bool = False,
        wheel_requires_focus: bool = False,
    ) -> "ButtonSpec":
        return cls(
            regions=tuple(RegionSpec.from_region(region) for region in regions),
            split=split or SingleRegionSplit(),
            divider=divider,
            shape=shape or ShapeSpec(),
            variant=variant,
            density=density,
            defer_click=defer_click,
            wheel_requires_focus=wheel_requires_focus,
        )

    def to_regions(self) -> list[ButtonRegion]:
        return [region.to_region() for region in self.regions]
