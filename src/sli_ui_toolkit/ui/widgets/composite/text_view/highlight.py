"""Delegate (text-p2c): implementation moved to ``sli_ui_toolkit.ui.widgets.text.engine.highlight``."""

from sli_ui_toolkit.ui.widgets.text.engine.highlight import (  # noqa: F401
    re,
    lru_cache,
    QColor,
    PY_KEYWORDS,
    PY_BUILTINS,
    _KEYWORD_RE,
    _NUMBER_RE,
    _DECORATOR_RE,
    _TRIPLE_RE,
    _QUOTE_RE,
    _DEF_NAME_RE,
    python_line_spans,
    _cached_span_colors,
    python_span_colors,
)
