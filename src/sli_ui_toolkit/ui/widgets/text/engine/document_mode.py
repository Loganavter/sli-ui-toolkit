"""Document-mode selection state for TextCanvas — owns its own state.

When the canvas shows a parsed help document (read-only), text selection
works on the *document index* offsets: press anchors, drag extends past a
small threshold, release clicks resolve links/images. ``DocumentSelection``
owns all of that interaction state and the pure decisions (threshold,
select-all, copy range); the canvas only delegates and repaints.
"""

from __future__ import annotations

from typing import Any


class DocumentSelection:
    """Selection + press/drag state for read-only document mode.

    No widget dependencies: ``press``/``extend``/``select_all`` work on
    document-index offsets, ``should_drag`` is the manhattan threshold,
    and ``copy_range`` yields the sorted (lo, hi) pair to copy.
    """

    DRAG_THRESHOLD_PX = 4

    def __init__(self) -> None:
        self.selection: tuple[int, int] | None = None
        self.press_offset: int | None = None
        self.press_point: Any = None
        self.dragged: bool = False

    def press(self, offset: int | None) -> None:
        """Anchor the selection at ``offset`` (``None`` = press on empty)."""
        self.selection = (offset, offset) if offset is not None else None
        self.press_offset = offset
        self.press_point = None
        self.dragged = False

    def anchor_point(self, point) -> None:
        self.press_point = point

    def should_drag(self, point) -> bool:
        """Whether a move from the anchor has crossed the drag threshold."""
        if self.press_point is None:
            return False
        return (point - self.press_point).manhattanLength() >= self.DRAG_THRESHOLD_PX

    def extend(self, offset: int) -> None:
        if self.selection is not None:
            self.selection = (self.selection[0], offset)

    def select_all(self, length: int) -> None:
        self.selection = (0, length)

    def copy_range(self) -> tuple[int, int] | None:
        if self.selection is None or self.selection[0] == self.selection[1]:
            return None
        return tuple(sorted(self.selection))  # type: ignore[return-value]

    def paint_range(self) -> tuple[int, int] | None:
        if self.selection is None or self.selection[0] == self.selection[1]:
            return None
        return tuple(sorted(self.selection))  # type: ignore[return-value]

    def reset(self) -> None:
        self.selection = None
        self.press_offset = None
        self.press_point = None
        self.dragged = False
