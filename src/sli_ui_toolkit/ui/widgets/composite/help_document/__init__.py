"""Widget-tree help document renderer (Blender-like illustrated pages).

The markdown/blocks/layout engine now lives in the sibling ``text_view``
composite (the unified painted-text system); this package re-exports the
same public names unchanged.
"""

from sli_ui_toolkit.ui.widgets.composite.text_view.markdown import (
    CodeBlock,
    FigureBlock,
    HeadingBlock,
    HelpBlock,
    ImageBlock,
    InlineKind,
    InlineSpan,
    ListBlock,
    ParagraphBlock,
    TableBlock,
    blocks_to_plain_text,
    collect_heading_anchors,
    parse_help_blocks,
    parse_inline,
    spans_to_plain,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.view import HelpDocumentView

__all__ = [
    "CodeBlock",
    "FigureBlock",
    "HeadingBlock",
    "HelpBlock",
    "HelpDocumentView",
    "ImageBlock",
    "InlineKind",
    "InlineSpan",
    "ListBlock",
    "ParagraphBlock",
    "TableBlock",
    "blocks_to_plain_text",
    "collect_heading_anchors",
    "parse_help_blocks",
    "parse_inline",
    "spans_to_plain",
]
