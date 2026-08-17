"""Marquee selection model for ListPanel — owns its own state.

``MarqueeSelectionModel`` is the selection index set plus the band-preview
logic; it has no widget dependencies (testable with a plain object). The
panel owns the gesture *widget* and the row visuals and only delegates
state decisions here. ``sync_row_visuals`` / ``indices_intersecting_rect``
are pure helpers the panel calls with explicit inputs.
"""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QRect


class MarqueeSelectionModel:
    """Owns the selected-index set and the marquee band semantics.

    ``additive`` (set at gesture start from the Ctrl/Meta modifiers)
    decides whether a band union-commits into the selection or replaces it;
    the same flag drives the preview.
    """

    def __init__(self) -> None:
        self._indices: set[int] = set()
        self.additive: bool = False

    def indices(self) -> set[int]:
        return set(self._indices)

    def toggle(self, index: int) -> None:
        if index in self._indices:
            self._indices.discard(index)
        else:
            self._indices.add(index)

    def clear(self) -> None:
        self._indices.clear()

    def set_indices(self, indices: Iterable[int]) -> None:
        self._indices = {int(i) for i in indices if isinstance(i, int) and i >= 0}

    def begin_band(self, additive: bool) -> None:
        """Start a marquee band: remembers the additive modifier. A
        non-additive band previews over a blank slate (the caller shows an
        empty preview first); the existing selection is only replaced at
        ``commit``."""
        self.additive = additive

    def preview(self, band: set[int]) -> set[int]:
        """The selection preview for a live band (not committed yet)."""
        return self._indices | band if self.additive else set(band)

    def commit(self, band: set[int]) -> None:
        """Commit a finished band into the selection."""
        if self.additive:
            self._indices |= band
        else:
            self._indices = set(band)

    def finish_empty(self) -> None:
        """A band that ended on empty space: additive keeps the selection
        intact; a non-additive band clears it (click on empty = deselect)."""
        if not self.additive:
            self._indices.clear()


def indices_intersecting_rect(
    rect: QRect, geometries: list[tuple[int, QRect]]
) -> set[int]:
    """Indices of rows whose geometry intersects ``rect``.

    ``geometries`` is ``(index, geometry)`` for every row widget; the
    caller reads them from the layout (pure geometry math, no widgets).
    """
    if rect.isEmpty():
        return set()
    return {index for index, geo in geometries if geo.intersects(rect)}


def sync_row_visuals(widgets, selected: set[int]) -> None:
    """Push the selection state onto row widgets.

    Rows expose the duck-typed protocol: ``set_selected(bool)`` when
    available, otherwise an ``is_selected`` attribute + repaint.
    """
    for widget in widgets:
        setter = getattr(widget, "set_selected", None)
        if callable(setter):
            setter(widget.index in selected)
        else:
            widget.is_selected = widget.index in selected
            widget.update()
