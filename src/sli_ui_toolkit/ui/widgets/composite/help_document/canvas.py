"""Delegate (text-p2c): implementation moved to ``sli_ui_toolkit.ui.widgets.text.engine.document_canvas``."""

from sli_ui_toolkit.ui.widgets.text.engine.document_canvas import (  # noqa: F401
    AssetResolver,
    Callable,
    DocumentSelection,
    DocumentTextIndex,
    HelpBlock,
    LayoutResult,
    PARAGRAPH_TAB_STOP_PX,
    QGuiApplication,
    QKeySequence,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPoint,
    QPointF,
    QSize,
    QSizePolicy,
    QWidget,
    Qt,
    Signal,
    ThemeManager,
    UiScale,
    _AnchorMarker,
    _help_debug,
    _help_debug_enabled,
    _normalize_ws,
    any_flag,
    build_text_index,
    hit_test_link,
    hit_test_pixmap,
    hit_test_text_offset,
    layout_document,
    logger,
    logging,
    markdown_for_selection,
    paint_layout,
    re,
    unicodedata,
)
from sli_ui_toolkit.ui.widgets.text.engine.document_canvas import HelpDocumentBodyCore


class HelpDocumentBodyCanvas(HelpDocumentBodyCore):
    """Thin wrapper over ``HelpDocumentBodyCore`` (same behavior, same name)."""
