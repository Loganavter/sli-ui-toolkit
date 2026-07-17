"""Controlled markdown subset → typed help document blocks.

Authoring contract (v1):

- ``##`` / ``###`` headings; optional ``{#anchor}``
- paragraphs with ``**bold**``, ``*italic*``, ``\\`code\\```, ``[text](url)``
- ``-`` / ``*`` bullet lists and ``1.`` ordered lists
- standalone ``![alt](path)``
- figure fence::

    :::figure{side=right width=320}
    ![alt](assets/foo.png)
    Caption text
    :::

  ``side``: ``right`` / ``left`` (float beside adjacent paragraphs),
  ``center`` / ``block`` (full-width row; ``center`` centers the image).

This is intentionally narrower than CommonMark — Help pages are authored for
a widget-tree renderer, not a browser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


_HEADING_RE = re.compile(
    r"^(#{2,3})\s+(?P<title>.+?)(?:\s+\{\#(?P<anchor>[-a-zA-Z0-9_:.]+)\})?\s*$"
)
_IMAGE_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)\s*$")
_FIGURE_OPEN_RE = re.compile(
    r"^:::figure(?:\{(?P<attrs>[^}]*)\})?\s*$",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^[-*+]\s+(?P<body>.+)$")
_ORDERED_RE = re.compile(r"^(?P<num>\d+)\.\s+(?P<body>.+)$")
_ATTR_RE = re.compile(r"(?P<key>[a-zA-Z_]+)\s*=\s*(?P<val>[^\s=]+)")

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
    width: int | None = None


HelpBlock = HeadingBlock | ParagraphBlock | ListBlock | ImageBlock | FigureBlock


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

        # Paragraph: gather consecutive non-empty, non-structural lines.
        para_parts: list[str] = []
        while i < n:
            row = lines[i]
            row_stripped = row.strip()
            if not row_stripped:
                break
            if (
                _HEADING_RE.match(row_stripped)
                or _FIGURE_OPEN_RE.match(row_stripped)
                or _IMAGE_RE.match(row_stripped)
                or _BULLET_RE.match(row_stripped)
                or _ORDERED_RE.match(row_stripped)
            ):
                break
            para_parts.append(row_stripped)
            i += 1
        if para_parts:
            blocks.append(ParagraphBlock(spans=parse_inline(" ".join(para_parts))))

    return tuple(blocks)


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
    width = None
    if width_raw:
        try:
            width = max(1, int(width_raw))
        except ValueError:
            width = None
    return FigureBlock(
        alt=alt,
        path=path,
        caption=" ".join(caption_parts),
        side=side,
        width=width,
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
    return "\n\n".join(part for part in parts if part.strip())
