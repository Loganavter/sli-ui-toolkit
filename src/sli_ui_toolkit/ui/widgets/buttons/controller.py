"""Button control controller.

The controller owns runtime state and geometry for a declarative ``ButtonSpec``.
``Button`` keeps compatibility aliases while delegating region runtime concerns
here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath

from .layers.ripple import RippleEffect
from .regions import ButtonRegion, Divider, SingleRegionSplit, SplitLayout
from .specs import BehaviorSpec, ButtonSpec, ShapeSpec, region_behaviors
from .state import ButtonState


@dataclass
class RegionRuntimeState:
    states: set[ButtonState] = field(default_factory=set)
    ripple: RippleEffect | None = None


class ButtonController:
    def __init__(self, button, spec: ButtonSpec | None = None) -> None:
        self.button = button
        self.spec = spec or ButtonSpec(regions=())
        self.regions: list[ButtonRegion] = []
        self.split: SplitLayout = SingleRegionSplit()
        self.divider: Divider | None = None
        self.rects: dict[str, QRectF] = {}
        self.paths: dict[str, QPainterPath] = {}
        self.fill_paths: dict[str, QPainterPath] = {}
        self.group_rects: dict[str, QRectF] = {}
        self.runtime: dict[str, RegionRuntimeState] = {}

    def set_spec(self, spec: ButtonSpec) -> None:
        self.spec = spec
        self.regions = spec.to_regions() or [ButtonRegion(id="_main")]
        self.split = spec.split or SingleRegionSplit()
        self.divider = spec.divider
        seen = {region.id for region in self.regions}

        group_ripples: dict[str, RippleEffect] = {}
        for region in self.regions:
            runtime = self.runtime.setdefault(region.id, RegionRuntimeState())
            if region.group:
                shared = group_ripples.get(region.group)
                if shared is None:
                    shared = runtime.ripple or RippleEffect(self.button)
                    group_ripples[region.group] = shared
                runtime.ripple = shared
            elif runtime.ripple is None:
                runtime.ripple = RippleEffect(self.button)
            if region.enabled:
                runtime.states.discard(ButtonState.DISABLED)
            else:
                runtime.states.add(ButtonState.DISABLED)

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
        fill_paths: dict[str, QPainterPath] = {}
        for region in self.regions:
            region_rect = self.rects.get(region.id)
            if region_rect is None:
                continue
            if region.path_fn is not None:
                path = QPainterPath(region.path_fn(rect))
                paths[region.id] = path
                fill_paths[region.id] = path
            else:
                path = QPainterPath()
                path.addRect(region_rect)
                paths[region.id] = path
                if region.group is not None and region.corner_radii is None:
                    # Hit-testing (region_at, above) must stay on the exact
                    # nominal rect. Painting a same-group capsule fill from
                    # that same rect can leave a hairline antialiased seam
                    # against the neighboring region when the split boundary
                    # isn't pixel-aligned (routine with 3+ fractional
                    # weights). Give the *fill* path alone a hairline
                    # overlap; the outer capsule clip in BackgroundLayer
                    # still trims it back at the button's true edges, so
                    # only the inner region-to-region seam is affected.
                    fill_path = QPainterPath()
                    fill_path.addRect(region_rect.adjusted(-0.75, -0.75, 0.75, 0.75))
                    fill_paths[region.id] = fill_path
                else:
                    fill_paths[region.id] = path
        self.paths = paths
        self.fill_paths = fill_paths

        group_rects: dict[str, QRectF] = {}
        for region in self.regions:
            if not region.group:
                continue
            region_rect = self.rects.get(region.id)
            if region_rect is None:
                continue
            if region.group in group_rects:
                group_rects[region.group] = group_rects[region.group].united(region_rect)
            else:
                group_rects[region.group] = QRectF(region_rect)
        self.group_rects = group_rects

    def ripple_rect(self, region_id: str) -> QRectF | None:
        region = next((r for r in self.regions if r.id == region_id), None)
        if region is None:
            return self.rects.get(region_id)
        if region.group:
            return self.group_rects.get(region.group, self.rects.get(region_id))
        return self.rects.get(region_id)

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

    def behaviors(self, region_id: str, kind: str | None = None) -> tuple[BehaviorSpec, ...]:
        region = next((r for r in self.regions if r.id == region_id), None)
        if region is None:
            return ()
        return region_behaviors(region, kind)
