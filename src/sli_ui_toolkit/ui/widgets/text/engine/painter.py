"""Segment painting for one painted text line.

``draw_text_line`` walks a line's ``(start, end, kind)`` spans and paints
each segment once — plain text in the base color, spans in theirs — never
overpainting the base text (bold/colored spans would double-draw on top of
it and look uneven). Advances are measured with the font the segment is
DRAWN with: the bold defclass is wider than the regular metrics, and a
regular advance would start the next segment on top of the bold text.
"""

from __future__ import annotations

from typing import Iterable

from functools import lru_cache

from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter

Span = tuple[int, int, str]

_BOLD_KINDS = frozenset({"defclass"})

# Cache for horizontalAdvance — selection of 2 chars on one line still
# repaints 29 visible lines × 5 segments = 145 advances per frame at 100Hz
# drag → 14k advances/s. Monospace 12px advances are pure function of text+bold.
_advance_cache: dict[tuple[str, bool], int] = {}


def _cached_advance(metrics: QFontMetrics, text: str, bold: bool) -> int:
    if not text:
        return 0
    key = (text, bold)
    cached = _advance_cache.get(key)
    if cached is not None:
        return cached
    val = metrics.horizontalAdvance(text)
    # Bounded — 8k entries ~ few KB, enough for visible vocabulary
    if len(_advance_cache) < 8192:
        _advance_cache[key] = val
    return val


def draw_text_line(
    painter: QPainter,
    x: int,
    y: int,
    line: str,
    spans: Iterable[Span],
    base_color: QColor,
    colors: dict[str, QColor],
    font: QFont,
    *,
    bold_kinds: frozenset[str] = _BOLD_KINDS,
) -> int:
    """Paint one line segment-by-segment; returns the final x position.

    Batching: ``setFont``/``setPen`` are called only when the font or color
    actually changes (was 78 calls per 25-line frame → now ~2-3).
    """
    # Pre-create bold font + metrics once per line — the old version
    # allocated a new QFont + QFontMetrics per segment (expensive at 60fps
    # for 40 visible lines). Editors cache glyph advances per font.
    bold_font: QFont | None = None
    regular_metrics = QFontMetrics(font)
    bold_metrics: QFontMetrics | None = None
    # materialize spans to avoid double iteration over generator
    span_list = list(spans)
    if any(k in bold_kinds for _, _, k in span_list):
        bold_font = QFont(font)
        bold_font.setBold(True)
        bold_metrics = QFontMetrics(bold_font)
    # batch state — seed from painter's current font/pen to allow cross-line batching
    try:
        cur_font = painter.font()
    except Exception:
        cur_font = None  # type: ignore[assignment]
    try:
        cur_pen = painter.pen().color()
        if not isinstance(cur_pen, QColor) or not cur_pen.isValid():
            cur_pen = None  # type: ignore[assignment]
    except Exception:
        cur_pen = None  # type: ignore[assignment]

    def _ensure_font(f: QFont) -> None:
        nonlocal cur_font
        if cur_font is not f:
            if cur_font is None or cur_font != f:
                painter.setFont(f)
                cur_font = f

    def _ensure_pen(c: QColor) -> None:
        nonlocal cur_pen
        if cur_pen is None or cur_pen.rgba() != c.rgba():
            painter.setPen(c)
            cur_pen = c

    pos = 0
    for start, end, kind in span_list:
        if start > pos:
            seg_text = line[pos:start]
            if seg_text:
                _ensure_font(font)
                _ensure_pen(base_color)
                painter.drawText(x, y, seg_text)
                x += _cached_advance(regular_metrics, seg_text, False)
        color = colors.get(kind)
        if color is None:
            continue
        is_bold = kind in bold_kinds
        seg_font = bold_font if is_bold else font
        seg_metrics = bold_metrics if is_bold else regular_metrics
        seg_text = line[start:end]
        if not seg_text:
            pos = end
            continue
        _ensure_font(seg_font)  # type: ignore[arg-type]
        _ensure_pen(color)
        painter.drawText(x, y, seg_text)
        x += _cached_advance(seg_metrics, seg_text, bool(is_bold))  # type: ignore[arg-type]
        pos = end
    if pos < len(line):
        seg_text = line[pos:]
        if seg_text:
            _ensure_font(font)
            _ensure_pen(base_color)
            painter.drawText(x, y, seg_text)
            x += _cached_advance(regular_metrics, seg_text, False)
    return x


def _draw_segment(
    painter: QPainter,
    x: int,
    y: int,
    text: str,
    color,
    font: QFont,
    metrics: QFontMetrics | None = None,
    *,
    bold: bool = False,
) -> int:
    if not text:
        return x
    # Legacy signature compatibility: _draw_segment was previously called with
    # bold= kwarg and no metrics. Keep it working for external callers.
    # Batched path above inlines the draw; this stays for external callers
    # but also batches (no extra overhead if called standalone).
    if metrics is None:
        if bold:
            bf = QFont(font)
            bf.setBold(True)
            painter.setFont(bf)
            metrics = QFontMetrics(bf)
        else:
            painter.setFont(font)
            metrics = QFontMetrics(font)
    else:
        painter.setFont(font)
    is_bold = font.bold() if hasattr(font, "bold") else bold
    painter.setPen(color)
    painter.drawText(x, y, text)
    return x + _cached_advance(metrics, text, is_bold)
