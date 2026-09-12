from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen, QPolygon

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import (
    BackgroundLayer,
    RippleLayer,
)
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

logger = logging.getLogger(__name__)


class _ComboContentLayer(Layer):
    """Текст слева + chevron справа. Заменяет дефолтный ContentLayer."""

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter
        rect = ctx.effective_rect.toRect()

        is_disabled = ButtonState.DISABLED in ctx.effective_states
        text_color = QColor(tm.get_color("dialog.text"))
        if is_disabled:
            text_color.setAlpha(140 if tm.is_dark() else 120)

        font = widget.getItemFont()
        p.setFont(font)
        p.setPen(QPen(text_color))
        fm = QFontMetrics(font)
        text_rect = QRect(
            rect.x() + 12,
            rect.y(),
            max(0, rect.width() - 12 - 28),
            rect.height(),
        )
        elided = fm.elidedText(
            widget._text, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        p.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        p.setPen(QPen(text_color, 1.5))
        center_x = rect.x() + rect.width() - 14
        center_y = rect.center().y()
        p.drawPolyline(
            QPolygon(
                [
                    QPoint(center_x - 4, center_y - 1),
                    QPoint(center_x, center_y + 2),
                    QPoint(center_x + 4, center_y - 1),
                ]
            )
        )


class ScrollableComboBox(Button):
    currentIndexChanged = Signal(int)
    wheelScrolledToIndex = Signal(int)

    def __init__(self, parent=None, *, wheel_requires_focus: bool = False):
        super().__init__(
            text="",
            variant="surface",
            size=(0, 33),
            corner_radius=6,
            wheel_requires_focus=wheel_requires_focus,
            layers=[BackgroundLayer(), RippleLayer(), _ComboContentLayer()],
            parent=parent,
        )
        self._current_index = -1
        self._count = 0
        self._text = ""
        self._items: list[str] = []
        self._auto_width = False
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._apply_debounced_index)
        self._pending_index = -1
        self.setMinimumWidth(0)

    # ---------------- auto-width ----------------

    def setAutoWidthEnabled(self, enabled: bool):
        self._auto_width = bool(enabled)
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def showEvent(self, event):
        super().showEvent(event)
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def _adjustWidthToContent(self):
        if not self._auto_width:
            return
        fm = QFontMetrics(self.getItemFont())
        max_text_w = 0
        for item_text in self._items:
            w = fm.horizontalAdvance(str(item_text))
            if w > max_text_w:
                max_text_w = w
        current_text_w = fm.horizontalAdvance(self._text or "")
        if current_text_w > max_text_w:
            max_text_w = current_text_w
        needed = max(80, max_text_w + 60)
        if self.width() != int(needed):
            self.setFixedWidth(int(needed))
            self.updateGeometry()

    # ---------------- state ----------------

    def count(self):
        return self._count

    def currentIndex(self):
        return self._current_index

    def currentText(self):
        return self._text

    def setText(self, text: str):
        self._text = text
        self.update()
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def setCurrentIndex(self, index: int):
        if 0 <= index < self._count and index != self._current_index:
            self._current_index = index
            if 0 <= index < len(self._items):
                self._text = self._items[index]
            self.update()
            if self._auto_width:
                QTimer.singleShot(0, self._adjustWidthToContent)
            self.currentIndexChanged.emit(index)

    def updateState(
        self, count: int, current_index: int, text: str = "", items: list = None
    ):
        self._count = count
        self._current_index = current_index
        if text:
            self._text = text
        if items is not None:
            self._items = items[:]
        self.update()
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    def addItem(self, text: str):
        self._items.append(text)
        self._count = len(self._items)
        if self._auto_width:
            QTimer.singleShot(0, self._adjustWidthToContent)

    # ---------------- popup integration hooks ----------------

    def getItemFont(self) -> QFont:
        return self.font()

    def getItemHeight(self) -> int:
        return self.height() - 2

    # ---------------- wheel ----------------

    def _apply_debounced_index(self):
        if self._pending_index != -1 and self._pending_index != self.currentIndex():
            self.wheelScrolledToIndex.emit(self._pending_index)
        self._pending_index = -1

    def wheelEvent(self, event):
        if not self.shouldHandleWheelEvent(event):
            return
        if not self.isEnabled() or self.count() <= 1:
            event.ignore()
            return
        start_index = (
            self._pending_index
            if self._debounce_timer.isActive()
            else self.currentIndex()
        )
        delta = event.angleDelta().y()
        if delta > 0:
            new_index = (start_index - 1 + self.count()) % self.count()
        elif delta < 0:
            new_index = (start_index + 1) % self.count()
        else:
            return
        if new_index != start_index:
            self._pending_index = new_index
            if 0 <= new_index < len(self._items):
                self._text = self._items[new_index]
            self._debounce_timer.start()
            self.update()
            event.accept()

    # ---------------- misc ----------------

    def changeEvent(self, event: QEvent):
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange):
            self.updateGeometry()
            if self._auto_width:
                QTimer.singleShot(0, self._adjustWidthToContent)
        super().changeEvent(event)

    # Compat: старая реализация хранила timestamp открытия flyout. Сохраним
    # внешний контракт, но time-tracking упростим — Button сам управляет hover.
    def setFlyoutOpen(self, is_open: bool):
        if is_open:
            self._flyout_open_timestamp = time.time()
        else:
            self._flyout_open_timestamp = 0.0
        super().setFlyoutOpen(is_open)
