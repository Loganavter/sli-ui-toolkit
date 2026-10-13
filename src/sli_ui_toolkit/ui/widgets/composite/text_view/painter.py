"""Delegate (text-p2c): implementation moved to ``sli_ui_toolkit.ui.widgets.text.engine.painter``."""

from sli_ui_toolkit.ui.widgets.text.engine.painter import (  # noqa: F401
    Iterable,
    lru_cache,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    Span,
    _BOLD_KINDS,
    _advance_cache,
    _cached_advance,
    draw_text_line,
    _draw_segment,
)
