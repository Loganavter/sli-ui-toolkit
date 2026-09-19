from __future__ import annotations

import math
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class TimelineViewportState:
    """Immutable snapshot of timeline viewport geometry and zoom.

    Single source of truth for ``_commitState`` diffing — zoom with eps,
    geometry via ``==`` for px values. Mirrors the plan's
    ``zoom/min_zoom/left_gutter/content_width/viewport_width/scroll_x``
    slots.

    Zoom contract (Z1): ``zoom`` is the single zoom scalar; px/sec is
    derived as ``pps = zoom * base_pps`` (see ``viewport`` helpers — never
    stored here). ``zoom`` stays in ``[min_zoom, 1.0]``. Every zoom change
    (including coalesced Ctrl+wheel steps, sources ``"wheelZoom"`` for a
    lone tick / ``"wheelZoomCoalesced"`` for a coalesced window) commits
    through ``_commitState``, the only emit path for ``zoomChanged`` /
    ``viewportChanged`` / ``viewportChangedState``.
    """

    zoom: float
    min_zoom: float
    left_gutter: int
    content_width: int
    viewport_width: int
    scroll_x: int

    def is_fitted(self, eps: float = 0.05) -> bool:
        return math.isclose(self.zoom, self.min_zoom, rel_tol=eps) or self.zoom < self.min_zoom

    def with_zoom(self, zoom: float) -> TimelineViewportState:
        """Copy with a new zoom (geometry slots untouched).

        Single-source funnel for zoom mutations: callers build the next
        state via this helper and hand it to ``_commitState``, which owns
        the diff/emit decision — nobody writes ``widget._zoom_level``
        directly anymore.
        """
        return replace(self, zoom=float(zoom))

    def with_left_gutter(self, left_gutter: int) -> TimelineViewportState:
        """Copy with a new left gutter (zoom slots untouched).

        Single-source funnel for gutter-drag mutations (Phase 2B): the
        drag path builds the next state via this helper so the snapshot
        shape stays frozen; until the CUTOVER-C convert lands in
        ``interaction.mouse_move_event`` the state is applied through the
        silent ``_refresh_viewport_state`` path, and wave C swaps that
        call for ``_commitState(nxt, source="gutterDrag")``.
        """
        return replace(self, left_gutter=int(left_gutter))

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
