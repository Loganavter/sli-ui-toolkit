"""Plain-mode geometry: line layout, hit-testing and selection rects.

Glyphs are painted by ``QStyle.drawItemText`` (the same call ``QLabel`` makes),
so unselected text is pixel-identical to ``Label``. ``QTextLayout`` only answers
geometry questions (where a character sits, which character a point hits).
Its glyph placement differs by a pixel from ``drawItemText``, so it is never
used for painting.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QTextLayout, QTextLine, QTextOption

_LINE_SEPARATOR = "\u2028"


def horizontal_option(alignment: Qt.AlignmentFlag) -> Qt.AlignmentFlag:
    value = int(alignment)
    if value & int(Qt.AlignmentFlag.AlignRight):
        return Qt.AlignmentFlag.AlignRight
    if value & int(Qt.AlignmentFlag.AlignHCenter):
        return Qt.AlignmentFlag.AlignHCenter
    if value & int(Qt.AlignmentFlag.AlignJustify):
        return Qt.AlignmentFlag.AlignJustify
    return Qt.AlignmentFlag.AlignLeft


def build_layout(
    text: str,
    font: QFont,
    width: int,
    wrap: bool,
    alignment: Qt.AlignmentFlag,
) -> QTextLayout:
    # Same length as ``text`` so cursor offsets map 1:1 onto the display text.
    layout = QTextLayout(text.replace("\n", _LINE_SEPARATOR), font)
    option = QTextOption(horizontal_option(alignment))
    option.setWrapMode(
        QTextOption.WrapMode.WordWrap if wrap else QTextOption.WrapMode.NoWrap
    )
    layout.setTextOption(option)
    layout.beginLayout()
    line_width = max(1, int(width))
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(line_width)
    layout.endLayout()
    return layout


def hit_test(layout: QTextLayout, local: QPointF) -> int:
    """Cursor position (between characters) under ``local`` (layout space)."""
    count = layout.lineCount()
    if count == 0:
        return 0
    for index in range(count):
        line = layout.lineAt(index)
        if local.y() < line.y() + line.height():
            return int(line.xToCursor(local.x()))
    last = layout.lineAt(count - 1)
    return int(last.textStart() + last.textLength())


def hit_glyph(layout: QTextLayout, local: QPointF) -> bool:
    """True when ``local`` (layout space) lands on a glyph's advance box.

    Strict rule shared with the document/code engines (``_hit_text``): the
    I-beam shows only where characters stand, never across the empty widget.
    """
    count = layout.lineCount()
    if count == 0:
        return False
    for index in range(count):
        line = layout.lineAt(index)
        if local.y() < line.y() + line.height():
            if local.y() < line.y() or line.textLength() == 0:
                return False
            left = line.x()
            return left <= local.x() <= left + line.naturalTextWidth()
    return False


def _cursor_x(line: QTextLine, position: int) -> float:
    # PySide6 returns (x, adjusted_position); the stubs type it as object.
    x, _ = cast(tuple[float, int], line.cursorToX(position))
    return float(x)


def selection_rects(
    layout: QTextLayout, start: int, end: int, origin: QPointF
) -> list[QRectF]:
    rects: list[QRectF] = []
    for index in range(layout.lineCount()):
        line = layout.lineAt(index)
        first = line.textStart()
        last = first + line.textLength()
        lo = max(start, first)
        hi = min(end, last)
        if lo >= hi:
            continue
        x1 = _cursor_x(line, lo)
        x2 = _cursor_x(line, hi)
        rects.append(
            QRectF(
                origin.x() + min(x1, x2),
                origin.y() + line.y(),
                abs(x2 - x1),
                line.height(),
            )
        )
    return rects
