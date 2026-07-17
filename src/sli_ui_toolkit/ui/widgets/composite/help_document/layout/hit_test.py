"""Pointer hit-testing on laid-out help document body."""

from __future__ import annotations

from PySide6.QtCore import QPointF

from sli_ui_toolkit.ui.widgets.composite.help_document.layout.coords import (
    fragment_layout_to_index,
    line_for_y,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.types import LayoutResult


def hit_test_text_offset(
    layout: LayoutResult,
    pos: QPointF,
) -> int | None:
    for frag in layout.text_fragments:
        if not frag.rect.contains(pos):
            continue
        local = pos - frag.rect.topLeft()
        line = line_for_y(frag.layout, local.y())
        if line is None or not line.isValid():
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
