"""Delegate (text-p2c): implementation moved to ``sli_ui_toolkit.ui.widgets.text.engine.layout.text_layout``."""

from sli_ui_toolkit.ui.widgets.text.engine.layout.text_layout import (  # noqa: F401
    cast,
    QPointF,
    QRectF,
    QFont,
    QTextCharFormat,
    QTextLayout,
    QTextOption,
    ThemeManager,
    InlineKind,
    InlineSpan,
    PARAGRAPH_TAB_STOP_PX,
    LinkHitBox,
    CharStyle,
    TextRole,
    TextRoleKind,
    styles_from_spans,
    text_layout_height,
    build_text_layout,
)
