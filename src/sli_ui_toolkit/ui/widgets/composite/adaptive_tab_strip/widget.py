from __future__ import annotations

from enum import Enum
import math
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QTabBar, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.painter import default_layers


class _CloseButtonTabBackgroundLayer(Layer):
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        slot = ctx.widget.parentWidget()
        tab_bar = slot.parentWidget() if slot is not None else None
        color = None
        if hasattr(tab_bar, "close_slot_background_color"):
            color = tab_bar.close_slot_background_color(slot)
        if color is None or color.alpha() <= 0:
            return
        ctx.painter.fillRect(ctx.rect, color)


class CloseButtonPolicy(str, Enum):
    CURRENT_ONLY = "current_only"
    ALL = "all"
    ALL_WHEN_FIT_ELSE_CURRENT = "all_when_fit_else_current"


class _CloseButtonSlot(QWidget):
    def __init__(self, button: QWidget, *, vertical_offset: int = 1, parent=None):
        super().__init__(parent)
        self.button = button
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        button.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        button.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        button.setAutoFillBackground(False)
        self.setMouseTracking(True)
        button.setMouseTracking(True)
        offset = int(vertical_offset)
        self.setFixedSize(button.width(), button.height() + abs(offset) * 2)
        button.setParent(self)
        button.move(0, max(0, offset * 2))
        button.installEventFilter(self)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.button and event.type() in (
            QEvent.Type.Enter,
            QEvent.Type.MouseMove,
            QEvent.Type.Leave,
        ):
            tab_bar = self.parentWidget()
            if hasattr(tab_bar, "set_hover_from_global"):
                if event.type() == QEvent.Type.Leave:
                    global_pos = QCursor.pos()
                elif hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                else:
                    global_pos = self.button.mapToGlobal(event.pos())
                tab_bar.set_hover_from_global(global_pos)
                if event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove):
                    self._force_button_hover_region(global_pos)
        return super().eventFilter(watched, event)

    def enterEvent(self, event):  # noqa: N802
        self._sync_parent_hover("slot-enter")
        super().enterEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        self._sync_parent_hover("slot-move")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._sync_parent_hover("slot-leave")
        super().leaveEvent(event)

    def _sync_parent_hover(self, reason: str) -> None:
        tab_bar = self.parentWidget()
        if not hasattr(tab_bar, "set_hover_from_global"):
            return
        global_pos = QCursor.pos()
        tab_bar.set_hover_from_global(global_pos)

    def _force_button_hover_region(self, global_pos) -> None:
        update_hover_region = getattr(self.button, "_update_hover_region", None)
        if update_hover_region is None:
            return
        local_pos = self.button.mapFromGlobal(global_pos)
        if not self.button.rect().contains(local_pos):
            return
        update_hover_region(QPointF(local_pos))


class _AdaptiveTabBar(QWidget):
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
    _TEXT_HEIGHT_PADDING = 16

    currentChanged = Signal(int)
    tabContextMenuRequested = Signal(int, QPoint)

    def __init__(self, *, close_button_width: int, parent=None):
        super().__init__(parent)
        self._close_button_width = int(close_button_width)
        self._visual_tab_height = 36
        self._hover_index = -1
        self._current_index = -1
        self._scroll_offset = 0
        # Each entry: {"text": str, "data": Any, "tooltip": str, "buttons": {QTabBar.ButtonPosition: QWidget|None}}
        self._tabs: list[dict] = []
        self._rects: list[QRect] = []
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_visual_tab_height(self, height: int) -> None:
        self._visual_tab_height = max(1, int(height))
        self.updateGeometry()
        self.update()

    # -- tab collection management (QTabBar-compatible surface) --------

    def addTab(self, text: str) -> int:  # noqa: N802
        return self.insertTab(len(self._tabs), text)

    def insertTab(self, index: int, text: str) -> int:  # noqa: N802
        index = max(0, min(int(index), len(self._tabs)))
        self._tabs.insert(index, {"text": text, "data": None, "tooltip": "", "buttons": {}})
        self._rects.insert(index, QRect())
        previous_current = self._current_index
        if self._current_index == -1:
            self._current_index = index
        elif index <= self._current_index:
            self._current_index += 1
        self._relayout()
        self.updateGeometry()
        self.update()
        if self._current_index != previous_current:
            self.currentChanged.emit(self._current_index)
        return index

    def removeTab(self, index: int) -> None:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return
        entry = self._tabs.pop(index)
        self._rects.pop(index)
        for widget in entry["buttons"].values():
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        previous_current = self._current_index
        if not self._tabs:
            self._current_index = -1
        elif index < self._current_index:
            self._current_index -= 1
        elif index == self._current_index:
            self._current_index = min(index, len(self._tabs) - 1)
        self._relayout()
        self.updateGeometry()
        self.update()
        if self._current_index != previous_current:
            self.currentChanged.emit(self._current_index)

    def count(self) -> int:
        return len(self._tabs)

    def currentIndex(self) -> int:  # noqa: N802
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if index == self._current_index or not (0 <= index < len(self._tabs)):
            return
        self._current_index = index
        self._ensure_visible(index)
        self._position_tab_buttons()
        self.update()
        self.currentChanged.emit(index)

    def tabText(self, index: int) -> str:  # noqa: N802
        return self._tabs[index]["text"]

    def setTabText(self, index: int, text: str) -> None:  # noqa: N802
        self._tabs[index]["text"] = text
        self._relayout()
        self.updateGeometry()
        self.update()

    def tabData(self, index: int) -> Any:  # noqa: N802
        return self._tabs[index]["data"]

    def setTabData(self, index: int, data: Any) -> None:  # noqa: N802
        self._tabs[index]["data"] = data

    def tabToolTip(self, index: int) -> str:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return ""
        return self._tabs[index]["tooltip"]

    def setTabToolTip(self, index: int, text: str) -> None:  # noqa: N802
        self._tabs[index]["tooltip"] = text

    def tabButton(self, index: int, position) -> QWidget | None:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return None
        return self._tabs[index]["buttons"].get(position)

    def setTabButton(self, index: int, position, widget: QWidget | None) -> None:  # noqa: N802
        existing = self._tabs[index]["buttons"].get(position)
        if existing is not None and existing is not widget:
            existing.hide()
            existing.setParent(None)
            existing.deleteLater()
        self._tabs[index]["buttons"][position] = widget
        if widget is not None:
            widget.setParent(self)
            widget.show()
        self._position_tab_buttons()

    def tabAt(self, pos: QPoint) -> int:  # noqa: N802
        for index, rect in enumerate(self._visual_rects()):
            if rect.contains(pos):
                return index
        return -1

    def tabRect(self, index: int) -> QRect:  # noqa: N802
        if not (0 <= index < len(self._rects)):
            return QRect()
        return self._rects[index].translated(-self._scroll_offset, 0)

    # -- sizing ----------------------------------------------------------

    def standard_tab_width(self, index: int) -> int:
        text_width = QFontMetrics(self.font()).horizontalAdvance(self._tabs[index]["text"])
        natural = (
            text_width
            + self._SIDE_PADDING * 2
            + self._HORIZONTAL_INSET
            + self._TEXT_SAFETY
        )
        return max(self._MIN_WIDTH, round(natural * self._WIDTH_SCALE))

    def _tab_width(self, index: int) -> int:
        return self.standard_tab_width(index) + self._close_button_width + self._CLOSE_GAP

    def full_tabs_width(self) -> int:
        return sum(self._tab_width(index) for index in range(len(self._tabs)))

    def _tab_height(self) -> int:
        native = QFontMetrics(self.font()).height() + self._TEXT_HEIGHT_PADDING
        return max(native, self._visual_tab_height)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.full_tabs_width(), self._tab_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._MIN_WIDTH, self._tab_height())

    # -- layout / scrolling ----------------------------------------------

    def _relayout(self) -> None:
        x = 0
        for index in range(len(self._tabs)):
            width = self._tab_width(index)
            self._rects[index] = QRect(x, 0, width, self._tab_height())
            x += width
        self._clamp_scroll_offset()
        self._position_tab_buttons()

    def _max_scroll_offset(self) -> int:
        total = self._rects[-1].right() + 1 if self._rects else 0
        return max(0, total - self.width())

    def _clamp_scroll_offset(self) -> None:
        self._scroll_offset = max(0, min(self._scroll_offset, self._max_scroll_offset()))

    def _visual_rects(self) -> list[QRect]:
        return [rect.translated(-self._scroll_offset, 0) for rect in self._rects]

    def _ensure_visible(self, index: int) -> None:
        if not (0 <= index < len(self._rects)):
            return
        rect = self._rects[index]
        if rect.left() - self._scroll_offset < 0:
            self._scroll_offset = rect.left()
        elif rect.right() - self._scroll_offset > self.width():
            self._scroll_offset = rect.right() - self.width()
        self._clamp_scroll_offset()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._max_scroll_offset() <= 0:
            super().wheelEvent(event)
            return
        delta = event.pixelDelta()
        dx = delta.x()
        dy = delta.y()
        if dx == 0 and dy == 0:
            angle = event.angleDelta()
            dx = angle.x()
            dy = angle.y()
        step = -(dx if dx != 0 else dy) / 120 * 40
        if step == 0:
            super().wheelEvent(event)
            return
        self._scroll_offset += round(step)
        self._clamp_scroll_offset()
        self._position_tab_buttons()
        self.update()
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = self._palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(event.rect())
        painter.fillRect(self.rect(), QColor(palette["strip"]))
        for index in range(len(self._tabs)):
            if index != self._current_index:
                self._paint_visible_tab(painter, index, event.rect(), palette)
        if self._current_index >= 0:
            self._paint_visible_tab(painter, self._current_index, event.rect(), palette)

    def _paint_visible_tab(self, painter, index, exposed_rect, palette) -> None:
        rect = self.tabRect(index)
        if rect.isValid() and rect.intersects(exposed_rect):
            self._paint_tab(painter, index, rect, palette)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.tabAt(event.position().toPoint())
            if index >= 0:
                self.setCurrentIndex(index)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            pos = event.position().toPoint()
            index = self.tabAt(pos)
            if index >= 0 and not self._close_slot_contains(index, pos):
                if hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                else:
                    global_pos = self.mapToGlobal(pos)
                self.tabContextMenuRequested.emit(index, global_pos)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def _close_slot_contains(self, index: int, pos: QPoint) -> bool:
        slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if slot is None or not slot.isVisible():
            return False
        return slot.geometry().contains(pos)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._set_hover_index(self.tabAt(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def set_hover_from_global(self, global_pos) -> None:
        local_pos = self.mapFromGlobal(global_pos)
        hover_index = self.tabAt(local_pos) if self.rect().contains(local_pos) else -1
        self._set_hover_index(hover_index)

    def _set_hover_index(self, index: int) -> None:
        if index != self._hover_index:
            self._hover_index = index
            self.update()
            self._update_close_slots()

    def _update_close_slots(self) -> None:
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if slot is not None:
                slot.update()
                button = getattr(slot, "button", None)
                if button is not None:
                    button.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_index != -1:
            self._hover_index = -1
            self.update()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._clamp_scroll_offset()
        self._position_tab_buttons()

    def _position_tab_buttons(self) -> None:
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if slot is None:
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

    def close_slot_background_color(self, slot: QWidget) -> QColor | None:
        for index in range(self.count()):
            if self.tabButton(index, QTabBar.ButtonPosition.RightSide) is not slot:
                continue
            if index == self.currentIndex():
                return QColor(self._palette()["background"])
            if index == self._hover_index:
                return QColor(self._palette()["hover"])
            return QColor(self._palette()["strip"])
        return None

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
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)
    tabContextMenuRequested = Signal(int, QPoint)
    addRequested = Signal()

    def __init__(
        self,
        *,
        add_icon: Any,
        close_icon: Any,
        close_policy: CloseButtonPolicy = CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT,
        single_tab_closable: bool = True,
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
        self.add_button = Button(add_icon, parent=self)
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
        self.tab_bar.tabContextMenuRequested.connect(self.tabContextMenuRequested)
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
            layers=[_CloseButtonTabBackgroundLayer(), *default_layers()],
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
        self.layout().activate()
        self.refresh_close_buttons()
        return index

    def insertTab(self, index: int, text: str) -> int:  # noqa: N802
        index = self.tab_bar.insertTab(index, text)
        self.layout().activate()
        self.refresh_close_buttons()
        return index

    def removeTab(self, index: int) -> None:  # noqa: N802
        self.tab_bar.removeTab(index)
        self.layout().activate()
        self.refresh_close_buttons()

    def replaceTab(self, index: int, text: str) -> int:  # noqa: N802
        """Swap the tab at ``index`` for a new one without a visible
        intermediate frame.

        A naive ``removeTab`` followed by ``addTab``/``insertTab`` briefly
        changes the tab count, which shifts every tab after ``index`` to
        close the gap and then shifts them back once the replacement is
        inserted. Disabling updates for the whole swap guarantees only the
        final layout is ever painted, instead of a transient reflow frame.
        """
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            self.tab_bar.removeTab(index)
            new_index = self.tab_bar.insertTab(index, text)
            self.layout().activate()
            self.refresh_close_buttons()
        finally:
            self.setUpdatesEnabled(updates_were_enabled)
        if updates_were_enabled:
            self.update()
        return new_index

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

    def tabText(self, index: int) -> str:  # noqa: N802
        return self.tab_bar.tabText(index)

    def setTabText(self, index: int, text: str) -> None:  # noqa: N802
        self.tab_bar.setTabText(index, text)

    def tabButton(self, index: int, position):  # noqa: N802
        return self.tab_bar.tabButton(index, position)

    def tabRect(self, index: int) -> QRect:  # noqa: N802
        return self.tab_bar.tabRect(index)

    def blockSignals(self, block: bool) -> bool:  # noqa: N802
        previous = super().blockSignals(block)
        self.tab_bar.blockSignals(block)
        return previous
