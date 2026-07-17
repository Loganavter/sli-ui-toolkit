"""Map text-index segments to layout builder lookups."""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.help_document.text_index import (
    DocumentTextIndex,
    TextSegment,
)


def build_segment_map(
    text_index: DocumentTextIndex,
) -> dict[tuple[int, int | None, bool], TextSegment]:
    out: dict[tuple[int, int | None, bool], TextSegment] = {}
    for segment in text_index.segments:
        key = (segment.block_index, segment.list_item_index, segment.caption)
        out[key] = segment
    return out
