"""Copy-as-Markdown: map a document selection back to its source slice.

The text index flattens a page to a plain stream (markers like ``-``/``##``/
``**`` are syntax, not text), so a plain substring search against the source
cannot locate a multi-block or formatted selection — the old fallback
returned the WHOLE page, which is what the user saw when selecting two list
labels. Parsed blocks instead carry source geometry (``SegmentSource``), and
this module maps index offsets through it:

* a part selected whole emits its ``emit`` range (heading line without its
  invisible ``{#anchor}``, list item line with its marker, whole code/figure
  fence, cell text);
* a partially selected part is sliced per character, and an inline span that
  is selected whole contributes its delimiters too — so a partial selection
  never emits half a ``**``;
* parts are joined with the real source text between them (``\\n`` between
  list items, ``\\n\\n`` between blocks, `` | `` between table cells), so a
  two-label selection copies exactly those two labels' markdown;
* a part without geometry (a host-built block) contributes its plain text —
  the selection is never widened to the page.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.text.engine.markdown import (
    SegmentSource,
    SourceRange,
)
from sli_ui_toolkit.ui.widgets.text.engine.text_index import (
    DocumentTextIndex,
    TextSegment,
)


def _normalize(markdown: str) -> str:
    # Mirrors ``parse_help_blocks``: offsets are recorded against the
    # newline-normalised source, so the slice must run on the same string.
    return markdown.replace("\r\n", "\n").replace("\r", "\n")


def _source_usable(
    segment: TextSegment,
    source: SegmentSource | None,
    source_length: int,
) -> bool:
    if source is None:
        return False
    if len(source.chars) != segment.end - segment.start:
        return False
    if source.part.start < 0 or source.part.end > source_length:
        return False
    if source.emit.start < 0 or source.emit.end > source_length:
        return False
    return all(0 <= offset < source_length for offset in source.chars)


def _slice_runs(
    chars: tuple[int, ...],
    start: int,
    end: int,
    markdown: str,
) -> str:
    """Slice ``[start, end)`` of the part, one source run per contiguous span.

    A run breaks where the source carries markup the selection cuts through;
    concatenating the runs (without the markup between them) keeps the copy
    valid markdown instead of emitting a dangling delimiter.
    """
    pieces: list[str] = []
    run_start = chars[start]
    previous = run_start
    for index in range(start + 1, end):
        offset = chars[index]
        if offset != previous + 1:
            pieces.append(markdown[run_start : previous + 1])
            run_start = offset
        previous = offset
    pieces.append(markdown[run_start : previous + 1])
    return "".join(pieces)


def _partial_text(
    source: SegmentSource,
    markdown: str,
    start: int,
    end: int,
) -> str:
    """Markdown for a *part* of one segment (offsets relative to the part)."""
    pieces: list[str] = []
    position = start
    for span in source.spans:
        if span.plain_end <= start or span.plain_start >= end:
            continue
        if span.plain_start > position:
            pieces.append(
                _slice_runs(source.chars, position, span.plain_start, markdown)
            )
        span_start = max(position, span.plain_start)
        span_end = min(end, span.plain_end)
        if span_start < span_end:
            if span_start == span.plain_start and span_end == span.plain_end:
                pieces.append(markdown[span.full.start : span.full.end])
            else:
                pieces.append(_slice_runs(source.chars, span_start, span_end, markdown))
        position = max(position, span.plain_end)
    if position < end:
        pieces.append(_slice_runs(source.chars, position, end, markdown))
    return "".join(pieces)


def markdown_for_range(
    index: DocumentTextIndex,
    markdown: str,
    start: int,
    end: int,
) -> str:
    """The source-markdown slice covering ``[start, end)`` of the plain index."""
    text = index.text
    lo = max(0, min(start, len(text)))
    hi = max(lo, min(end, len(text)))
    if lo == hi:
        return ""
    source_markdown = _normalize(markdown)
    pieces: list[tuple[str, TextSegment | None]] = []
    first_part: SourceRange | None = None
    last_part: SourceRange | None = None
    for segment in index.segments:
        if segment.end <= lo or segment.start >= hi:
            continue
        seg_lo = max(lo, segment.start)
        seg_hi = min(hi, segment.end)
        if seg_hi <= seg_lo:
            continue
        source = segment.source
        if source is not None and _source_usable(
            segment, source, len(source_markdown)
        ):
            if first_part is None:
                first_part = source.part
            last_part = source.part
            if seg_lo == segment.start and seg_hi == segment.end:
                pieces.append(
                    (source_markdown[source.emit.start : source.emit.end], segment)
                )
            else:
                pieces.append(
                    (
                        _partial_text(
                            source,
                            source_markdown,
                            seg_lo - segment.start,
                            seg_hi - segment.start,
                        ),
                        segment,
                    )
                )
        else:
            pieces.append((text[seg_lo:seg_hi], None))

    if not pieces:
        return text[lo:hi]
    out: list[str] = []
    if lo == 0 and first_part is not None and first_part.start > 0:
        lead = source_markdown[: first_part.start]
        if not lead.strip():
            out.append(lead)
    out.append(pieces[0][0])
    previous: TextSegment | None = pieces[0][1]
    for piece, next_segment in pieces[1:]:
        gap = "\n\n"
        if previous is not None and next_segment is not None:
            previous_source = previous.source
            current_source = next_segment.source
            if (
                previous_source is not None
                and current_source is not None
                and previous_source.part.end <= current_source.part.start
            ):
                gap = source_markdown[
                    previous_source.part.end : current_source.part.start
                ]
        out.append(gap)
        out.append(piece)
        previous = next_segment
    if hi == len(text) and last_part is not None and last_part.end < len(source_markdown):
        tail = source_markdown[last_part.end :]
        if not tail.strip():
            out.append(tail)
    return "".join(out)
