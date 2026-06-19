from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, QPointF
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.ui.widgets.composite.sunburst_chart.models import SunburstSegmentData
from sli_ui_toolkit.ui.widgets.composite.sunburst_chart.segment_item import (
    SegmentSignals,
    SunburstSegmentItem,
)
from sli_ui_toolkit.theme import ThemeManager

class SunburstChartWidget(QWidget):
    """Generic sunburst/donut chart widget.

    Feed it a list of ``SunburstSegmentData`` via ``set_segments()``.
    Connect to signals for user interaction.
    """

    segment_clicked = Signal(str, int)
    segment_hover_enter = Signal(object, QPointF)
    segment_hover_move = Signal(object, QPointF)
    segment_hover_leave = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bg_color = QColor(30, 30, 30)
        self._gap_color: QColor | None = None
        self._center_text_color: QColor | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, False)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._view.setMinimumSize(0, 0)
        layout.addWidget(self._view)

        self._signals = SegmentSignals()
        self._signals.clicked.connect(self.segment_clicked.emit)
        self._signals.hover_enter.connect(self.segment_hover_enter.emit)
        self._signals.hover_move.connect(self.segment_hover_move.emit)
        self._signals.hover_leave.connect(self.segment_hover_leave.emit)

    def set_background_color(self, color: QColor) -> None:
        self._bg_color = QColor(color)
        self._view.setBackgroundBrush(QBrush(self._bg_color))

    def set_gap_color(self, color: QColor) -> None:
        self._gap_color = QColor(color)

    def set_center_text_color(self, color: QColor) -> None:
        self._center_text_color = QColor(color)

    def set_segments(
        self,
        segments: list[SunburstSegmentData],
        *,
        center_text: str = "",
        center_sub_text: str = "",
        center_font_scale: float = 1.0,
    ) -> None:
        self._scene.clear()
        self._view.setBackgroundBrush(QBrush(self._bg_color))

        for seg in segments:
            item = SunburstSegmentItem(seg, self._signals, gap_color=self._gap_color)
            self._scene.addItem(item)

        if center_text:
            inner_radius_norm = min(
                (seg.inner_radius for seg in segments), default=0.5
            )
            inner_radius_scene = inner_radius_norm * SunburstSegmentItem.SCENE_SCALE
            self._draw_center_text(
                center_text,
                center_sub_text,
                center_font_scale,
                inner_radius_scene,
            )

        bounds = self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)
        self._view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        QTimer.singleShot(0, self.fit_to_view)

    def clear(self) -> None:
        self._scene.clear()

    def fit_to_view(self) -> None:
        bounds = self._scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)
        self._view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._scene.items():
            self.fit_to_view()

    def _draw_center_text(
        self,
        text: str,
        sub_text: str,
        font_scale: float,
        inner_radius: float,
    ) -> None:
        text_color = self._resolved_center_text_color()
        sub_text_color = QColor(text_color)
        sub_text_color.setAlpha(210)

        max_width = max(20.0, inner_radius * 2.0 * 0.9)

        base_size = max(1, int(12 * font_scale))
        main_font = self._fit_font(text, base_size, bold=True, max_width=max_width)
        sub_font = None
        if sub_text:
            sub_base = max(8, main_font.pointSize() - 3)
            sub_font = self._fit_font(sub_text, sub_base, bold=False, max_width=max_width)

        main_text = self._elide(text, main_font, max_width)
        main_item = QGraphicsTextItem(main_text)
        main_item.setFont(main_font)
        main_item.setDefaultTextColor(text_color)
        main_metrics = QFontMetricsF(main_font)

        sub_item = None
        sub_metrics = None
        if sub_text and sub_font is not None:
            sub_text_fit = self._elide(sub_text, sub_font, max_width)
            sub_item = QGraphicsTextItem(sub_text_fit)
            sub_item.setFont(sub_font)
            sub_item.setDefaultTextColor(sub_text_color)
            sub_metrics = QFontMetricsF(sub_font)

        gap = (main_metrics.descent() + 2.0) if sub_item is not None else 0.0
        main_h = main_metrics.height()
        sub_h = sub_metrics.height() if sub_metrics is not None else 0.0
        total_h = main_h + gap + sub_h

        main_br = main_item.boundingRect()
        main_x = -main_br.width() / 2.0
        main_y = -total_h / 2.0 - (main_br.height() - main_h) / 2.0
        main_item.setPos(main_x, main_y)
        self._scene.addItem(main_item)

        if sub_item is not None:
            sub_br = sub_item.boundingRect()
            sub_x = -sub_br.width() / 2.0
            sub_y = main_y + main_br.height() + gap - (sub_br.height() - sub_h) / 2.0
            sub_item.setPos(sub_x, sub_y)
            self._scene.addItem(sub_item)

    @staticmethod
    def _fit_font(text: str, base_size: int, *, bold: bool, max_width: float) -> QFont:
        size = base_size
        floor = 6
        while size >= floor:
            font = QFont()
            font.setPointSize(size)
            font.setBold(bold)
            if QFontMetricsF(font).horizontalAdvance(text) <= max_width:
                return font
            size -= 1
        font = QFont()
        font.setPointSize(floor)
        font.setBold(bold)
        return font

    @staticmethod
    def _elide(text: str, font: QFont, max_width: float) -> str:
        metrics = QFontMetricsF(font)
        if metrics.horizontalAdvance(text) <= max_width:
            return text
        return metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(max_width))

    def _resolved_center_text_color(self) -> QColor:
        if self._center_text_color is not None:
            return QColor(self._center_text_color)
        color = ThemeManager.get_instance().try_get_color("dialog.text")
        if color is not None and color.isValid():
            return color
        luminance = 0.2126 * self._bg_color.red() + 0.7152 * self._bg_color.green() + 0.0722 * self._bg_color.blue()
        return QColor("#111111") if luminance > 170 else QColor("#ffffff")

    @property
    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def view(self) -> QGraphicsView:
        return self._view
