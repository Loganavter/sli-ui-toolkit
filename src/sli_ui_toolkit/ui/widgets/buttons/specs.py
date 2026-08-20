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


def _to_corner_radii(values) -> CornerRadii:
    tl, tr, br, bl = values
    return (int(tl), int(tr), int(br), int(bl))


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


@dataclass
class ButtonConfig:
    """Декларативная конфигурация — альтернатива kwargs."""
    icon: Any = None
    text: str = ""
    rows: list[ButtonRow] | None = None
    toggle: bool = False
    long_press: bool = False
    long_press_ms: int = 600
    badge: int | str | None = None
    show_underline: bool = False
    underline_color: Any = None
    underline_thickness: float | None = None
    underline_tongue_reach: float | None = None
    underline_ring: bool = False
    underline_fade: bool | None = None
    size: tuple[int, int] = (36, 36)
    icon_size: int = 22
    corner_radius: int | None = None
    corner_radii: CornerRadii | None = None
    border_color: QColor | None = None
    variant: str = "default"
    density: str = "normal"
    wheel_requires_focus: bool = False
    # ``None`` → process-wide ``get_default_defer_click()``.
    defer_click: bool | int | str | None = None
    #: grow with the parent layout up to the full text width, compress below
    #: it (pair with a row ``marquee=True`` for overflowing text)
    text_fit: bool = False

    def to_kwargs(self) -> dict[str, Any]:
        """Field values keyed by the ``Button.__init__`` kwarg they override."""
        return {
            "icon": self.icon,
            "text": self.text,
            "rows": self.rows,
            "toggle": self.toggle,
            "long_press": self.long_press,
            "long_press_ms": self.long_press_ms,
            "badge": self.badge,
            "show_underline": self.show_underline,
            "underline_color": self.underline_color,
            "underline_thickness": self.underline_thickness,
            "underline_tongue_reach": self.underline_tongue_reach,
            "underline_ring": self.underline_ring,
            "underline_fade": self.underline_fade,
            "size": self.size,
            "icon_size": self.icon_size,
            "corner_radius": self.corner_radius,
            "corner_radii": self.corner_radii,
            "border_color": self.border_color,
            "variant": self.variant,
            "density": self.density,
            "wheel_requires_focus": self.wheel_requires_focus,
            "defer_click": self.defer_click,
            "text_fit": self.text_fit,
        }
