"""Paint laid-out help document body content."""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.coords import (
    fragment_index_to_layout,
    normalized_range,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.types import (
    LayoutResult,
    TextFragment,
)


def paint_layout(
    painter: QPainter,
    layout: LayoutResult,
    *,
    selection_start: int | None,
    selection_end: int | None,
    theme: ThemeManager,
) -> None:
    sel_a, sel_b = normalized_range(selection_start, selection_end)
    highlight = theme.try_get_color("accent")
    if highlight is None or not highlight.isValid():
        highlight = QColor(59, 130, 246, 80)
    else:
        highlight.setAlpha(80)

    _paint_tables(painter, layout, theme)

    for frag in layout.text_fragments:
        painter.save()
        painter.translate(frag.rect.topLeft())
        frag.layout.draw(painter, QPointF(0, 0))
        if sel_a is not None and sel_b is not None:
            _paint_selection(painter, frag, sel_a, sel_b, highlight)
        painter.restore()

    for pix in layout.pixmaps:
        if pix.pixmap is not None and not pix.pixmap.isNull():
            painter.drawPixmap(pix.rect.topLeft().toPoint(), pix.pixmap)
        else:
            painter.save()
            painter.setPen(theme.get_color("dialog.text"))
            fm = QFontMetrics(QFont())
            painter.drawText(pix.rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), pix.alt)
            painter.restore()


def _paint_tables(painter: QPainter, layout: LayoutResult, theme: ThemeManager) -> None:
    if not layout.tables:
        return
    border = theme.try_get_color("help.separator")
    if border is None or not border.isValid():
        border = theme.try_get_color("dialog.border")
    if border is None or not border.isValid():
        border = QColor(128, 128, 128, 160)
    painter.save()
    pen = painter.pen()
    pen.setColor(border)
    pen.setWidthF(1.0)
    painter.setPen(pen)
    for table in layout.tables:
        painter.drawRect(table.rect)
        for row_y in table.row_ys:
            painter.drawLine(
                QPointF(table.rect.left(), row_y), QPointF(table.rect.right(), row_y)
            )
        painter.drawLine(
            QPointF(table.col_x, table.rect.top()),
            QPointF(table.col_x, table.rect.bottom()),
        )
    painter.restore()


def _paint_selection(
    painter: QPainter,
    frag: TextFragment,
    sel_start: int,
    sel_end: int,
    color: QColor,
) -> None:
    overlap_start = max(sel_start, frag.global_start)
    overlap_end = min(sel_end, frag.global_end)
    if overlap_start >= overlap_end:
        return
    layout = frag.layout
    local_start = fragment_index_to_layout(frag, overlap_start)
    local_end = fragment_index_to_layout(frag, overlap_end)
    if local_end < local_start:
        local_start, local_end = local_end, local_start
    for li in range(layout.lineCount()):
        line = layout.lineAt(li)
        if not line.isValid():
            continue
        line_start = line.textStart()
        line_end = line_start + line.textLength()
        o_start = max(local_start, line_start)
        o_end = min(local_end, line_end)
        if o_start >= o_end:
            continue
        x1, _ = cast(tuple[float, int], line.cursorToX(o_start))
        x2, _ = cast(tuple[float, int], line.cursorToX(o_end))
        rect = QRectF(
            min(x1, x2),
            line.y(),
            abs(x2 - x1),
            line.height(),
        )
        painter.fillRect(rect, color)
