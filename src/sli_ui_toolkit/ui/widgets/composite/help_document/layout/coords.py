"""Coordinate mapping between text-index offsets and QTextLayout fragments."""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.help_document.layout.types import TextFragment


def normalized_range(
    start: int | None,
    end: int | None,
) -> tuple[int | None, int | None]:
    if start is None or end is None:
        return None, None
    if start == end:
        return start, end
    if start <= end:
        return start, end
    return end, start


def fragment_index_to_layout(frag: TextFragment, index_pos: int) -> int:
    """Map a text-index offset inside *frag* to QTextLayout character coordinates."""
    layout_len = len(frag.layout.text())
    index_len = frag.global_end - frag.global_start
    if index_len <= 0 or layout_len <= 0:
        return 0
    local = max(0, min(index_pos - frag.global_start, index_len))
    if index_len == layout_len:
        return local
    return min(layout_len, int(local * layout_len / index_len))


def fragment_layout_to_index(frag: TextFragment, layout_pos: int) -> int:
    """Map a QTextLayout character coordinate back to the text-index stream."""
    layout_len = len(frag.layout.text())
    index_len = frag.global_end - frag.global_start
    if layout_len <= 0 or index_len <= 0:
        return frag.global_start
    local = max(0, min(layout_pos, layout_len))
    if index_len == layout_len:
        return frag.global_start + local
    return frag.global_start + int(local * index_len / layout_len)


def line_for_y(layout, y: float):
    """Return the ``QTextLine`` whose vertical span contains layout-local *y*."""
    last: object = None
    for index in range(layout.lineCount()):
        line = layout.lineAt(index)
        if not line.isValid():
            continue
        last = line
        if y < line.y() + line.height():
            return line
    return last
