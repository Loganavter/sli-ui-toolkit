"""Document mode: markdown blocks → painted QTextLayout document.

Reuses the help-document layout machinery (blocks parser, text index,
``QTextLayout``-based builder, paint pass) — the TextView's document mode is
read-only and non-interactive; editing stays in code mode.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.text_view.markdown import (
    HelpBlock,
    InlineKind,
    InlineSpan,
    parse_help_blocks,
    parse_inline,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.builder import (
    layout_document,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.paint import (
    paint_layout,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.text_index import (
    build_text_index,
)

__all__ = [
    "HelpBlock",
    "InlineKind",
    "InlineSpan",
    "build_text_index",
    "layout_document",
    "paint_layout",
    "parse_help_blocks",
    "parse_inline",
]
