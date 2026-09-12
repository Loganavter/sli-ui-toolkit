"""Text view composite: painted text rendering + editing.

File roles:

- ``widget.py`` — ``TextView``: public QScrollArea composite (rounded frame
  overlay, toolkit scrollbar, read/edit mode switch, document mode).
- ``canvas.py`` — ``TextCanvas``: the painted text surface that IS the
  editor (line model, cursor, selection, undo, clipboard; document mode).
- ``selection.py`` — the unified selection state machine: ``SelectionState``
  (anchor/focus, multi-click chain, drag threshold) + ``TextSelection``
  (code mode, ``(line, col)``) + ``DocumentSelection`` (document mode,
  offsets) — shared with the help-document canvas.
- ``painter.py`` — segment painting for one painted text line.
- ``highlight.py`` — Python syntax spans (``python_line_spans``) and the
  theme-aware span palette (``python_span_colors``).
- ``document.py`` — markdown blocks → painted document (help-document
  layout reuse).
- ``constants.py`` — shared sizing constants.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.text_view.canvas import TextCanvas
from sli_ui_toolkit.ui.widgets.composite.text_view.highlight import (
    python_line_spans,
    python_span_colors,
)
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
    blocks_to_plain_text,
    collect_heading_anchors,
    parse_help_blocks,
    parse_inline,
    spans_to_plain,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.selection import TextSelection
from sli_ui_toolkit.ui.widgets.composite.text_view.widget import TextView

__all__ = [
    "TextView",
    "TextCanvas",
    "TextSelection",
    "python_line_spans",
    "python_span_colors",
    "CodeBlock",
    "FigureBlock",
    "HeadingBlock",
    "HelpBlock",
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
