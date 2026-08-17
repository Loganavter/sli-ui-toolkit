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
    pos = 0
    for start, end, kind in spans:
        if start > pos:
            x = _draw_segment(painter, x, y, line[pos:start], base_color, font)
        color = colors.get(kind)
        if color is None:
            continue
        x = _draw_segment(
            painter,
            x,
            y,
            line[start:end],
            color,
            font,
            bold=(kind in bold_kinds),
        )
        pos = end
    if pos < len(line):
        x = _draw_segment(painter, x, y, line[pos:], base_color, font)
    return x


def _draw_segment(
    painter: QPainter,
    x: int,
    y: int,
    text: str,
    color,
    font: QFont,
    *,
    bold: bool = False,
) -> int:
    if not text:
        return x
    if bold:
        bold_font = QFont(font)
        bold_font.setBold(True)
        painter.setFont(bold_font)
    else:
        painter.setFont(font)
    painter.setPen(color)
    painter.drawText(x, y, text)
    return x + QFontMetrics(painter.font()).horizontalAdvance(text)
