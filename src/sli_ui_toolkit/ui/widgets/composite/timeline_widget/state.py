from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TimelineViewportState:
    """Immutable snapshot of timeline viewport geometry and zoom.

    Single source of truth for ``_commitState`` diffing — zoom with eps,
    geometry via ``==`` for px values. Mirrors the plan's
    ``zoom/min_zoom/left_gutter/content_width/viewport_width/scroll_x``
    slots.
    """

    zoom: float
    min_zoom: float
    left_gutter: int
    content_width: int
    viewport_width: int
    scroll_x: int

    def is_fitted(self, eps: float = 0.05) -> bool:
        return math.isclose(self.zoom, self.min_zoom, rel_tol=eps) or self.zoom < self.min_zoom

    def has_zoom_changed(self, other: TimelineViewportState | None, eps: float = 1e-4) -> bool:
        if other is None:
            return True
        return abs(self.zoom - other.zoom) > eps

    def has_geometry_changed(self, other: TimelineViewportState | None) -> bool:
        if other is None:
            return True
        return (
            self.left_gutter != other.left_gutter
            or self.content_width != other.content_width
            or self.viewport_width != other.viewport_width
            or self.scroll_x != other.scroll_x
        )
