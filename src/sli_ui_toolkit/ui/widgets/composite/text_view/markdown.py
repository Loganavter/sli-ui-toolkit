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
from dataclasses import dataclass
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

_INLINE_TOKEN_RE = re.compile(
    r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))"
)


class InlineKind(str, Enum):
    TEXT = "text"
    BOLD = "bold"
    ITALIC = "italic"
    CODE = "code"
    LINK = "link"
    KBD = "kbd"


@dataclass(frozen=True, slots=True)
class InlineSpan:
    kind: InlineKind
    text: str
    href: str | None = None


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
    """Split a line into inline spans (bold / italic / code / link / text)."""
    spans: list[InlineSpan] = []
    pos = 0
    for match in _INLINE_TOKEN_RE.finditer(text):
        start, end = match.span()
        if start > pos:
            spans.extend(_text_spans(text[pos:start]))
        token = match.group(0)
        spans.append(_token_to_span(token))
        pos = end
    if pos < len(text):
        spans.extend(_text_spans(text[pos:]))
    return tuple(spans) if spans else (InlineSpan(InlineKind.TEXT, text),)


def _text_spans(chunk: str) -> list[InlineSpan]:
    if not chunk:
        return []
    # Treat short backtick-free key chords written as Ctrl+S outside code
    # as plain text; authors should use `Ctrl+S` for kbd styling.
    return [InlineSpan(InlineKind.TEXT, chunk)]


def _token_to_span(token: str) -> InlineSpan:
    if token.startswith("**") and token.endswith("**") and len(token) >= 4:
        return InlineSpan(InlineKind.BOLD, token[2:-2])
    if token.startswith("*") and token.endswith("*") and len(token) >= 3:
        return InlineSpan(InlineKind.ITALIC, token[1:-1])
    if token.startswith("`") and token.endswith("`") and len(token) >= 2:
        inner = token[1:-1]
        if _looks_like_shortcut(inner):
            return InlineSpan(InlineKind.KBD, inner)
        return InlineSpan(InlineKind.CODE, inner)
    if token.startswith("[") and "](" in token and token.endswith(")"):
        label, _, rest = token[1:].partition("](")
        return InlineSpan(InlineKind.LINK, label, href=rest[:-1])
    return InlineSpan(InlineKind.TEXT, token)


def _looks_like_shortcut(text: str) -> bool:
    if not text:
        return False
    if "+" in text:
        return True
    lowered = text.lower()
    return lowered in {
        "esc",
        "enter",
        "return",
        "tab",
        "space",
        "backspace",
        "delete",
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
        "lmb",
        "rmb",
        "mmb",
    }


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
