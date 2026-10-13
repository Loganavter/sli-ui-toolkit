"""Delegate (text-p2c): implementation moved to ``sli_ui_toolkit.ui.widgets.text.engine.document``."""

from sli_ui_toolkit.ui.widgets.text.engine.document import (  # noqa: F401
    HelpBlock,
    InlineKind,
    InlineSpan,
    parse_help_blocks,
    parse_inline,
    layout_document,
    paint_layout,
    build_text_index,
)

__all__ = ['HelpBlock', 'InlineKind', 'InlineSpan', 'build_text_index', 'layout_document', 'paint_layout', 'parse_help_blocks', 'parse_inline']
