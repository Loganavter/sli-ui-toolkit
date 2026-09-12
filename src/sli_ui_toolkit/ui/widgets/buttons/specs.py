"""Declarative button control specifications.

These dataclasses describe what a button control is. Runtime state lives in the
controller, and painting lives in the renderer/layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QSize

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


def region_behaviors(region: ButtonRegion, kind: str | None = None) -> tuple[BehaviorSpec, ...]:
    """Behaviors implied by a ``ButtonRegion``'s own fields.

    Computed on demand rather than stored separately, so it cannot drift from
    the region it describes — see ``docs/dev/BUTTON_REGION_ARCHITECTURE.md``.
    """
    behaviors: list[BehaviorSpec] = [
        ClickBehavior(action=region.action, data=region.action_data, callback=region.action_callback)
    ]
    if region.toggle:
        behaviors.append(ToggleBehavior())
    if region.long_press:
        behaviors.append(LongPressBehavior(delay_ms=region.long_press_ms))
    if kind is None:
        return tuple(behaviors)
    return tuple(b for b in behaviors if b.kind == kind)


@dataclass(frozen=True)
class ButtonSpec:
    regions: tuple[ButtonRegion, ...]
    split: SplitLayout = field(default_factory=SingleRegionSplit)
    divider: Divider | None = None
    shape: ShapeSpec = field(default_factory=ShapeSpec)
    variant: str = "default"
    density: str = "normal"
    defer_click: bool | int | str | None = None
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
        defer_click: bool | int | str | None = None,
        wheel_requires_focus: bool = False,
    ) -> "ButtonSpec":
        return cls(
            regions=tuple(regions),
            split=split or SingleRegionSplit(),
            divider=divider,
            shape=shape or ShapeSpec(),
            variant=variant,
            density=density,
            defer_click=defer_click,
            wheel_requires_focus=wheel_requires_focus,
        )

    def to_regions(self) -> list[ButtonRegion]:
        return list(self.regions)
