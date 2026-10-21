"""Controlled markdown subset → typed help document blocks.

Authoring contract (v2):

- ``#`` … ``######`` headings; optional ``{#anchor}``
- paragraphs with ``**bold**``, ``*italic*``, ``\\`code\\```, ``[text](url)``
- ``-`` / ``*`` bullet lists and ``1.`` ordered lists
- standalone ``![alt](path)``
- fenced code blocks::

    ```python
    from sli_ui_toolkit.widgets import Button
    ```

  The fence language (``python`` above) is optional; fence lines themselves
  are not part of the block. Code blocks render monospaced.
- figure fence::

    :::figure{side=right width=320}
    ![alt](assets/foo.png)
    Caption text
    :::

    :::figure{side=block height=160}
    ![alt](assets/foo.png)
    Caption text
    :::

  ``side``: ``right`` / ``left`` (float beside adjacent paragraphs),
  ``center`` / ``block`` (full-width row; ``center`` centers the image).
  ``width``: absolute px (``320``) or percent of the content column (``75%``).
  ``height``: absolute px (``160``). When both are set, the image fits inside
  that box; with only one, the other axis follows aspect ratio (and never
  exceeds the content column width).
- pipe tables::

    | Param | Meaning |
    |---|---|
    | `alpha` | allow alpha editing |
    | `hover` | keep hover overlays |

  The first row becomes the (bold) header when the second line is a
  ``---`` separator row (alignment markers ``:---:`` / ``---:`` are
  accepted and ignored — all cells render left-aligned). Without a
  separator the table has no header. Rows may be shorter than the header —
  missing cells are padded empty. ``\\|`` escapes a literal pipe inside a
  cell. Cells support the same inline formatting as paragraphs. Tables
  render as bordered label/value grids — the same ``TableBlock`` surface
  the Image Properties dialog uses.

This is intentionally narrower than CommonMark — Help pages are authored for
a widget-tree renderer, not a browser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable


_HEADING_RE = re.compile(
    r"^(#{1,6})\s+(?P<title>.+?)(?:\s+\{\#(?P<anchor>[-a-zA-Z0-9_:.]+)\})?\s*$"
)
_FENCE_RE = re.compile(r"^```(?P<lang>[a-zA-Z0-9_+-]*)\s*$")
_IMAGE_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)\s*$")
_FIGURE_OPEN_RE = re.compile(
    r"^:::figure(?:\{(?P<attrs>[^}]*)\})?\s*$",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^[-*+]\s+(?P<body>.+)$")
_ORDERED_RE = re.compile(r"^(?P<num>\d+)\.\s+(?P<body>.+)$")
_ATTR_RE = re.compile(r"(?P<key>[a-zA-Z_]+)\s*=\s*(?P<val>[^\s=]+)")
_PIPE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_PIPE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")


class InlineKind(str, Enum):
    TEXT = "text"
    BOLD = "bold"
    ITALIC = "italic"
    CODE = "code"
    LINK = "link"


@dataclass(frozen=True, slots=True)
class InlineSpan:
    """One inline run. ``bold`` carries the weight inherited from an
    enclosing ``**…**`` when the run has its own kind (code/link/italic),
    since the layout and selection index style by kind per character."""

    kind: InlineKind
    text: str
    href: str | None = None
    bold: bool = False


@dataclass(frozen=True, slots=True)
class SourceRange:
    """Absolute ``[start, end)`` character range in the source markdown."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SpanSource:
    """Source geometry of one inline span inside its part's plain text.

    ``plain_start``/``plain_end`` are offsets into the part's plain text (the
    list marker included, when the part is one); ``text`` is the span's text
    range in the source, ``full`` the same range with its markup delimiters
    (``**``, `` ` ``, ``[label](href)``). Copy-as-Markdown uses ``full`` only
    when the whole span is selected, so a partial selection never emits half
    a delimiter.
    """

    plain_start: int
    plain_end: int
    text: SourceRange
    full: SourceRange


@dataclass(frozen=True, slots=True)
class SegmentSource:
    """Source geometry for one selectable part (one text-index segment).

    ``part`` is the part's full structural range (heading line, list item
    line, cell text, whole code/figure fence) — the range copy-as-Markdown
    uses for separators between parts. ``emit`` is the range copied when the
    whole part is selected (it differs from ``part`` where the source carries
    invisible directives, e.g. a heading's ``{#anchor}``). ``chars`` maps the
    part's plain characters to their source offset, so a partial selection
    can be sliced without guessing.
    """

    part: SourceRange
    emit: SourceRange
    chars: tuple[int, ...]
    spans: tuple[SpanSource, ...] = ()


@dataclass(frozen=True, slots=True)
class HeadingBlock:
    level: int
    text: str
    anchor: str | None = None
    sources: tuple[SegmentSource, ...] = ()


@dataclass(frozen=True, slots=True)
class CodeBlock:
    """Fenced code block (`` ```lang … ``` ``), rendered monospaced.

    ``lines`` are the raw fence body lines, fences excluded.
    """

    lines: tuple[str, ...]
    language: str = ""
    sources: tuple[SegmentSource, ...] = ()


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    spans: tuple[InlineSpan, ...]
    sources: tuple[SegmentSource, ...] = ()


@dataclass(frozen=True, slots=True)
class ListBlock:
    ordered: bool
    items: tuple[tuple[InlineSpan, ...], ...]
    sources: tuple[SegmentSource, ...] = ()


@dataclass(frozen=True, slots=True)
class ImageBlock:
    alt: str
    path: str
    sources: tuple[SegmentSource, ...] = ()


@dataclass(frozen=True, slots=True)
class FigureBlock:
    alt: str
    path: str
    caption: str = ""
    side: str = "block"  # block | center | left | right
    width: int | None = None  # absolute px
    width_percent: float | None = None  # 1..100 of content column
    height: int | None = None
    sources: tuple[SegmentSource, ...] = ()  # absolute px


@dataclass(frozen=True, slots=True)
class TableBlock:
    """Bordered table with an optional (bold) header row.

    ``rows`` is a tuple of rows; each row a tuple of cells; each cell a
    tuple of ``InlineSpan``. Two-column label/value rows (the Image
    Properties shape) are the common case; pipe-table parsing may produce
    any column count. ``header`` cells render bold and are separated from
    the body by a divider line.
    """

    rows: tuple[tuple[tuple[InlineSpan, ...], ...], ...] = ()
    header: tuple[tuple[InlineSpan, ...], ...] = ()
    #: one source record per cell, in text-index order: header cells first,
    #: then each body row left-to-right (see ``text_index.add_table_cell``).
    sources: tuple[SegmentSource, ...] = ()


HelpBlock = (
    HeadingBlock | CodeBlock | ParagraphBlock | ListBlock | ImageBlock | FigureBlock | TableBlock
)


def parse_inline(text: str) -> tuple[InlineSpan, ...]:
    """Split a line into inline spans (bold / italic / code / link / text).

    Hand-written character scanner — no alternation regex, no key wordlist:

    - ``**…**`` → bold; the body is parsed recursively so nested spans work
      (``**a `b` c**`` gives bold text + bold code + bold text — the nested
      spans carry ``bold=True`` for the layout / selection index).
    - ``*…*`` → italic (body parsed recursively).
    - `` `…` `` → inline code; scans to the next backtick, never nests.
    - ``[label](href)`` → link (the label may itself contain inline spans).
    - anything else → text.

    An unterminated delimiter stays literal text; the scanner never raises
    and always advances, so it cannot loop and there is no regex
    backtracking. Source geometry is not part of this API — use
    :func:`_parse_inline_with_source` when copy-as-Markdown needs it.
    """
    spans, _, _, _ = _scan_spans(text, 0, end=None, base=0)
    if not spans:
        return (InlineSpan(InlineKind.TEXT, text),)
    return tuple(spans)


def _parse_inline_with_source(
    text: str, *, base: int = 0
) -> tuple[tuple[InlineSpan, ...], tuple[tuple[int, int, int, int], ...]]:
    """``parse_inline`` plus each span's source geometry.

    Returns ``(spans, sources)``; ``sources[i]`` is
    ``(text_start, text_end, full_start, full_end)`` in absolute source
    coordinates — the span's text range, and the same range with its markup
    delimiters (``**``, `` ` ``, ``[label](href)``). ``base`` shifts the
    offsets when ``text`` is a slice of the source line.
    """
    spans, sources, _, _ = _scan_spans(text, 0, end=None, base=base)
    if not spans:
        source = (base, base + len(text), base, base + len(text))
        return (InlineSpan(InlineKind.TEXT, text),), (source,)
    return tuple(spans), tuple(sources)


def _scan_spans(
    text: str,
    pos: int,
    *,
    end: str | None,
    base: int = 0,
) -> tuple[list[InlineSpan], list[tuple[int, int, int, int]], int, bool]:
    """Scan inline spans from ``pos`` until the ``end`` delimiter (or the end
    of ``text``). Returns ``(spans, sources, new_pos, terminated)``;
    ``terminated`` is True only when the closing delimiter was found and
    consumed. ``sources`` parallels ``spans`` with
    ``(text_start, text_end, full_start, full_end)`` absolute offsets."""
    spans: list[InlineSpan] = []
    sources: list[tuple[int, int, int, int]] = []
    buf: list[str] = []
    buf_start = pos
    n = len(text)

    def put(segment: str, at: int) -> None:
        nonlocal buf_start
        if not buf:
            buf_start = at
        buf.extend(segment)

    def flush() -> None:
        if buf:
            run = "".join(buf)
            spans.append(InlineSpan(InlineKind.TEXT, run))
            start = base + buf_start
            sources.append((start, start + len(run), start, start + len(run)))
            buf.clear()

    while pos < n:
        if end is not None and text.startswith(end, pos):
            flush()
            return spans, sources, pos + len(end), True
        ch = text[pos]
        if ch == "`":
            close = text.find("`", pos + 1)
            if close != -1:
                flush()
                spans.append(InlineSpan(InlineKind.CODE, text[pos + 1 : close]))
                sources.append(
                    (base + pos + 1, base + close, base + pos, base + close + 1)
                )
                pos = close + 1
                continue
            put(ch, pos)
            pos += 1
            continue
        if text.startswith("**", pos):
            body, body_src, new_pos, terminated = _scan_spans(
                text, pos + 2, end="**", base=base
            )
            if terminated and body:
                flush()
                bold, bold_src = _as_bold(
                    body, body_src, full=(base + pos, base + new_pos)
                )
                spans.extend(bold)
                sources.extend(bold_src)
                pos = new_pos
                continue
            put("**", pos)
            pos += 2
            continue
        if ch == "*":
            close = _find_single_star(text, pos + 1)
            if close != -1:
                body, body_src, _, _ = _scan_spans(
                    text[pos + 1 : close], 0, end=None, base=base + pos + 1
                )
                flush()
                italic, italic_src = _as_italic(
                    body, body_src, full=(base + pos, base + close + 1)
                )
                spans.extend(italic)
                sources.extend(italic_src)
                pos = close + 1
                continue
            put(ch, pos)
            pos += 1
            continue
        if ch == "[":
            link = _parse_link(text, pos, base=base)
            if link is not None:
                link_spans, link_src, new_pos = link
                flush()
                spans.extend(link_spans)
                sources.extend(link_src)
                pos = new_pos
                continue
            put(ch, pos)
            pos += 1
            continue
        put(ch, pos)
        pos += 1

    flush()
    return spans, sources, pos, False


def _find_single_star(text: str, start: int) -> int:
    """Index of the next ``*`` that is NOT part of a ``**`` run, or -1.
    Keeps ``**a*b**`` bold (the interior star stays literal)."""
    n = len(text)
    i = start
    while i < n:
        if text[i] == "*":
            prev_star = i > 0 and text[i - 1] == "*"
            next_star = i + 1 < n and text[i + 1] == "*"
            if not prev_star and not next_star:
                return i
        i += 1
    return -1


def _as_bold(
    spans: list[InlineSpan],
    sources: list[tuple[int, int, int, int]],
    *,
    full: tuple[int, int],
) -> tuple[list[InlineSpan], list[tuple[int, int, int, int]]]:
    """Promote a parsed ``**…**`` body to bold runs (sources merged too)."""
    if not spans:
        return [], []
    if all(span.kind == InlineKind.TEXT and span.href is None for span in spans):
        merged = "".join(s.text for s in spans)
        text = (sources[0][0], sources[-1][1])
        return (
            [InlineSpan(InlineKind.BOLD, merged, bold=True)],
            [(text[0], text[1], full[0], full[1])],
        )
    return [replace(span, bold=True) for span in spans], list(sources)


def _as_italic(
    spans: list[InlineSpan],
    sources: list[tuple[int, int, int, int]],
    *,
    full: tuple[int, int],
) -> tuple[list[InlineSpan], list[tuple[int, int, int, int]]]:
    """Promote a parsed ``*…*`` body to an italic run (plain bodies only;
    nested kinds keep their own look and their own source geometry)."""
    if not spans:
        return [], []
    if all(span.kind == InlineKind.TEXT and span.href is None for span in spans):
        merged = "".join(s.text for s in spans)
        text = (sources[0][0], sources[-1][1])
        return (
            [InlineSpan(InlineKind.ITALIC, merged)],
            [(text[0], text[1], full[0], full[1])],
        )
    return spans, list(sources)


def _parse_link(
    text: str,
    pos: int,
    *,
    base: int = 0,
) -> (
    tuple[
        list[InlineSpan],
        list[tuple[int, int, int, int]],
        int,
    ]
    | None
):
    """Parse ``[label](href)`` at ``pos`` (0-based index of ``[``), or None
    when the shape is not a link. The label is parsed as inline content; every
    label span records the whole link as its ``full`` range, so selecting the
    label copies a usable link."""
    close_bracket = text.find("]", pos + 1)
    if close_bracket == -1 or close_bracket + 1 >= len(text) or text[close_bracket + 1] != "(":
        return None
    close_paren = text.find(")", close_bracket + 2)
    if close_paren == -1:
        return None
    label = text[pos + 1 : close_bracket]
    href = text[close_bracket + 2 : close_paren]
    body, body_src, _, _ = _scan_spans(
        label, 0, end=None, base=base + pos + 1
    )
    if not body:
        body = [InlineSpan(InlineKind.TEXT, label)]
        body_src = [(base + pos + 1, base + close_bracket, base + pos + 1, base + close_bracket)]
    out: list[InlineSpan] = []
    out_src: list[tuple[int, int, int, int]] = []
    full = (base + pos, base + close_paren + 1)
    for span, source in zip(body, body_src):
        if span.kind == InlineKind.TEXT and not span.bold:
            out.append(InlineSpan(InlineKind.LINK, span.text, href=href))
        else:
            out.append(replace(span, href=href))
        out_src.append((source[0], source[1], full[0], full[1]))
    return out, out_src, close_paren + 1


def _parse_attrs(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    return {m.group("key").lower(): m.group("val").strip("\"'") for m in _ATTR_RE.finditer(raw)}


def _line_layout(markdown: str) -> tuple[str, list[str], list[int]]:
    """Normalised source, its lines, and each line's first-character offset."""
    source = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    starts: list[int] = []
    pos = 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1
    return source, lines, starts


def _trim_bounds(raw: str) -> tuple[int, int]:
    """``(leading, trailing)`` whitespace counts of one raw source line."""
    return len(raw) - len(raw.lstrip()), len(raw) - len(raw.rstrip())


def _span_sources(
    spans: tuple[InlineSpan, ...],
    raw_sources: tuple[tuple[int, int, int, int], ...],
    *,
    plain_offset: int = 0,
    char_map: tuple[int, ...] | None = None,
) -> tuple[SpanSource, ...]:
    """Pair scanner output with plain offsets and source ranges.

    Plain offsets are accumulated from the spans' TEXT lengths — the source
    offsets cannot be used for them (markup has source length but no plain
    character). ``char_map`` translates scanner offsets (joined paragraph /
    cell text) into source offsets; ``None`` means the scanner already ran on
    the source itself.
    """
    out: list[SpanSource] = []
    cursor = plain_offset
    for span, raw in zip(spans, raw_sources):
        text_start, text_end, full_start, full_end = raw
        if char_map is None:
            text = SourceRange(text_start, text_end)
            full = SourceRange(full_start, full_end)
        else:
            text = SourceRange(
                char_map[text_start],
                char_map[text_end - 1] + 1 if text_end > text_start else char_map[text_start],
            )
            full = SourceRange(char_map[full_start], char_map[full_end - 1] + 1)
        out.append(
            SpanSource(
                plain_start=cursor,
                plain_end=cursor + len(span.text),
                text=text,
                full=full,
            )
        )
        cursor += len(span.text)
    return tuple(out)


def _chars_from_spans(
    raw_sources: tuple[tuple[int, int, int, int], ...],
    char_map: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    """One source offset per plain character of the part's inline spans."""
    if char_map is None:
        return tuple(
            offset
            for text_start, text_end, _full_start, _full_end in raw_sources
            for offset in range(text_start, text_end)
        )
    return tuple(
        char_map[position]
        for text_start, text_end, _full_start, _full_end in raw_sources
        for position in range(text_start, text_end)
    )


def _heading_block(
    heading: re.Match[str],
    raw: str,
    index: int,
    starts: list[int],
) -> HeadingBlock:
    indent, trail = _trim_bounds(raw)
    offset = starts[index]
    group = heading.group("title")
    text = group.strip()
    title_start = offset + indent + heading.start("title") + (len(group) - len(group.lstrip()))
    part = SourceRange(offset + indent, offset + len(raw) - trail)
    emit = part
    anchor = heading.group("anchor")
    if anchor:
        # The ``{#anchor}`` directive is invisible: copy the heading without
        # it (``heading.start("anchor")`` points at the name, ``{#`` two chars
        # earlier; trailing spaces before the brace go too).
        relative_end = heading.start("anchor") - len("{#")
        while relative_end > 0 and raw[indent + relative_end - 1] == " ":
            relative_end -= 1
        emit = SourceRange(part.start, offset + indent + relative_end)
    chars = tuple(range(title_start, title_start + len(text)))
    span = SpanSource(
        plain_start=0,
        plain_end=len(text),
        text=SourceRange(title_start, title_start + len(text)),
        # Selecting exactly the title text copies the heading (level included),
        # still without its invisible anchor directive.
        full=emit,
    )
    source = SegmentSource(part=part, emit=emit, chars=chars, spans=(span,))
    return HeadingBlock(
        level=len(heading.group(1)),
        text=text,
        anchor=anchor,
        sources=(source,),
    )


def _code_block(
    body: list[tuple[int, str]],
    language: str,
    open_index: int,
    close_index: int | None,
    lines: list[str],
    starts: list[int],
) -> CodeBlock:
    chars: list[int] = []
    for position, (line_index, line) in enumerate(body):
        if position:
            previous = body[position - 1][0]
            chars.append(starts[previous] + len(lines[previous]))
        chars.extend(range(starts[line_index], starts[line_index] + len(line)))
    if close_index is not None:
        part_end = starts[close_index] + len(lines[close_index])
    elif body:
        part_end = starts[body[-1][0]] + len(body[-1][1])
    else:
        part_end = starts[open_index] + len(lines[open_index])
    part = SourceRange(starts[open_index], part_end)
    source = SegmentSource(part=part, emit=part, chars=tuple(chars))
    return CodeBlock(
        lines=tuple(line for _, line in body),
        language=language,
        sources=(source,),
    )


def _image_block(
    image: re.Match[str],
    raw: str,
    index: int,
    starts: list[int],
) -> ImageBlock:
    indent, trail = _trim_bounds(raw)
    offset = starts[index]
    alt = image.group("alt")
    path_group = image.group("path")
    path = path_group.strip()
    part = SourceRange(offset + indent, offset + len(raw) - trail)
    text = alt or path
    if alt:
        text_start = offset + indent + image.start("alt")
    else:
        text_start = (
            offset
            + indent
            + image.start("path")
            + (len(path_group) - len(path_group.lstrip()))
        )
    chars = tuple(range(text_start, text_start + len(text)))
    span = SpanSource(
        plain_start=0,
        plain_end=len(text),
        text=SourceRange(text_start, text_start + len(text)),
        full=part,
    )
    source = SegmentSource(part=part, emit=part, chars=chars, spans=(span,))
    return ImageBlock(alt=alt, path=path, sources=(source,))


def _list_item(
    match: re.Match[str],
    raw: str,
    index: int,
    starts: list[int],
    *,
    marker_len: int,
) -> tuple[tuple[InlineSpan, ...], SegmentSource]:
    indent, trail = _trim_bounds(raw)
    offset = starts[index]
    body = match.group("body")
    body_start = offset + indent + match.start("body")
    spans, raw_sources = _parse_inline_with_source(body, base=body_start)
    marker_start = max(offset + indent, body_start - marker_len)
    span_sources = _span_sources(spans, raw_sources, plain_offset=marker_len)
    # ``chars`` is per PLAIN character: markup delimiters carry no character
    # of their own, so it is built from the spans' text ranges, not from the
    # raw body (a ``range()`` over the source would overshoot by the markup).
    chars = tuple(range(marker_start, body_start)) + _chars_from_spans(raw_sources)
    part = SourceRange(offset + indent, offset + len(raw) - trail)
    source = SegmentSource(part=part, emit=part, chars=chars, spans=span_sources)
    return spans, source


def _paragraph_block(
    parts: list[str],
    indices: list[int],
    lines: list[str],
    starts: list[int],
) -> ParagraphBlock:
    joined = " ".join(parts)
    # Joined-text offset -> source offset (the joining space maps to the
    # newline that ended its row). Spans are mapped through this; the
    # per-character index is then derived from the spans, since markup
    # characters have no plain counterpart.
    joined_map: list[int] = []
    for position, index in enumerate(indices):
        raw = lines[index]
        indent = len(raw) - len(raw.lstrip())
        start = starts[index] + indent
        joined_map.extend(range(start, start + len(parts[position])))
        if position < len(indices) - 1:
            joined_map.append(starts[index] + len(raw))
    spans, raw_sources = _parse_inline_with_source(joined, base=0)
    mapped = tuple(joined_map)
    span_sources = _span_sources(spans, raw_sources, char_map=mapped)
    chars = _chars_from_spans(raw_sources, mapped)
    first_raw = lines[indices[0]]
    last_raw = lines[indices[-1]]
    part = SourceRange(
        starts[indices[0]] + (len(first_raw) - len(first_raw.lstrip())),
        starts[indices[-1]] + len(last_raw) - (len(last_raw) - len(last_raw.rstrip())),
    )
    source = SegmentSource(part=part, emit=part, chars=chars, spans=span_sources)
    return ParagraphBlock(spans=spans, sources=(source,))


def parse_help_blocks(markdown: str) -> tuple[HelpBlock, ...]:
    """Parse controlled help markdown into an ordered block list.

    Every block also carries ``sources`` — the source geometry copy-as-Markdown
    uses to map a selection back to the page source (``SegmentSource``), aligned
    one-to-one with the text-index segments the block produces.
    """
    _source, lines, starts = _line_layout(markdown)
    blocks: list[HelpBlock] = []
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        figure_open = _FIGURE_OPEN_RE.match(stripped)
        if figure_open:
            open_index = i
            attrs = _parse_attrs(figure_open.group("attrs"))
            body: list[tuple[int, str]] = []
            i += 1
            while i < n and lines[i].strip() != ":::":
                body.append((i, lines[i]))
                i += 1
            close_index = i if i < n and lines[i].strip() == ":::" else None
            if close_index is not None:
                i += 1
            blocks.append(
                _figure_from_body(
                    body,
                    attrs,
                    open_index=open_index,
                    close_index=close_index,
                    lines=lines,
                    starts=starts,
                )
            )
            continue

        fence = _FENCE_RE.match(stripped)
        if fence:
            open_index = i
            code_body: list[tuple[int, str]] = []
            i += 1
            while i < n and not _FENCE_RE.match(lines[i].strip()):
                code_body.append((i, lines[i]))
                i += 1
            close_index = i if i < n and _FENCE_RE.match(lines[i].strip()) else None
            if close_index is not None:
                i += 1
            while code_body and not code_body[-1][1]:
                code_body.pop()
            blocks.append(
                _code_block(
                    code_body, fence.group("lang"), open_index, close_index, lines, starts
                )
            )
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            blocks.append(_heading_block(heading, raw, i, starts))
            i += 1
            continue

        image = _IMAGE_RE.match(stripped)
        if image:
            blocks.append(_image_block(image, raw, i, starts))
            i += 1
            continue

        bullet = _BULLET_RE.match(stripped)
        ordered = _ORDERED_RE.match(stripped)
        if bullet or ordered:
            items: list[tuple[InlineSpan, ...]] = []
            sources: list[SegmentSource] = []
            is_ordered = ordered is not None
            marker_len = 3 if is_ordered else 2
            while i < n:
                row = lines[i].strip()
                if not row:
                    break
                match = (_ORDERED_RE if is_ordered else _BULLET_RE).match(row)
                if not match:
                    break
                spans, source = _list_item(
                    match, lines[i], i, starts, marker_len=marker_len
                )
                items.append(spans)
                sources.append(source)
                i += 1
            blocks.append(
                ListBlock(ordered=is_ordered, items=tuple(items), sources=tuple(sources))
            )
            continue

        if _PIPE_ROW_RE.match(stripped):
            blocks.append(_parse_pipe_table(lines, starts, i))
            while i < n and _PIPE_ROW_RE.match(lines[i].strip()):
                i += 1
            continue

        # Paragraph: gather consecutive non-empty, non-structural lines.
        para_parts: list[str] = []
        para_indices: list[int] = []
        while i < n:
            row = lines[i]
            row_stripped = row.strip()
            if not row_stripped:
                break
            if (
                _HEADING_RE.match(row_stripped)
                or _FENCE_RE.match(row_stripped)
                or _FIGURE_OPEN_RE.match(row_stripped)
                or _IMAGE_RE.match(row_stripped)
                or _BULLET_RE.match(row_stripped)
                or _ORDERED_RE.match(row_stripped)
                or _PIPE_ROW_RE.match(row_stripped)
            ):
                break
            para_parts.append(row_stripped)
            para_indices.append(i)
            i += 1
        if para_parts:
            blocks.append(_paragraph_block(para_parts, para_indices, lines, starts))

    return tuple(blocks)


def _split_pipe_cells_with_offsets(
    line: str,
    base: int,
) -> list[tuple[str, tuple[int, ...], SourceRange]]:
    """Split a pipe row into ``(trimmed text, source offsets, part range)``.

    One offset per text character: ``\\|`` escapes a literal pipe (two source
    characters → one text character, and the offset points at the backslash).
    The part range is the cell's trimmed source extent (markup included).
    """
    lead, trail = _trim_bounds(line)
    lo = lead
    hi = len(line) - trail
    if hi > lo and line[lo] == "|":
        lo += 1
    if hi > lo and line[hi - 1] == "|":
        hi -= 1
    cells: list[tuple[str, tuple[int, ...], SourceRange]] = []
    text: list[str] = []
    offsets: list[int] = []
    cell_start = lo
    i = lo
    while i < hi:
        ch = line[i]
        if ch == "\\" and i + 1 < hi and line[i + 1] == "|":
            text.append("|")
            offsets.append(base + i)
            i += 2
            continue
        if ch == "|":
            cells.append(_trim_cell("".join(text), offsets, base + cell_start, base + i))
            text, offsets = [], []
            i += 1
            cell_start = i
            continue
        text.append(ch)
        offsets.append(base + i)
        i += 1
    cells.append(_trim_cell("".join(text), offsets, base + cell_start, base + hi))
    return cells


def _trim_cell(
    text: str,
    offsets: list[int],
    raw_start: int,
    raw_end: int,
) -> tuple[str, tuple[int, ...], SourceRange]:
    lo = 0
    hi = len(text)
    while lo < hi and text[lo].isspace():
        lo += 1
    while hi > lo and text[hi - 1].isspace():
        hi -= 1
    # The part keeps the cell's raw extent (minus surrounding spaces) so the
    # `` | `` separators between cells stay in the source gaps.
    leading = len(text) - len(text.lstrip())
    trailing = len(text) - len(text.rstrip())
    part = SourceRange(raw_start + leading, raw_end - trailing)
    return text[lo:hi], tuple(offsets[lo:hi]), part


def _split_pipe_cells(line: str) -> list[str]:
    """Split a ``| a | b |`` row into trimmed cell texts (``\\|`` escapes a
    literal pipe; leading/trailing pipes are the table fence, not cells)."""
    return [text for text, _, _ in _split_pipe_cells_with_offsets(line, 0)]


_EMPTY_SEGMENT_SOURCE = SegmentSource(
    part=SourceRange(0, 0), emit=SourceRange(0, 0), chars=()
)


def _cell_source(
    text: str,
    offsets: tuple[int, ...],
    part: SourceRange,
) -> SegmentSource:
    if not offsets:
        return _EMPTY_SEGMENT_SOURCE
    spans, raw_sources = _parse_inline_with_source(text, base=0)
    span_sources = _span_sources(spans, raw_sources, char_map=offsets)
    chars = _chars_from_spans(raw_sources, offsets)
    return SegmentSource(part=part, emit=part, chars=chars, spans=span_sources)


def _parse_pipe_table(
    lines: list[str],
    starts: list[int],
    start: int,
) -> TableBlock:
    """Build a ``TableBlock`` from consecutive pipe rows starting at
    ``start``. The second line being a ``---`` separator turns the first
    row into the header; rows shorter than the column count are padded
    with empty cells."""
    first_cells = _split_pipe_cells_with_offsets(lines[start], starts[start])
    header: tuple[tuple[InlineSpan, ...], ...] = ()
    header_sources: list[SegmentSource] = []
    body_rows: list[tuple[tuple[InlineSpan, ...], ...]] = []
    body_sources: list[list[SegmentSource]] = []
    index = start + 1

    first_spans = tuple(parse_inline(text) for text, _, _ in first_cells)
    first_source = [
        _cell_source(text, offsets, part) for text, offsets, part in first_cells
    ]
    if index < len(lines) and _PIPE_SEPARATOR_RE.match(lines[index].strip()):
        header = first_spans
        header_sources = first_source
        index += 1
    else:
        body_rows.append(first_spans)
        body_sources.append(first_source)
    while index < len(lines) and _PIPE_ROW_RE.match(lines[index].strip()):
        cells = _split_pipe_cells_with_offsets(lines[index], starts[index])
        body_rows.append(tuple(parse_inline(text) for text, _, _ in cells))
        body_sources.append(
            [_cell_source(text, offsets, part) for text, offsets, part in cells]
        )
        index += 1

    col_count = max(
        len(header),
        *(len(row) for row in body_rows),
    )
    empty = (InlineSpan(InlineKind.TEXT, ""),)

    def _padded(row: tuple[tuple[InlineSpan, ...], ...]) -> tuple[tuple[InlineSpan, ...], ...]:
        return row if len(row) >= col_count else row + (empty,) * (col_count - len(row))

    sources: list[SegmentSource] = []
    if header:
        sources.extend(header_sources)
        sources.extend([_EMPTY_SEGMENT_SOURCE] * (col_count - len(header_sources)))
    for row_sources in body_sources:
        sources.extend(row_sources)
        sources.extend([_EMPTY_SEGMENT_SOURCE] * (col_count - len(row_sources)))

    return TableBlock(
        rows=tuple(_padded(row) for row in body_rows),
        header=_padded(header) if header else (),
        sources=tuple(sources),
    )


def _figure_from_body(
    body: list[tuple[int, str]],
    attrs: dict[str, str],
    *,
    open_index: int,
    close_index: int | None,
    lines: list[str],
    starts: list[int],
) -> FigureBlock:
    alt = ""
    path = ""
    image_line: int | None = None
    image_match: re.Match[str] | None = None
    caption_parts: list[tuple[int, str]] = []
    for index, raw in body:
        stripped = raw.strip()
        if not stripped:
            continue
        image = _IMAGE_RE.match(stripped)
        if image and not path:
            alt = image.group("alt")
            path = image.group("path").strip()
            image_line = index
            image_match = image
            continue
        caption_parts.append((index, stripped))
    side = attrs.get("side", "block").lower()
    if side not in {"block", "center", "left", "right"}:
        side = "block"
    width_raw = attrs.get("width")
    width: int | None = None
    width_percent: float | None = None
    if width_raw:
        raw = width_raw.strip()
        if raw.endswith("%"):
            try:
                width_percent = max(1.0, min(100.0, float(raw[:-1].strip())))
            except ValueError:
                width_percent = None
        else:
            try:
                width = max(1, int(raw))
            except ValueError:
                width = None
    height: int | None = None
    height_raw = attrs.get("height")
    if height_raw:
        try:
            height = max(1, int(height_raw.strip()))
        except ValueError:
            height = None

    if close_index is not None:
        part_end = starts[close_index] + len(lines[close_index])
    elif body:
        part_end = starts[body[-1][0]] + len(body[-1][1])
    else:
        part_end = starts[open_index] + len(lines[open_index])
    part = SourceRange(starts[open_index], part_end)

    caption = " ".join(text for _, text in caption_parts)
    chars: list[int] = []
    if caption:
        for position, (index, text) in enumerate(caption_parts):
            if position:
                previous = caption_parts[position - 1][0]
                chars.append(starts[previous] + len(lines[previous]))
            indent = len(lines[index]) - len(lines[index].lstrip())
            start = starts[index] + indent
            chars.extend(range(start, start + len(text)))
    elif alt and image_line is not None and image_match is not None:
        indent = len(lines[image_line]) - len(lines[image_line].lstrip())
        start = starts[image_line] + indent + image_match.start("alt")
        chars.extend(range(start, start + len(alt)))
    elif path and image_line is not None and image_match is not None:
        indent = len(lines[image_line]) - len(lines[image_line].lstrip())
        path_group = image_match.group("path")
        start = (
            starts[image_line]
            + indent
            + image_match.start("path")
            + (len(path_group) - len(path_group.lstrip()))
        )
        chars.extend(range(start, start + len(path)))

    plain = caption or alt or path
    sources: tuple[SegmentSource, ...] = ()
    if chars and plain:
        span = SpanSource(
            plain_start=0,
            plain_end=len(plain),
            text=SourceRange(chars[0], chars[-1] + 1),
            full=part,
        )
        sources = (
            SegmentSource(part=part, emit=part, chars=tuple(chars), spans=(span,)),
        )

    return FigureBlock(
        alt=alt,
        path=path,
        caption=caption,
        side=side,
        width=width,
        width_percent=width_percent,
        height=height,
        sources=sources,
    )


def collect_heading_anchors(blocks: Iterable[HelpBlock]) -> tuple[tuple[str, str], ...]:
    """Return ``(anchor_id, title)`` for headings that expose an anchor."""
    items: list[tuple[str, str]] = []
    for block in blocks:
        if isinstance(block, HeadingBlock) and block.anchor:
            items.append((block.anchor, block.text))
    return tuple(items)


def spans_to_plain(spans: tuple[InlineSpan, ...]) -> str:
    return "".join(span.text for span in spans)


def blocks_to_plain_text(blocks: Iterable[HelpBlock]) -> str:
    """Flatten parsed blocks to plain text (page-level copy / search)."""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, HeadingBlock):
            parts.append(block.text)
        elif isinstance(block, CodeBlock):
            parts.append("\n".join(block.lines))
        elif isinstance(block, ParagraphBlock):
            parts.append(spans_to_plain(block.spans))
        elif isinstance(block, ListBlock):
            for index, item in enumerate(block.items, start=1):
                prefix = f"{index}. " if block.ordered else "• "
                parts.append(prefix + spans_to_plain(item))
        elif isinstance(block, ImageBlock):
            parts.append(block.alt or block.path)
        elif isinstance(block, FigureBlock):
            parts.append(block.caption or block.alt or block.path)
        elif isinstance(block, TableBlock):
            all_rows: list[tuple[tuple[InlineSpan, ...], ...]] = []
            if block.header:
                all_rows.append(block.header)
            all_rows.extend(block.rows)
            for row in all_rows:
                # One part per cell — matches the text-index segments
                # ``build_text_index`` emits per cell (see ``add_table_cell``).
                for cell in row:
                    parts.append(spans_to_plain(cell))
    return "\n\n".join(part for part in parts if part.strip())
