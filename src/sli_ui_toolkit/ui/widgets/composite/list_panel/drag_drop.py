"""Drop-target math (pure) + the insertion-indicator widget.

The drop indicator is a painted widget with no logic; the insertion-index
computation and the no-op-drop detection are pure functions of explicit
inputs (row geometries / drag payload), so they are testable without a
widget tree. The panel translates its layout into those inputs and applies
the results.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.helpers.multi_move import payload_indices


def drop_target_index(
    rows: list[tuple[int, QRect]], local_pos_y: int
) -> tuple[int, int]:
    """Insertion index + indicator Y for a cursor Y.

    ``rows`` is ``(layout_index, geometry)`` for the *visible* rows (the
    caller filters hidden ones, keeping original layout indices). Returns
    ``(dest_index, indicator_y)``: the index before which the drop lands,
    and the pixel line where the indicator should be drawn.
    """
    for index, geo in rows:
        if local_pos_y < geo.center().y():
            return index, geo.top()
    if rows:
        return rows[-1][0] + 1, rows[-1][1].bottom()
    return 0, 0


def should_hide_indicator(payload, list_num: int, dest_index: int) -> bool:
    """Whether the drop indicator should hide at ``dest_index``.

    True when the payload is a contiguous selection block from this same
    list and dropping at ``dest_index`` would be a no-op (the block already
    sits there).
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("list_num") != list_num:
        return False
    indices = payload_indices(payload)
    if not indices:
        return False
    lo, hi = indices[0], indices[-1]
    return lo <= dest_index <= hi + 1


class _DropIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor("#00b7ff")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.hide()

    def set_color(self, color: QColor):
        if color is None:
            color = QColor("#00b7ff")
        self._color = QColor(color)
        self._color.setAlpha(200)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if rect.isEmpty():
            return
        top_left = QPointF(rect.topLeft())
        top_right = QPointF(rect.topRight())
        gradient = QLinearGradient(top_left, top_right)
        middle = QColor(self._color)
        middle.setAlpha(200)
        transparent = QColor(middle)
        transparent.setAlpha(0)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.5, middle)
        gradient.setColorAt(1.0, transparent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
