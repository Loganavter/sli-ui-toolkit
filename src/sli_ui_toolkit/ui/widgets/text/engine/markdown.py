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
class HeadingBlock:
    level: int
    text: str
    anchor: str | None = None


@dataclass(frozen=True, slots=True)
class CodeBlock:
    """Fenced code block (`` ```lang … ``` ``), rendered monospaced.

    ``lines`` are the raw fence body lines, fences excluded.
    """

    lines: tuple[str, ...]
    language: str = ""


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    spans: tuple[InlineSpan, ...]


@dataclass(frozen=True, slots=True)
class ListBlock:
    ordered: bool
    items: tuple[tuple[InlineSpan, ...], ...]


@dataclass(frozen=True, slots=True)
class ImageBlock:
    alt: str
    path: str


@dataclass(frozen=True, slots=True)
class FigureBlock:
    alt: str
    path: str
    caption: str = ""
    side: str = "block"  # block | center | left | right
    width: int | None = None  # absolute px
    width_percent: float | None = None  # 1..100 of content column
    height: int | None = None  # absolute px


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
    backtracking.
    """
    spans, _, _ = _scan_spans(text, 0, end=None)
    if not spans:
        return (InlineSpan(InlineKind.TEXT, text),)
    return tuple(spans)


def _scan_spans(
    text: str,
    pos: int,
    *,
    end: str | None,
) -> tuple[list[InlineSpan], int, bool]:
    """Scan inline spans from ``pos`` until the ``end`` delimiter (or the end
    of ``text``). Returns ``(spans, new_pos, terminated)``; ``terminated`` is
    True only when the closing delimiter was found and consumed."""
    spans: list[InlineSpan] = []
    buf: list[str] = []
    n = len(text)

    def flush() -> None:
        if buf:
            spans.append(InlineSpan(InlineKind.TEXT, "".join(buf)))
            buf.clear()

    while pos < n:
        if end is not None and text.startswith(end, pos):
            flush()
            return spans, pos + len(end), True
        ch = text[pos]
        if ch == "`":
            close = text.find("`", pos + 1)
            if close != -1:
                flush()
                spans.append(InlineSpan(InlineKind.CODE, text[pos + 1 : close]))
                pos = close + 1
                continue
            buf.append(ch)
            pos += 1
            continue
        if text.startswith("**", pos):
            body, new_pos, terminated = _scan_spans(text, pos + 2, end="**")
            if terminated and body:
                flush()
                spans.extend(_as_bold(body))
                pos = new_pos
                continue
            buf.append("**")
            pos += 2
            continue
        if ch == "*":
            close = _find_single_star(text, pos + 1)
            if close != -1:
                body, _, _ = _scan_spans(text[pos + 1 : close], 0, end=None)
                flush()
                spans.extend(_as_italic(body))
                pos = close + 1
                continue
            buf.append(ch)
            pos += 1
            continue
        if ch == "[":
            link = _parse_link(text, pos)
            if link is not None:
                link_spans, new_pos = link
                flush()
                spans.extend(link_spans)
                pos = new_pos
                continue
            buf.append(ch)
            pos += 1
            continue
        buf.append(ch)
        pos += 1

    flush()
    return spans, pos, False


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


def _as_bold(spans: list[InlineSpan]) -> list[InlineSpan]:
    """Promote a parsed ``**…**`` body to bold runs."""
    if not spans:
        return []
    if all(span.kind == InlineKind.TEXT and span.href is None for span in spans):
        return [InlineSpan(InlineKind.BOLD, "".join(s.text for s in spans), bold=True)]
    return [replace(span, bold=True) for span in spans]


def _as_italic(spans: list[InlineSpan]) -> list[InlineSpan]:
    """Promote a parsed ``*…*`` body to an italic run (plain bodies only;
    nested kinds keep their own look)."""
    if not spans:
        return []
    if all(span.kind == InlineKind.TEXT and span.href is None for span in spans):
        return [InlineSpan(InlineKind.ITALIC, "".join(s.text for s in spans))]
    return spans


def _parse_link(text: str, pos: int) -> tuple[list[InlineSpan], int] | None:
    """Parse ``[label](href)`` at ``pos`` (0-based index of ``[``), or None
    when the shape is not a link. The label is parsed as inline content."""
    close_bracket = text.find("]", pos + 1)
    if close_bracket == -1 or close_bracket + 1 >= len(text) or text[close_bracket + 1] != "(":
        return None
    close_paren = text.find(")", close_bracket + 2)
    if close_paren == -1:
        return None
    label = text[pos + 1 : close_bracket]
    href = text[close_bracket + 2 : close_paren]
    body, _, _ = _scan_spans(label, 0, end=None)
    if not body:
        body = [InlineSpan(InlineKind.TEXT, label)]
    out: list[InlineSpan] = []
    for span in body:
        if span.kind == InlineKind.TEXT and not span.bold:
            out.append(InlineSpan(InlineKind.LINK, span.text, href=href))
        else:
            out.append(replace(span, href=href))
    return out, close_paren + 1


def _parse_attrs(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    return {m.group("key").lower(): m.group("val").strip("\"'") for m in _ATTR_RE.finditer(raw)}


def parse_help_blocks(markdown: str) -> tuple[HelpBlock, ...]:
    """Parse controlled help markdown into an ordered block list."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[HelpBlock] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        figure_open = _FIGURE_OPEN_RE.match(stripped)
        if figure_open:
            attrs = _parse_attrs(figure_open.group("attrs"))
            body_lines: list[str] = []
            i += 1
            while i < n and lines[i].strip() != ":::":
                body_lines.append(lines[i])
                i += 1
            if i < n and lines[i].strip() == ":::":
                i += 1
            blocks.append(_figure_from_body(body_lines, attrs))
            continue

        fence = _FENCE_RE.match(stripped)
        if fence:
            code_lines: list[str] = []
            i += 1
            while i < n and not _FENCE_RE.match(lines[i].strip()):
                code_lines.append(lines[i])
                i += 1
            if i < n and _FENCE_RE.match(lines[i].strip()):
                i += 1
            while code_lines and not code_lines[-1]:
                code_lines.pop()
            blocks.append(
                CodeBlock(lines=tuple(code_lines), language=fence.group("lang"))
            )
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            title = heading.group("title").strip()
            anchor = heading.group("anchor")
            blocks.append(HeadingBlock(level=level, text=title, anchor=anchor))
            i += 1
            continue

        image = _IMAGE_RE.match(stripped)
        if image:
            blocks.append(
                ImageBlock(alt=image.group("alt"), path=image.group("path").strip())
            )
            i += 1
            continue

        bullet = _BULLET_RE.match(stripped)
        ordered = _ORDERED_RE.match(stripped)
        if bullet or ordered:
            items: list[tuple[InlineSpan, ...]] = []
            is_ordered = ordered is not None
            while i < n:
                row = lines[i].strip()
                if not row:
                    break
                b = _BULLET_RE.match(row)
                o = _ORDERED_RE.match(row)
                if is_ordered:
                    if not o:
                        break
                    items.append(parse_inline(o.group("body")))
                else:
                    if not b:
                        break
                    items.append(parse_inline(b.group("body")))
                i += 1
            blocks.append(ListBlock(ordered=is_ordered, items=tuple(items)))
            continue

        if _PIPE_ROW_RE.match(stripped):
            blocks.append(_parse_pipe_table(lines, i))
            while i < n and _PIPE_ROW_RE.match(lines[i].strip()):
                i += 1
            continue

        # Paragraph: gather consecutive non-empty, non-structural lines.
        para_parts: list[str] = []
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
            i += 1
        if para_parts:
            blocks.append(ParagraphBlock(spans=parse_inline(" ".join(para_parts))))

    return tuple(blocks)


def _split_pipe_cells(line: str) -> list[str]:
    """Split a ``| a | b |`` row into trimmed cell texts (``\\|`` escapes a
    literal pipe; leading/trailing pipes are the table fence, not cells)."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return [cell.strip() for cell in cells]


def _parse_pipe_table(lines: list[str], start: int) -> TableBlock:
    """Build a ``TableBlock`` from consecutive pipe rows starting at
    ``start``. The second line being a ``---`` separator turns the first
    row into the header; rows shorter than the column count are padded
    with empty cells."""
    first_cells = _split_pipe_cells(lines[start])
    header: tuple[tuple[InlineSpan, ...], ...] = ()
    body_rows: list[tuple[tuple[InlineSpan, ...], ...]] = []
    index = start + 1
    if index < len(lines) and _PIPE_SEPARATOR_RE.match(lines[index].strip()):
        header = tuple(parse_inline(cell) for cell in first_cells)
        index += 1
    else:
        body_rows.append(tuple(parse_inline(cell) for cell in first_cells))
    while index < len(lines) and _PIPE_ROW_RE.match(lines[index].strip()):
        body_rows.append(
            tuple(parse_inline(cell) for cell in _split_pipe_cells(lines[index]))
        )
        index += 1

    col_count = max(
        len(header),
        *(len(row) for row in body_rows),
    )
    empty = (InlineSpan(InlineKind.TEXT, ""),)

    def _padded(row: tuple[tuple[InlineSpan, ...], ...]) -> tuple[tuple[InlineSpan, ...], ...]:
        return row if len(row) >= col_count else row + (empty,) * (col_count - len(row))

    return TableBlock(
        rows=tuple(_padded(row) for row in body_rows),
        header=_padded(header) if header else (),
    )


def _figure_from_body(body_lines: Iterable[str], attrs: dict[str, str]) -> FigureBlock:
    alt = ""
    path = ""
    caption_parts: list[str] = []
    for raw in body_lines:
        stripped = raw.strip()
        if not stripped:
            continue
        image = _IMAGE_RE.match(stripped)
        if image and not path:
            alt = image.group("alt")
            path = image.group("path").strip()
            continue
        caption_parts.append(stripped)
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
    return FigureBlock(
        alt=alt,
        path=path,
        caption=" ".join(caption_parts),
        side=side,
        width=width,
        width_percent=width_percent,
        height=height,
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
