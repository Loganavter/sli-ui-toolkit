"""Widget-tree help document renderer (Blender-like illustrated pages)."""

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
    collect_heading_anchors,
    parse_help_blocks,
    parse_inline,
    spans_to_plain,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.view import HelpDocumentView

__all__ = [
    "FigureBlock",
    "HeadingBlock",
    "HelpBlock",
    "HelpDocumentView",
    "ImageBlock",
    "InlineKind",
    "InlineSpan",
    "ListBlock",
    "ParagraphBlock",
    "blocks_to_plain_text",
    "collect_heading_anchors",
    "parse_help_blocks",
    "parse_inline",
    "spans_to_plain",
]
