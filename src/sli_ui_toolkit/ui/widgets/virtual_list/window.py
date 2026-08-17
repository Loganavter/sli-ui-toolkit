"""Pure math for virtual list scrolling.

Separated from the widget layer so the window/scrollbar arithmetic can be
unit-tested without a QApplication and reused by any host (ComboBox dropdown,
ListPanel, IconListWidget, palette dialogs, ...).

Two height models:

- fixed row height (the common case: ComboBox, ListPanel, IconListWidget) —
  O(1) window computation;
- variable row heights — heights are measured lazily and cached in
  :class:`MeasuredHeights` with prefix sums for O(log n) offset<->index
  mapping.
"""

from __future__ import annotations

import bisect
import math


def max_scroll_px(count: int, viewport_height: int, row_height: int) -> int:
    """Max scroll offset in px for fixed-height rows (0 when nothing scrolls)."""
    return max(0, count * row_height - viewport_height)


def visible_window(
    count: int,
    viewport_height: int,
    row_height: int,
    scroll_px: int,
    overscan: int = 0,
) -> tuple[int, int]:
    """Half-open item window [start, end) to materialize for fixed heights.

    ``scroll_px`` is clamped to the valid range; ``overscan`` adds extra rows
    on both sides of the viewport (rendering headroom for smooth scrolling).
    """
    if count <= 0 or row_height <= 0 or viewport_height <= 0:
        return (0, 0)
    max_scroll = max_scroll_px(count, viewport_height, row_height)
    scroll_px = max(0, min(scroll_px, max_scroll))
    first = int(scroll_px // row_height)
    visible = math.ceil(viewport_height / row_height)
    start = max(0, first - overscan)
    end = min(count, first + visible + overscan)
    return (start, end)


class MeasuredHeights:
    """Lazily cached variable row heights with prefix sums.

    Hosts report a height for an index once (``set_height``); the cache grows
    on demand up to the item count and stores prefix sums so both
    ``offset_of_index`` and ``index_at_offset`` are O(log n).
    """

    def __init__(self) -> None:
        self._heights: list[int] = []
        self._prefix: list[int] = [0]
        self._count = 0

    def set_count(self, count: int) -> None:
        count = max(0, int(count))
        if count < self._count:
            del self._heights[count:]
            del self._prefix[count + 1:]
        self._count = count
        self._prefix = [0]
        for h in self._heights:
            self._prefix.append(self._prefix[-1] + h)

    def set_height(self, index: int, height: int) -> None:
        if not (0 <= index < self._count):
            return
        h = max(0, int(height))
        delta = h - (self._heights[index] if index < len(self._heights) else 0)
        if delta == 0 and index < len(self._heights):
            return
        while len(self._heights) <= index:
            self._heights.append(0)
        self._heights[index] = h
        # Rebuild prefix from the changed index on (linear in changed tail).
        if index == 0:
            self._prefix = [0]
        else:
            del self._prefix[index + 1:]
        for i in range(index, self._count):
            self._prefix.append(self._prefix[-1] + (self._heights[i] if i < len(self._heights) else 0))

    def height(self, index: int) -> int:
        if 0 <= index < len(self._heights):
            return self._heights[index]
        return 0

    def total(self) -> int:
        return self._prefix[-1]

    def offset_of_index(self, index: int) -> int:
        index = max(0, min(index, self._count))
        return self._prefix[index]

    def index_at_offset(self, offset_px: int) -> int:
        """First index whose row start is at or after ``offset_px``."""
        return bisect.bisect_right(self._prefix, offset_px) - 1

    def max_scroll(self, viewport_height: int) -> int:
        return max(0, self.total() - viewport_height)

    def visible_window(
        self,
        viewport_height: int,
        scroll_px: int,
        overscan: int = 0,
    ) -> tuple[int, int]:
        if self._count <= 0 or viewport_height <= 0:
            return (0, 0)
        max_scroll = self.max_scroll(viewport_height)
        scroll_px = max(0, min(scroll_px, max_scroll))
        first = self.index_at_offset(scroll_px)
        # Walk forward from the first visible row until the accumulated height
        # covers the viewport, then pad with overscan rows on both sides.
        end = first
        acc = 0
        while end < self._count and acc < viewport_height:
            acc += self.height(end)
            end += 1
        start = max(0, first - overscan)
        end = min(self._count, end + overscan)
        return (start, max(start, end))