"""Button control controller.

The controller owns runtime state and geometry for a declarative ``ButtonSpec``.
``Button`` keeps compatibility aliases while delegating region runtime concerns
here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath

from .layers.ripple import RippleEffect
from .regions import ButtonRegion, Divider, SingleRegionSplit, SplitLayout
from .specs import BehaviorSpec, ButtonSpec, RegionSpec, ScrollBehavior, ShapeSpec
from .state import ButtonState


@dataclass
class RegionRuntimeState:
    states: set[ButtonState] = field(default_factory=set)
    ripple: RippleEffect | None = None
    scroll_range: tuple[int, int] | None = None
    scroll_value: int | None = None


class ButtonController:
    def __init__(self, button, spec: ButtonSpec | None = None) -> None:
        self.button = button
        self.spec = spec or ButtonSpec(regions=())
        self.regions: list[ButtonRegion] = []
        self.region_specs: dict[str, RegionSpec] = {}
        self.split: SplitLayout = SingleRegionSplit()
        self.divider: Divider | None = None
        self.rects: dict[str, QRectF] = {}
        self.paths: dict[str, QPainterPath] = {}
        self.runtime: dict[str, RegionRuntimeState] = {}

    def set_spec(self, spec: ButtonSpec) -> None:
        self.spec = spec
        self.regions = spec.to_regions() or [ButtonRegion(id="_main")]
        self.region_specs = {region.id: region for region in spec.regions}
        self.split = spec.split or SingleRegionSplit()
        self.divider = spec.divider
        seen = {region.id for region in self.regions}

        for region in self.regions:
            runtime = self.runtime.setdefault(region.id, RegionRuntimeState())
            if runtime.ripple is None:
                runtime.ripple = RippleEffect(self.button)
            if region.enabled:
                runtime.states.discard(ButtonState.DISABLED)
            else:
                runtime.states.add(ButtonState.DISABLED)

            scroll_behavior = self._scroll_behavior(region.id)
            if scroll_behavior is not None:
                min_v = int(scroll_behavior.min_value)
                max_v = int(scroll_behavior.max_value)
                runtime.scroll_range = (min_v, max_v)
                if runtime.scroll_value is None:
                    runtime.scroll_value = max(min_v, min(max_v, max(min_v, 1)))
                else:
                    runtime.scroll_value = max(min_v, min(max_v, runtime.scroll_value))
            else:
                runtime.scroll_range = None
                runtime.scroll_value = None

        for region_id in list(self.runtime):
            if region_id not in seen:
                del self.runtime[region_id]
        self.recompute_rects()

    def set_regions(
        self,
        regions: list[ButtonRegion],
        *,
        split: SplitLayout | None = None,
        divider: Divider | None = None,
        shape: ShapeSpec | None = None,
        variant: str = "default",
        density: str = "normal",
        defer_click: bool = False,
        wheel_requires_focus: bool = False,
    ) -> None:
        self.set_spec(
            ButtonSpec.from_regions(
                regions,
                split=split,
                divider=divider,
                shape=shape,
                variant=variant,
                density=density,
                defer_click=defer_click,
                wheel_requires_focus=wheel_requires_focus,
            )
        )

    def recompute_rects(self) -> None:
        rect = QRectF(self.button.rect())
        rects = self.split.compute(rect, self.regions)
        self.rects = {
            region.id: QRectF(region.rect_fn(rect) if region.rect_fn else region_rect)
            for region, region_rect in zip(self.regions, rects)
        }
        paths: dict[str, QPainterPath] = {}
        for region in self.regions:
            region_rect = self.rects.get(region.id)
            if region_rect is None:
                continue
            if region.path_fn is not None:
                paths[region.id] = QPainterPath(region.path_fn(rect))
            else:
                path = QPainterPath()
                path.addRect(region_rect)
                paths[region.id] = path
        self.paths = paths

    def region_at(self, pos) -> str | None:
        point = QPointF(pos.toPoint() if hasattr(pos, "toPoint") else pos)
        if not QRectF(self.button.rect()).contains(point):
            return None
        if not self.rects:
            self.recompute_rects()
        ordered = sorted(
            enumerate(self.regions),
            key=lambda item: (item[1].z_index, item[0]),
            reverse=True,
        )
        for _index, region in ordered:
            path = self.paths.get(region.id)
            if path is None or not path.contains(point):
                continue
            if ButtonState.DISABLED in self.states(region.id):
                return None
            return region.id
        return None

    def states(self, region_id: str) -> set[ButtonState]:
        return self.runtime.setdefault(region_id, RegionRuntimeState()).states

    def set_state(self, region_id: str | None, state: ButtonState, active: bool) -> None:
        if region_id is None:
            return
        states = self.states(region_id)
        if active:
            states.add(state)
        else:
            states.discard(state)

    def ripple(self, region_id: str) -> RippleEffect | None:
        runtime = self.runtime.get(region_id)
        return runtime.ripple if runtime else None

    def scroll_range(self, region_id: str) -> tuple[int, int] | None:
        runtime = self.runtime.get(region_id)
        return runtime.scroll_range if runtime else None

    def scroll_value(self, region_id: str) -> int | None:
        runtime = self.runtime.get(region_id)
        return runtime.scroll_value if runtime else None

    def set_scroll_value(self, region_id: str, value: int) -> None:
        runtime = self.runtime.setdefault(region_id, RegionRuntimeState())
        if runtime.scroll_range is None:
            runtime.scroll_value = value
            return
        min_v, max_v = runtime.scroll_range
        runtime.scroll_value = max(min_v, min(max_v, int(value)))

    def behaviors(self, region_id: str, kind: str | None = None) -> tuple[BehaviorSpec, ...]:
        spec = self.region_specs.get(region_id)
        if spec is None:
            return ()
        if kind is None:
            return spec.behaviors
        return tuple(behavior for behavior in spec.behaviors if behavior.kind == kind)

    def _scroll_behavior(self, region_id: str) -> ScrollBehavior | None:
        spec = self.region_specs.get(region_id)
        if spec is None:
            return None
        for behavior in spec.behaviors:
            if isinstance(behavior, ScrollBehavior):
                return behavior
        return None
