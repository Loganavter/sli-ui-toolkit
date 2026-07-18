"""Unified plain-text stream + per-character metadata for help documents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sli_ui_toolkit.ui.widgets.composite.help_document.blocks import (
    FigureBlock,
    HeadingBlock,
    HelpBlock,
    ImageBlock,
    InlineKind,
    InlineSpan,
    ListBlock,
    ParagraphBlock,
    blocks_to_plain_text,
    spans_to_plain,
)


class TextRoleKind(str, Enum):
    BODY = "body"
    HEADING = "heading"
    LIST_MARKER = "list_marker"
    SEPARATOR = "separator"


@dataclass(frozen=True, slots=True)
class CharStyle:
    kind: InlineKind
    href: str | None = None


@dataclass(frozen=True, slots=True)
class TextRole:
    kind: TextRoleKind
    heading_level: int = 0


@dataclass(frozen=True, slots=True)
class TextSegment:
    """Contiguous selectable range produced from one logical block part."""

    start: int
    end: int
    block_index: int
    list_item_index: int | None = None
    heading_level: int = 0  # 0 = body/list/caption
    caption: bool = False


@dataclass(frozen=True, slots=True)
class DocumentTextIndex:
    text: str
    styles: tuple[CharStyle, ...]
    roles: tuple[TextRole, ...]
    segments: tuple[TextSegment, ...] = ()

    def __post_init__(self) -> None:
        n = len(self.text)
        if len(self.styles) != n or len(self.roles) != n:
            raise ValueError("text, styles, and roles must have equal length")

    def slice_plain(self, start: int, end: int) -> str:
        start = max(0, min(start, len(self.text)))
        end = max(start, min(end, len(self.text)))
        return self.text[start:end]


def _is_word_char(ch: str) -> bool:
    return bool(ch) and (ch.isalnum() or ch == "_")


def word_bounds_at_offset(text: str, offset: int) -> tuple[int, int] | None:
    """Return [start, end) word span around *offset*, or None if text is empty."""
    if not text:
        return None
    offset = max(0, min(offset, len(text)))
    if offset == len(text):
        offset -= 1
    if not _is_word_char(text[offset]):
        return offset, offset
    start = offset
    while start > 0 and _is_word_char(text[start - 1]):
        start -= 1
    end = offset + 1
    while end < len(text) and _is_word_char(text[end]):
        end += 1
    return start, end


def segment_bounds_at_offset(
    index: DocumentTextIndex,
    offset: int,
) -> tuple[int, int] | None:
    """Return [start, end) for the text segment (paragraph/heading/item) at *offset*.

    Clicks on inter-block separators resolve to the preceding segment when
    possible (same idea as caret-at-end for word selection).
    """
    if not index.segments:
        return None
    n = len(index.text)
    offset = max(0, min(offset, n))
    if offset == n and offset > 0:
        offset -= 1
    for seg in index.segments:
        if seg.start <= offset < seg.end:
            return seg.start, seg.end
    preceding: TextSegment | None = None
    for seg in index.segments:
        if seg.end <= offset:
            preceding = seg
        elif seg.start > offset:
            break
    if preceding is not None:
        return preceding.start, preceding.end
    first = index.segments[0]
    return first.start, first.end


class _TextIndexBuilder:
    def __init__(self) -> None:
        self._chars: list[str] = []
        self._styles: list[CharStyle] = []
        self._roles: list[TextRole] = []
        self._segments: list[TextSegment] = []

    def build(self) -> DocumentTextIndex:
        return DocumentTextIndex(
            text="".join(self._chars),
            styles=tuple(self._styles),
            roles=tuple(self._roles),
            segments=tuple(self._segments),
        )

    def _append_char(
        self,
        ch: str,
        *,
        style: CharStyle,
        role: TextRole,
    ) -> None:
        self._chars.append(ch)
        self._styles.append(style)
        self._roles.append(role)

    def _append_plain(
        self,
        text: str,
        *,
        style: CharStyle | None = None,
        role: TextRole | None = None,
    ) -> None:
        base_style = style or CharStyle(InlineKind.TEXT)
        base_role = role or TextRole(TextRoleKind.BODY)
        for ch in text:
            self._append_char(ch, style=base_style, role=base_role)

    def _append_spans(self, spans: tuple[InlineSpan, ...]) -> None:
        for span in spans:
            role = TextRole(TextRoleKind.BODY)
            style = CharStyle(span.kind, span.href)
            self._append_plain(span.text, style=style, role=role)

    def add_block_separator(self) -> None:
        if not self._chars:
            return
        sep_role = TextRole(TextRoleKind.SEPARATOR)
        sep_style = CharStyle(InlineKind.TEXT)
        self._append_char("\n", style=sep_style, role=sep_role)
        self._append_char("\n", style=sep_style, role=sep_role)

    def _begin_segment(self, *, heading_level: int = 0, caption: bool = False) -> int:
        return len(self._chars)

    def _end_segment(
        self,
        start: int,
        *,
        block_index: int,
        list_item_index: int | None = None,
        heading_level: int = 0,
        caption: bool = False,
    ) -> None:
        end = len(self._chars)
        if end > start:
            self._segments.append(
                TextSegment(
                    start=start,
                    end=end,
                    block_index=block_index,
                    list_item_index=list_item_index,
                    heading_level=heading_level,
                    caption=caption,
                )
            )

    def add_heading(self, block: HeadingBlock, block_index: int) -> None:
        self.add_block_separator()
        start = self._begin_segment(heading_level=block.level)
        role = TextRole(TextRoleKind.HEADING, heading_level=block.level)
        style = CharStyle(InlineKind.TEXT)
        self._append_plain(block.text, style=style, role=role)
        self._end_segment(start, block_index=block_index, heading_level=block.level)

    def add_paragraph(self, block: ParagraphBlock, block_index: int) -> None:
        self.add_block_separator()
        start = self._begin_segment()
        self._append_spans(block.spans)
        self._end_segment(start, block_index=block_index)

    def add_list_item(
        self,
        *,
        ordered: bool,
        index: int,
        spans: tuple[InlineSpan, ...],
        block_index: int,
        list_item_index: int,
    ) -> None:
        self.add_block_separator()
        start = self._begin_segment()
        prefix = f"{index}. " if ordered else "• "
        marker_role = TextRole(TextRoleKind.LIST_MARKER)
        marker_style = CharStyle(InlineKind.TEXT)
        self._append_plain(prefix, style=marker_style, role=marker_role)
        self._append_spans(spans)
        self._end_segment(
            start,
            block_index=block_index,
            list_item_index=list_item_index,
        )

    def add_image(self, block: ImageBlock, block_index: int) -> None:
        self.add_block_separator()
        start = self._begin_segment()
        text = block.alt or block.path
        self._append_plain(text)
        self._end_segment(start, block_index=block_index)

    def add_figure_caption(self, block: FigureBlock, block_index: int) -> None:
        self.add_block_separator()
        caption = block.caption or block.alt or block.path
        if not caption:
            return
        start = self._begin_segment(caption=True)
        self._append_plain(caption)
        self._end_segment(start, block_index=block_index, caption=True)


def build_text_index(blocks: tuple[HelpBlock, ...]) -> DocumentTextIndex:
    """Build a unified selectable text stream matching ``blocks_to_plain_text``."""
    builder = _TextIndexBuilder()
    for block_index, block in enumerate(blocks):
        if isinstance(block, HeadingBlock):
            builder.add_heading(block, block_index)
        elif isinstance(block, ParagraphBlock):
            builder.add_paragraph(block, block_index)
        elif isinstance(block, ListBlock):
            for item_index, item in enumerate(block.items, start=1):
                builder.add_list_item(
                    ordered=block.ordered,
                    index=item_index,
                    spans=item,
                    block_index=block_index,
                    list_item_index=item_index - 1,
                )
        elif isinstance(block, ImageBlock):
            builder.add_image(block, block_index)
        elif isinstance(block, FigureBlock):
            builder.add_figure_caption(block, block_index)
    return builder.build()


def plain_text_from_index(index: DocumentTextIndex) -> str:
    """Return page plain text (same as ``blocks_to_plain_text`` for valid indexes)."""
    return index.text


def assert_index_matches_blocks(blocks: tuple[HelpBlock, ...], index: DocumentTextIndex) -> None:
    expected = blocks_to_plain_text(blocks)
    if index.text != expected:
        raise AssertionError(
            f"text index mismatch:\nexpected: {expected!r}\ngot: {index.text!r}"
        )
