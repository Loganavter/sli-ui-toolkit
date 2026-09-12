"""Paint laid-out help document body content."""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.constants import (
    BODY_FONT_PX,
    CODE_HEADER_H,
    CODE_LABEL_FONT_PX,
    CODE_PAD_X,
    CODE_RADIUS,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.coords import (
    fragment_index_to_layout,
    normalized_range,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.types import (
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
    _paint_code_boxes(painter, layout, theme)

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
            # Scale-resolve the fallback alt text (plain drawText would use
            # the raw painter font, i.e. the unscaled design size).
            font = ui_font(pixel_size=BODY_FONT_PX)
            painter.setFont(font)
            painter.drawText(pix.rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), pix.alt)
            painter.restore()


def _paint_code_boxes(
    painter: QPainter, layout: LayoutResult, theme: ThemeManager
) -> None:
    """Shaded rounded box behind fenced code fragments + the fence language
    label in the box header (``help.code.background`` token; the token
    predates this painter and is only consumed here)."""
    boxes = [f for f in layout.text_fragments if f.code and f.code_box is not None]
    if not boxes:
        return
    background = theme.try_get_color("help.code.background")
    if background is None or not background.isValid():
        background = QColor(0, 0, 0, 13)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    # Every line of a code block shares the same ``code_box`` fragment, so
    # the box would be repainted once per line. The token is
    # semi-transparent — repeated strokes accumulate alpha and the shade
    # would depend on the block's line count. Paint each box exactly once.
    # (QRectF is not hashable; key on its geometry.)
    box_language: dict[tuple[float, float, float, float], str] = {}
    for frag in boxes:
        box = frag.code_box
        if box is None:
            continue
        key = (box.x(), box.y(), box.width(), box.height())
        box_language.setdefault(key, frag.code_language)
    for key in box_language:
        painter.drawRoundedRect(QRectF(*key), CODE_RADIUS, CODE_RADIUS)
    label_color = QColor(theme.get_color("dialog.text"))
    label_color.setAlpha(150)
    painter.setPen(label_color)
    painter.setFont(ui_font(pixel_size=CODE_LABEL_FONT_PX))
    for key, language in box_language.items():
        if not language:
            continue
        box = QRectF(*key)
        header = QRectF(
            box.left() + CODE_PAD_X,
            box.top(),
            max(1.0, box.width() - 2 * CODE_PAD_X),
            CODE_HEADER_H,
        )
        painter.drawText(
            header,
            int(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            ),
            language,
        )
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
        for col_x in table.col_xs:
            painter.drawLine(
                QPointF(col_x, table.rect.top()),
                QPointF(col_x, table.rect.bottom()),
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
