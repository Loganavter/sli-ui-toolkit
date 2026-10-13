"""Pointer hit-testing on laid-out help document body."""

from __future__ import annotations

from PySide6.QtCore import QPointF

from sli_ui_toolkit.ui.widgets.composite.text_view.layout.coords import (
    fragment_layout_to_index,
    line_for_y,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.types import LayoutResult


def hit_test_text_offset(
    layout: LayoutResult,
    pos: QPointF,
) -> int | None:
    """Offset of the glyph under *pos*, or None on empty space.

    The text zone is where glyphs stand — not the fragment's full block
    width: past the last glyph (whitespace counts by its advance width),
    on an empty line, or below the content is a miss. Both document
    viewers (help body, TextView document mode) share this, so hover
    cursor and click selection behave identically everywhere.
    """
    for frag in layout.text_fragments:
        if not frag.rect.contains(pos):
            continue
        local = pos - frag.rect.topLeft()
        line = line_for_y(frag.layout, local.y())
        if line is None or not line.isValid():
            continue
        try:
            line_len = int(line.textLength())
        except Exception:
            line_len = 1
        if line_len <= 0:
            continue
        try:
            span_top = float(line.y())
            span_h = float(line.height())
        except Exception:
            span_top, span_h = 0.0, 0.0
        if span_h > 0 and not (span_top <= local.y() < span_top + span_h):
            continue
        try:
            end_x = float(line.naturalTextWidth())
        except Exception:
            end_x = None
        if end_x is not None and local.x() > end_x:
            continue
        rel = line.xToCursor(local.x())
        if isinstance(rel, tuple):
            rel = rel[0]
        if rel < 0:
            continue
        offset = fragment_layout_to_index(frag, rel)
        return max(frag.global_start, min(offset, frag.global_end))
    return None


def hit_test_link(layout: LayoutResult, pos: QPointF) -> str | None:
    for frag in layout.text_fragments:
        if not frag.rect.contains(pos):
            continue
        local = pos - frag.rect.topLeft()
        for link in frag.links:
            if link.rect.contains(local):
                return link.href
    return None


def hit_test_pixmap(layout: LayoutResult, pos: QPointF) -> str | None:
    """Return the source asset path for a help figure under *pos*, if any."""
    for frag in reversed(layout.pixmaps):
        if frag.rect.contains(pos) and frag.source_path:
            return frag.source_path
    return None
