from __future__ import annotations

from enum import Enum
import math
from typing import Any

from PyQt6.QtCore import QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QTabBar, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button


class CloseButtonPolicy(str, Enum):
    CURRENT_ONLY = "current_only"
    ALL = "all"
    ALL_WHEN_FIT_ELSE_CURRENT = "all_when_fit_else_current"


class _CloseButtonSlot(QWidget):
    def __init__(self, button: QWidget, *, vertical_offset: int = 1, parent=None):
        super().__init__(parent)
        self.button = button
        offset = int(vertical_offset)
        self.setFixedSize(button.width(), button.height() + abs(offset) * 2)
        button.setParent(self)
        button.move(0, max(0, offset * 2))


class _AdaptiveTabBar(QTabBar):
    _RADIUS = 8.0
    _MIN_WIDTH = 10
    _WIDTH_SCALE = 1.15
    _SIDE_PADDING = 12
    _HORIZONTAL_INSET = 2
    _TEXT_SAFETY = 6
    _CLOSE_GAP = 2
    _CLOSE_RIGHT_MARGIN = 2
    _TEXT_FADE = 26
    _SELECTED_SHADOW_OFFSET = 0.5
    _SELECTED_SHADOW_SPREAD = 1

    def __init__(self, *, close_button_width: int, parent=None):
        super().__init__(parent)
        self._close_button_width = int(close_button_width)
        self._visual_tab_height = 36
        self._hover_index = -1
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setMovable(False)
        self.setExpanding(False)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_visual_tab_height(self, height: int) -> None:
        self._visual_tab_height = max(1, int(height))
        self.updateGeometry()
        self.update()

    def tabSizeHint(self, index):  # noqa: N802
        size = super().tabSizeHint(index)
        width = (
            self.standard_tab_width(index)
            + self._close_button_width
            + self._CLOSE_GAP
        )
        return QSize(max(self._MIN_WIDTH, width), max(size.height(), self._visual_tab_height))

    def standard_tab_width(self, index: int) -> int:
        text_width = QFontMetrics(self.font()).horizontalAdvance(self.tabText(index))
        natural = (
            text_width
            + self._SIDE_PADDING * 2
            + self._HORIZONTAL_INSET
            + self._TEXT_SAFETY
        )
        return max(self._MIN_WIDTH, round(natural * self._WIDTH_SCALE))

    def full_tabs_width(self) -> int:
        return sum(
            self.standard_tab_width(index)
            + self._close_button_width
            + self._CLOSE_GAP
            for index in range(self.count())
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        self._position_tab_buttons()
        palette = self._palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(event.rect())
        painter.fillRect(self.rect(), QColor(palette["strip"]))
        for index in range(self.count()):
            if index != self.currentIndex():
                self._paint_visible_tab(painter, index, event.rect(), palette)
        if self.currentIndex() >= 0:
            self._paint_visible_tab(painter, self.currentIndex(), event.rect(), palette)

    def _paint_visible_tab(self, painter, index, exposed_rect, palette) -> None:
        rect = self.tabRect(index)
        if rect.isValid() and rect.intersects(exposed_rect):
            self._paint_tab(painter, index, rect, palette)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hover_index = self.tabAt(event.pos())
        if hover_index != self._hover_index:
            self._hover_index = hover_index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_index != -1:
            self._hover_index = -1
            self.update()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_tab_buttons()

    def tabLayoutChange(self) -> None:  # noqa: N802
        super().tabLayoutChange()
        self._position_tab_buttons()

    def _position_tab_buttons(self) -> None:
        for index in range(self.count()):
            slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if slot is None or not slot.isVisible():
                continue
            tab_rect = self._painted_tab_rect(self.tabRect(index))
            x = tab_rect.right() - slot.width() - self._CLOSE_RIGHT_MARGIN + 1
            y = tab_rect.center().y() - slot.height() // 2
            slot.move(x, y)

    def _painted_tab_rect(self, rect: QRect) -> QRect:
        height = min(rect.height(), self._visual_tab_height)
        top = rect.top() + max(0, (rect.height() - height) // 2)
        return QRect(rect.left() + 1, top, max(0, rect.width() - 2), height)

    def _paint_tab(self, painter: QPainter, index: int, rect: QRect, palette: dict[str, str]) -> None:
        selected = index == self.currentIndex()
        hovered = not selected and index == self._hover_index
        tab_rect = self._painted_tab_rect(rect)
        if selected:
            self._paint_selected_shadow(painter, tab_rect)
            self._paint_selected_background(painter, tab_rect, palette)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["hover"]))
            painter.drawRoundedRect(tab_rect, self._RADIUS, self._RADIUS)

        text_right = tab_rect.right() - self._SIDE_PADDING
        close_slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
        has_close = close_slot is not None and close_slot.isVisible()
        if has_close:
            text_right = min(text_right, close_slot.geometry().left() - self._CLOSE_GAP)
        text_rect = QRect(
            tab_rect.left() + self._SIDE_PADDING,
            tab_rect.top(),
            max(0, text_right - tab_rect.left() - self._SIDE_PADDING + 1),
            tab_rect.height(),
        )
        if text_rect.width() <= 0:
            return
        metrics = QFontMetrics(self.font())
        raw_text = self.tabText(index)
        needs_fade = has_close and metrics.horizontalAdvance(raw_text) > text_rect.width()
        text = raw_text if needs_fade else metrics.elidedText(
            raw_text, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.setPen(QColor(palette["text"]))
        painter.save()
        painter.setClipRect(text_rect)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()
        if needs_fade:
            fade = QLinearGradient(text_rect.right() - self._TEXT_FADE, 0, text_rect.right() + 1, 0)
            fade.setColorAt(0.0, QColor(0, 0, 0, 0))
            fade.setColorAt(1.0, QColor(palette["background"]))
            painter.fillRect(
                QRect(
                    text_rect.right() - self._TEXT_FADE,
                    tab_rect.top(),
                    self._TEXT_FADE + 1,
                    tab_rect.height(),
                ),
                fade,
            )

    def _paint_selected_background(self, painter, rect, palette) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette["background"]))
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)
        painter.setPen(QPen(QColor(palette["border"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, self._RADIUS, self._RADIUS)

    def _paint_selected_shadow(self, painter, rect) -> None:
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.save()
        painter.setClipRect(
            QRectF(
                rect.left() - 1,
                rect.bottom() - 1,
                rect.width() + 2,
                self._SELECTED_SHADOW_OFFSET + self._SELECTED_SHADOW_SPREAD + 3,
            )
        )
        painter.setPen(Qt.PenStyle.NoPen)
        soft_rect = QRectF(rect).adjusted(
            0,
            self._SELECTED_SHADOW_OFFSET,
            0,
            self._SELECTED_SHADOW_OFFSET + self._SELECTED_SHADOW_SPREAD,
        )
        painter.setBrush(QColor(0, 0, 0, 55))
        painter.drawRoundedRect(soft_rect, self._RADIUS, self._RADIUS)
        core_rect = QRectF(rect).adjusted(
            1,
            self._SELECTED_SHADOW_OFFSET - 1,
            -1,
            self._SELECTED_SHADOW_OFFSET,
        )
        painter.setBrush(QColor(0, 0, 0, 125))
        painter.drawRoundedRect(core_rect, self._RADIUS - 1, self._RADIUS - 1)
        painter.restore()

    def _palette(self) -> dict[str, str]:
        theme = ThemeManager.get_instance()

        def color(token: str, fallback: str) -> str:
            value = theme.try_get_color(token)
            return value.name() if value is not None and value.isValid() else fallback

        return {
            "strip": color("button.toggle.background.normal", "#f0f0f0"),
            "background": color("Window", "#ffffff"),
            "border": color("separator.color", "#e5e5e5"),
            "hover": color("button.toggle.background.hover", "#e6e6e6"),
            "text": color("WindowText", "#1f1f1f"),
        }


class AdaptiveTabStrip(QWidget):
    currentChanged = pyqtSignal(int)
    tabCloseRequested = pyqtSignal(int)
    addRequested = pyqtSignal()

    def __init__(
        self,
        *,
        add_icon: Any,
        close_icon: Any,
        close_policy: CloseButtonPolicy = CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT,
        single_tab_closable: bool = True,
        add_button_menu: list[tuple[str, Any]] | None = None,
        close_button_size: int = 28,
        close_icon_size: int = 16,
        close_button_vertical_offset: int = 1,
        margins: tuple[int, int, int, int] = (0, 4, 8, 4),
        spacing: int = 2,
        parent=None,
    ):
        super().__init__(parent)
        self.close_policy = CloseButtonPolicy(close_policy)
        self.single_tab_closable = bool(single_tab_closable)
        self._close_icon = close_icon
        self._close_button_size = int(close_button_size)
        self._close_icon_size = int(close_icon_size)
        self._close_button_vertical_offset = int(close_button_vertical_offset)
        self._updating_close_buttons = False

        self.tab_bar = _AdaptiveTabBar(
            close_button_width=self._close_button_size,
            parent=self,
        )
        self.add_button = Button(add_icon, menu=add_button_menu, parent=self)
        plus_height = max(
            self.add_button.sizeHint().height(),
            self.add_button.minimumHeight(),
            self.add_button.height(),
        )
        self.tab_bar.set_visual_tab_height(plus_height)
        self.tab_bar.setMinimumHeight(
            plus_height
            + math.ceil(
                self.tab_bar._SELECTED_SHADOW_OFFSET
                + self.tab_bar._SELECTED_SHADOW_SPREAD
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(*margins)
        layout.setSpacing(int(spacing))
        layout.addWidget(self.tab_bar)
        layout.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addStretch(1)

        self.tab_bar.currentChanged.connect(self._on_current_changed)
        self.add_button.clicked.connect(self.addRequested)

    def _on_current_changed(self, index: int) -> None:
        self.refresh_close_buttons()
        self.currentChanged.emit(index)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.refresh_close_buttons()

    def refresh_close_buttons(self) -> None:
        if self._updating_close_buttons:
            return
        self._updating_close_buttons = True
        try:
            count = self.count()
            show_all = self._should_show_all_close_buttons()
            for index in range(count):
                existing = self.tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
                should_show = self._should_show_close_button(index, count, show_all)
                if should_show and existing is None:
                    self.tab_bar.setTabButton(
                        index,
                        QTabBar.ButtonPosition.RightSide,
                        self._create_close_slot(),
                    )
                elif not should_show and existing is not None:
                    self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
        finally:
            self._updating_close_buttons = False

    def _should_show_all_close_buttons(self) -> bool:
        if self.close_policy is CloseButtonPolicy.ALL:
            return True
        if self.close_policy is CloseButtonPolicy.CURRENT_ONLY:
            return False
        margins = self.layout().contentsMargins()
        available = (
            self.contentsRect().width()
            - margins.left()
            - margins.right()
            - max(self.add_button.width(), self.add_button.sizeHint().width())
            - self.layout().spacing()
        )
        return self.tab_bar.full_tabs_width() <= available

    def _should_show_close_button(self, index: int, count: int, show_all: bool) -> bool:
        if count <= 0 or (count == 1 and not self.single_tab_closable):
            return False
        return show_all or index == self.currentIndex()

    def _create_close_slot(self) -> QWidget:
        button = Button(
            self._close_icon,
            size=(self._close_button_size, self._close_button_size),
            icon_size=self._close_icon_size,
            corner_radius=5,
            variant="ghost",
        )
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slot = _CloseButtonSlot(
            button,
            vertical_offset=self._close_button_vertical_offset,
            parent=self.tab_bar,
        )
        button.clicked.connect(lambda: self._emit_close_for_slot(slot))
        return slot

    def _emit_close_for_slot(self, slot: QWidget) -> None:
        for index in range(self.count()):
            if self.tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide) is slot:
                self.tabCloseRequested.emit(index)
                return

    # QTabBar-like compatibility surface.
    def addTab(self, text: str) -> int:  # noqa: N802
        index = self.tab_bar.addTab(text)
        self.refresh_close_buttons()
        return index

    def removeTab(self, index: int) -> None:  # noqa: N802
        self.tab_bar.removeTab(index)
        self.refresh_close_buttons()

    def count(self) -> int:
        return self.tab_bar.count()

    def currentIndex(self) -> int:  # noqa: N802
        return self.tab_bar.currentIndex()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        self.tab_bar.setCurrentIndex(index)

    def setTabData(self, index: int, data: Any) -> None:  # noqa: N802
        self.tab_bar.setTabData(index, data)

    def tabData(self, index: int) -> Any:  # noqa: N802
        return self.tab_bar.tabData(index)

    def setTabToolTip(self, index: int, text: str) -> None:  # noqa: N802
        self.tab_bar.setTabToolTip(index, text)

    def tabButton(self, index: int, position):  # noqa: N802
        return self.tab_bar.tabButton(index, position)

    def tabRect(self, index: int) -> QRect:  # noqa: N802
        return self.tab_bar.tabRect(index)

    def blockSignals(self, block: bool) -> bool:  # noqa: N802
        previous = super().blockSignals(block)
        self.tab_bar.blockSignals(block)
        return previous
