"""Caret geometry for the laid-out help document body.

`hit_test.py` maps a point to a text offset; this is the inverse, for the one thing document mode was missing: a visible
cursor. The document body is read-only, but a click still has to *show* where it landed - without a caret the only
feedback is a selection highlight, which appears after the drag threshold, so a plain click on a character looked like a
dead click (owner, 2026-11-22: "document mode has no caret").

The rect is in the canvas' own coordinates, the same space `paint_layout` draws the fragments in
(``frag.rect.topLeft()`` + the line's own offset inside the fragment).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF

from .coords import fragment_index_to_layout
from .types import LayoutResult

#: Width of the painted caret. 2 px so it survives a 1x display without looking like a hairline (Qt's own carets are 1
#: design px, which the toolkit's painter would draw at scale anyway).
CARET_WIDTH = 2.0


def caret_rect(layout: LayoutResult | None, offset: int | None) -> QRectF | None:
    """Rect of the text cursor at *offset*, or ``None`` when the offset is not inside a fragment."""
    if layout is None or offset is None:
        return None
    for frag in layout.text_fragments:
        if not (frag.global_start <= offset <= frag.global_end):
            continue
        layout_pos = fragment_index_to_layout(frag, offset)
        line = frag.layout.lineForTextPosition(layout_pos)
        if line is None or not line.isValid():
            continue
        x = line.cursorToX(layout_pos)
        if isinstance(x, tuple):  # bidi: (left, right) — the left edge is the caret
            x = x[0]
        return QRectF(
            frag.rect.left() + float(x),
            frag.rect.top() + float(line.y()),
            CARET_WIDTH,
            float(line.height()),
        )
    return None
