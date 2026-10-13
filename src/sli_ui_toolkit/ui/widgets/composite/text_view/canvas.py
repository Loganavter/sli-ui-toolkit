"""Delegate (text-p2c): implementation moved to ``sli_ui_toolkit.ui.widgets.text.engine.canvas``."""

from sli_ui_toolkit.ui.widgets.text.engine.canvas import (  # noqa: F401
    Any,
    DocumentSelection,
    Position,
    QColor,
    QEvent,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QPointF,
    QSizePolicy,
    QTimer,
    QWidget,
    Qt,
    Signal,
    TextSelection,
    ThemeManager,
    UiScale,
    _CanvasEditingApi,
    _CanvasEventsApi,
    _CanvasPaintApi,
    _SELECTION_EVENTS,
    _TEXTVIEW_DEBUG_VARS,
    _canvas_logger,
    _last_update_ts,
    _textview_debug,
    _textview_debug_enabled,
    _update_counter,
    any_flag,
    build_text_index,
    constants,
    hit_test_link,
    hit_test_pixmap,
    hit_test_text_offset,
    layout_document,
    logging,
    parse_help_blocks,
    time,
    traceback,
)
from sli_ui_toolkit.ui.widgets.text.engine.canvas import TextCanvasCore


class TextCanvas(TextCanvasCore):
    """Thin wrapper over ``TextCanvasCore`` (same behavior, same name)."""

__all__ = ['TextCanvas', 'Position']
