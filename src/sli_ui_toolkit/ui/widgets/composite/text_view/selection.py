"""Unified text-selection state shared by every painted text surface.

One state machine serves both coordinate spaces of the text view:

- **Code mode** anchors ``(line, col)`` positions (``TextSelection``): a
  double-click selects the word, a triple-click the whole line, drags
  extend, Ctrl+A/C select/copy.
- **Document mode** anchors flat text-index offsets (``DocumentSelection``):
  a double-click selects the word, a triple-click the whole segment
  (paragraph/heading/item), drags extend word- or segment-wise, Ctrl+A/C
  select/copy.

``SelectionState`` owns the anchor/focus pair, the multi-click chain counter
(time + distance), the drag threshold, select-all and range normalization;
the subclasses bind it to a coordinate space and resolve the click modes.
The same machinery backs the help-document canvas
(``help_document/canvas.py``), so the inspector's Docs and Code sections and
the Help pages all select text the same way.
"""

from __future__ import annotations

import time
from typing import Any, Generic, TypeVar

from sli_ui_toolkit.ui.widgets.composite.text_view.text_index import (
    DocumentTextIndex,
    segment_bounds_at_offset,
    word_bounds_at_offset,
)

Coord = TypeVar("Coord")

#: Distance a press must travel (widget px) before it becomes a drag-select.
DRAG_THRESHOLD_PX = 4
#: Triple-click window floor: the third press arrives after the user has
#: already seen the word selection — give it more slack than the OS.
MULTI_CLICK_INTERVAL_MIN_MS = 900
MULTI_CLICK_INTERVAL_SCALE = 2.5
MULTI_CLICK_DISTANCE_SCALE = 2


def _multi_click_interval_ms() -> int:
    """OS-derived triple-click window (style hints, scaled for the chain)."""
    from PySide6.QtWidgets import QApplication

    hints = QApplication.styleHints()
    return max(
        MULTI_CLICK_INTERVAL_MIN_MS,
        int(hints.mouseDoubleClickInterval() * MULTI_CLICK_INTERVAL_SCALE),
    )


def _multi_click_distance() -> int:
    from PySide6.QtWidgets import QApplication

    hints = QApplication.styleHints()
    return max(1, int(hints.mouseDoubleClickDistance() * MULTI_CLICK_DISTANCE_SCALE))


class SelectionState(Generic[Coord]):
    """Shared selection core: anchor/focus pair + multi-click chain + drag.

    Coordinate-agnostic — subclasses bind it to ``(line, col)`` positions
    (code mode) or flat text-index offsets (document mode). ``range()``
    returns the normalized ``(lo, hi)`` pair; ``select_all`` / ``clear`` /
    ``set_range`` work on the raw coords.
    """

    DRAG_THRESHOLD_PX = DRAG_THRESHOLD_PX

    def __init__(
        self,
        *,
        multi_click_interval_ms: int | None = None,
        multi_click_distance: int | None = None,
    ) -> None:
        self.anchor: Coord | None = None
        self.focus: Coord | None = None
        #: widget-space point of the last press (drag threshold anchor)
        self.press_point: Any = None
        self.dragged = False
        #: press count in the current multi-click chain (1..3, 4 restarts)
        self.click_count = 0
        self._last_point: Any = None
        self._last_time = 0.0
        interval = (
            _multi_click_interval_ms()
            if multi_click_interval_ms is None
            else multi_click_interval_ms
        )
        distance = (
            _multi_click_distance()
            if multi_click_distance is None
            else multi_click_distance
        )
        self._interval_s = max(0.05, interval) / 1000.0
        self._distance = max(1, distance)

    # -- state --------------------------------------------------------------

    def clear(self) -> None:
        self.anchor = None
        self.focus = None

    def active(self) -> bool:
        return self.anchor is not None and self.anchor != self.focus

    def range(self) -> tuple[Coord, Coord] | None:
        """Normalized ``(lo, hi)`` or None when empty/absent."""
        if self.anchor is None or self.focus is None or self.anchor == self.focus:
            return None
        return tuple(  # type: ignore[return-value]
            sorted(  # type: ignore[type-var]
                (self.anchor, self.focus)
            )
        )

    def set_range(self, lo: Coord, hi: Coord) -> None:
        self.anchor = lo
        self.focus = hi

    def select_all_range(self, lo: Coord, hi: Coord) -> None:
        """Select the whole buffer: ``lo`` is the first, ``hi`` the last coord."""
        self.anchor = lo
        self.focus = hi

    # -- multi-click chain --------------------------------------------------

    def press_chain(self, point, now: float | None = None) -> int:
        """Count a press; returns the click count (1, 2, 3, …).

        Clicks within the interval and distance of the previous press count
        as a chain: 2 = word selection, 3 = whole line/segment. A fourth
        rapid click starts a NEW chain (count resets to 1) — otherwise the
        counter would keep climbing and every subsequent click would stay
        in whole-line mode forever.
        """
        now = now if now is not None else time.monotonic()
        if self._same_spot(point) and now - self._last_time <= self._interval_s:
            self.click_count += 1
            if self.click_count > 3:
                self.click_count = 1
        else:
            self.click_count = 1
        self._last_point = point
        self._last_time = now
        return self.click_count

    def _same_spot(self, point) -> bool:
        """Whether ``point`` sits within the chain distance of the previous
        press. Default: per-axis distance (``(line, col)`` tuples)."""
        if self._last_point is None:
            return False
        return (
            abs(point[0] - self._last_point[0]) <= self._distance
            and abs(point[1] - self._last_point[1]) <= self._distance
        )

    # -- drag ---------------------------------------------------------------

    def should_drag(self, point) -> bool:
        """Whether a move from the press point crossed the drag threshold."""
        if self.press_point is None:
            return False
        return (point - self.press_point).manhattanLength() >= self.DRAG_THRESHOLD_PX

    def end_gesture(self) -> None:
        """Release: the press gesture ends; the painted selection stays."""
        self.press_point = None
        self.dragged = False


Position = tuple[int, int]


class TextSelection(SelectionState[Position]):
    """Code-mode selection: ``(line, col)`` anchor/focus over a line buffer.

    A double-click selects the word, a triple-click the whole line, drags
    extend; Ctrl+A/C select/copy. The chain's same-spot test runs in
    ``(line, col)`` space (per-axis distance).
    """

    def press(
        self,
        pos: Position,
        point=None,
        now: float | None = None,
    ) -> int:
        """Record a press; returns the click count (1, 2, 3, …).

        ``point`` is the widget-space press position — the chain's
        same-spot test then runs in PIXELS (Qt's double-click distance),
        so clicks on different lines never chain into a double-click.
        Without a point (legacy callers) the test falls back to per-axis
        distance in ``(line, col)`` space.
        """
        spot = point if point is not None else pos
        return self.press_chain(spot, now=now)

    def text_of(self, lines: list[str]) -> str | None:
        """The selected plain text across the buffer, or None."""
        rng = self.range()
        if rng is None:
            return None
        (lo_line, lo_col), (hi_line, hi_col) = rng
        if lo_line == hi_line:
            return lines[lo_line][lo_col:hi_col]
        parts = [lines[lo_line][lo_col:]]
        parts.extend(lines[lo_line + 1:hi_line])
        parts.append(lines[hi_line][:hi_col])
        return "\n".join(parts)

    def select_all(self, lines: list[str]) -> None:
        if not lines:
            self.clear()
            return
        self.select_all_range((0, 0), (len(lines) - 1, len(lines[-1])))

    # -- range helpers ------------------------------------------------------

    @staticmethod
    def word_range(pos: Position, line: str) -> tuple[Position, Position]:
        """The identifier word under ``pos`` (fallback: the single char)."""
        line_index, col = pos
        start = end = col
        while start > 0 and line[start - 1] in _WORD_CHARS:
            start -= 1
        while end < len(line) and line[end] in _WORD_CHARS:
            end += 1
        if start == end and end < len(line):
            end += 1  # non-word char → select it alone
        return ((line_index, start), (line_index, end))

    @staticmethod
    def line_range(pos: Position, line: str) -> tuple[Position, Position]:
        return ((pos[0], 0), (pos[0], len(line)))


_WORD_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)


class DocumentSelection(SelectionState[int]):
    """Document-mode selection: flat text-index offsets, same chain as code.

    Double-click selects the word, triple-click the whole segment
    (paragraph/heading/item), drags extend word-/segment-wise. ``index`` is
    the live ``DocumentTextIndex`` the canvas attaches when a document
    loads — the bounds resolution and the word/paragraph extension math
    live here, so code and document modes share one selection state
    machine.
    """

    def __init__(
        self,
        *,
        index: DocumentTextIndex | None = None,
        multi_click_interval_ms: int | None = None,
        multi_click_distance: int | None = None,
    ) -> None:
        super().__init__(
            multi_click_interval_ms=multi_click_interval_ms,
            multi_click_distance=multi_click_distance,
        )
        self.index = index
        #: (anchor, focus) pair in document offsets — kept for callers that
        #: read the raw pair (paint/copy use ``range()``).
        self.selection: tuple[int, int] | None = None
        self.press_offset: int | None = None
        #: armed multi-click mode: ``None`` | ``"word"`` | ``"paragraph"``
        self._mode: str | None = None
        self._mode_anchor: tuple[int, int] | None = None

    def _same_spot(self, point) -> bool:
        """Chain distance in widget-pixel space (QPoint/QPointF)."""
        if self._last_point is None:
            return False
        return (point - self._last_point).manhattanLength() <= self._distance

    # -- press --------------------------------------------------------------

    def press(self, offset: int | None, point) -> None:
        """Anchor the selection at ``offset``; ``point`` drives the
        multi-click chain (double-click = word, triple-click = segment)."""
        count = self.press_chain(point)
        self.press_offset = offset
        self.press_point = point
        self.dragged = False
        self._mode = None
        self._mode_anchor = None
        if offset is None:
            self.anchor = None
            self.focus = None
            self.selection = None
            return
        if count >= 3:
            bounds = self._segment_bounds(offset)
            if bounds is not None and bounds[0] != bounds[1]:
                self._arm("paragraph", bounds)
                return
        if count >= 2:
            bounds = self._word_bounds(offset)
            if bounds is not None and bounds[0] != bounds[1]:
                self._arm("word", bounds)
                return
        self.anchor = offset
        self.focus = offset
        self.selection = (offset, offset)

    def arm(self, mode: str, bounds: tuple[int, int]) -> None:
        """Arm ``word``/``paragraph`` extension mode and select ``bounds``."""
        self._arm(mode, bounds)

    def _arm(self, mode: str, bounds: tuple[int, int]) -> None:
        self._mode = mode
        self._mode_anchor = bounds
        self.anchor, self.focus = bounds
        self.selection = bounds

    # -- extend -------------------------------------------------------------

    def extend(self, offset: int) -> None:
        """Extend toward ``offset`` — word-/segment-wise while a multi-click
        mode is armed, plain otherwise."""
        if self.anchor is None:
            return
        if self._mode == "word":
            self.extend_word(offset)
        elif self._mode == "paragraph":
            self.extend_paragraph(offset)
        else:
            self.focus = offset
            self.selection = (self.anchor, offset)

    def extend_word(self, offset: int) -> None:
        if self._mode_anchor is None or self.index is None:
            return
        self._set_pair(
            extend_word_range(offset, self._mode_anchor, self.index.text)
        )

    def extend_paragraph(self, offset: int) -> None:
        if self._mode_anchor is None:
            return
        self._set_pair(
            extend_segment_range(offset, self._mode_anchor, self.index)
        )

    def _set_pair(self, pair: tuple[int, int]) -> None:
        self.anchor, self.focus = pair
        self.selection = pair

    def _word_bounds(self, offset: int) -> tuple[int, int] | None:
        if self.index is None:
            return None
        return word_bounds_at_offset(self.index.text, offset)

    def _segment_bounds(self, offset: int) -> tuple[int, int] | None:
        if self.index is None:
            return None
        return segment_bounds_at_offset(self.index, offset)

    # -- select-all / copy / reset ------------------------------------------

    def select_all(self, length: int) -> None:
        self.select_all_range(0, length)
        self.selection = (0, length)

    def copy_range(self) -> tuple[int, int] | None:
        """The sorted ``(lo, hi)`` range to copy, or None when empty."""
        return self.range()

    def paint_range(self) -> tuple[int, int] | None:
        return self.range()

    def reset(self) -> None:
        self.clear()
        self.end_gesture()
        self.selection = None
        self.press_offset = None
        self._mode = None
        self._mode_anchor = None


def extend_word_range(
    offset: int, anchor: tuple[int, int], text: str
) -> tuple[int, int]:
    """Grow a double-click word selection word-by-word toward ``offset``."""
    wa, wb = anchor
    bounds = word_bounds_at_offset(text, offset)
    if bounds is None:
        return wa, wb
    ca, cb = bounds
    if ca == cb:
        # Between words / punctuation: still extend toward the caret.
        if offset >= wb:
            return wa, max(wb, offset)
        if offset < wa:
            return wb, min(wa, offset)
        return wa, wb
    if ca >= wa:
        return wa, max(wb, cb)
    return wb, min(wa, ca)


def extend_segment_range(
    offset: int,
    anchor: tuple[int, int],
    index: DocumentTextIndex | None,
) -> tuple[int, int]:
    """Grow a triple-click paragraph/segment selection segment-wise."""
    pa, pb = anchor
    bounds = segment_bounds_at_offset(index, offset) if index is not None else None
    if bounds is None:
        return pa, pb
    ca, cb = bounds
    if ca >= pa:
        return pa, max(pb, cb)
    return pb, min(pa, ca)
