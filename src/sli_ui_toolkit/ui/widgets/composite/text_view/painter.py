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

from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter

Span = tuple[int, int, str]

_BOLD_KINDS = frozenset({"defclass"})


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
    """Paint one line segment-by-segment; returns the final x position."""
    # Pre-create bold font + metrics once per line — the old version
    # allocated a new QFont + QFontMetrics per segment (expensive at 60fps
    # for 40 visible lines). Editors cache glyph advances per font.
    bold_font: QFont | None = None
    regular_metrics = QFontMetrics(font)
    bold_metrics: QFontMetrics | None = None
    if any(k in bold_kinds for _, _, k in spans):
        bold_font = QFont(font)
        bold_font.setBold(True)
        bold_metrics = QFontMetrics(bold_font)
    pos = 0
    for start, end, kind in spans:
        if start > pos:
            x = _draw_segment(
                painter, x, y, line[pos:start], base_color, font, regular_metrics
            )
        color = colors.get(kind)
        if color is None:
            continue
        is_bold = kind in bold_kinds
        seg_font = bold_font if is_bold else font
        seg_metrics = bold_metrics if is_bold else regular_metrics
        x = _draw_segment(
            painter,
            x,
            y,
            line[start:end],
            color,
            seg_font,  # type: ignore[arg-type]
            seg_metrics,  # type: ignore[arg-type]
        )
        pos = end
    if pos < len(line):
        x = _draw_segment(painter, x, y, line[pos:], base_color, font, regular_metrics)
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
    painter.setPen(color)
    painter.drawText(x, y, text)
    return x + metrics.horizontalAdvance(text)
