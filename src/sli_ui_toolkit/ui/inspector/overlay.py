"""Inspector overlay: highlight the selected/hovered widget, and for
Button-family widgets draw every region rect with the hovered region filled.

Overlays stay in-process children of the inspected window (Wayland-safe).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

_WIDGET_PEN = QColor("#ff2d7dff")
_REGION_PEN = QColor(255, 200, 60, 220)
_REGION_FILL = QColor(255, 200, 60, 40)


class InspectorOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("UiInspectorOverlay")
        self.setProperty("_ui_inspector_owned", True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._target_rect = QRectF()
        self._label = ""
        self._regions: list[tuple[str, QRectF]] = []
        self._hovered_region: str | None = None
        self.hide()

    def set_target(self, rect, label: str) -> None:
        self._target_rect = QRectF(rect)
        self._label = label
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.update()

    def set_regions(
        self, regions: list[tuple[str, object]], hovered: str | None = None
    ) -> None:
        """Region rects already mapped into overlay-local coordinates."""
        self._regions = [(rid, QRectF(r)) for rid, r in regions if r is not None]
        self._hovered_region = hovered
        self.update()

    def clear_target(self) -> None:
        self._target_rect = QRectF()
        self._label = ""
        self._regions = []
        self._hovered_region = None
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self._regions:
            self._paint_regions(painter)
        if not self._target_rect.isNull() and self._target_rect.isValid():
            painter.setPen(QPen(_WIDGET_PEN, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._target_rect.adjusted(1, 1, -2, -2))
            if self._label:
                self._draw_label(painter)

    def _paint_regions(self, painter: QPainter) -> None:
        for rid, rect in self._regions:
            if rid == self._hovered_region:
                painter.setPen(QPen(_REGION_PEN, 1))
                painter.setBrush(_REGION_FILL)
                painter.drawRect(rect.adjusted(1, 1, -2, -2))
            else:
                painter.setPen(QPen(_REGION_PEN, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(1, 1, -2, -2))

    def _draw_label(self, painter: QPainter) -> None:
        from sli_ui_toolkit.ui.managers.ui_font import ui_font

        painter.setFont(ui_font())
        metrics = QFontMetrics(painter.font())
        padding_x = 8
        padding_y = 5
        label_width = metrics.horizontalAdvance(self._label) + padding_x * 2
        label_height = metrics.height() + padding_y * 2
        x = int(self._target_rect.left())
        y = int(self._target_rect.top()) - label_height - 4
        if y < 4:
            y = int(self._target_rect.bottom()) + 4
        x = max(4, min(x, self.width() - label_width - 4))
        y = max(4, min(y, self.height() - label_height - 4))
        box = __import__("PySide6.QtCore", fromlist=["QRect"]).QRect(
            x, y, label_width, label_height
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(24, 24, 24, 230))
        painter.drawRoundedRect(box, 5, 5)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            box.adjusted(padding_x, padding_y, -padding_x, -padding_y),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._label,
        )
