from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import QEvent, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.comboboxes._models import _ComboItem
from sli_ui_toolkit.ui.widgets.comboboxes._overlay import _DropdownOverlay
from sli_ui_toolkit.ui.widgets.comboboxes._search import (
    match_score,
    normalize_for_search,
    visible_indices_normalized,
)

logger = logging.getLogger(__name__)


class _ComboFieldBgLayer(Layer):
    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        states = ctx.effective_states
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rectf = QRectF(ctx.rect).adjusted(0.5, 0.5, -0.5, -0.5)
        if ButtonState.PRESSED in states or widget._expanded:
            bg_color = QColor(tm.get_color("flyout.background"))
        elif ButtonState.HOVERED in states:
            bg_color = QColor(tm.get_color("list_item.background.hover"))
        else:
            bg_color = QColor(tm.get_color("dialog.input.background"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(rectf, widget.RADIUS, widget.RADIUS)
        pen_border = QPen(QColor(tm.get_color("input.border.thin")))
        pen_border.setWidthF(1.0)
        p.setPen(pen_border)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rectf, widget.RADIUS, widget.RADIUS)


class _ComboFieldContentLayer(Layer):
    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        current_text = widget.currentText()
        if not current_text:
            return
        is_disabled = ButtonState.DISABLED in ctx.effective_states
        text_color = QColor(tm.get_color("dialog.text"))
        if is_disabled:
            text_color.setAlpha(140 if tm.is_dark() else 120)
        rect = ctx.rect.toRect()
        fm = QFontMetrics(widget.font())
        inner_h = widget._item_height()
        inner_top = (rect.height() - inner_h) // 2
        text_rect = QRect(
            widget.TEXT_HORIZONTAL_PADDING,
            inner_top,
            rect.width() - 2 * widget.TEXT_HORIZONTAL_PADDING,
            inner_h,
        )
        display_text = current_text
        if widget._search_text and widget._expanded:
            display_text = f"{widget._search_text} -> {current_text}"
        p = ctx.painter
        p.setFont(widget.font())
        p.setPen(QPen(text_color))
        p.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            fm.elidedText(display_text, Qt.TextElideMode.ElideRight, text_rect.width()),
        )


class ComboBox(Button):
    currentIndexChanged = pyqtSignal(int)
    currentTextChanged = pyqtSignal(str)

    BASE_HEIGHT = 33
    RADIUS = 6
    ITEM_VERTICAL_PADDING = 12
    TEXT_HORIZONTAL_PADDING = 12

    def __init__(
        self,
        parent=None,
        *,
        wheel_requires_focus: bool = False,
    ):
        super().__init__(
            text="",
            size=(0, self.BASE_HEIGHT),
            corner_radius=self.RADIUS,
            wheel_requires_focus=wheel_requires_focus,
            layers=[
                _ComboFieldBgLayer(),
                RippleLayer(),
                _ComboFieldContentLayer(),
            ],
            parent=parent,
        )
        self._theme = ThemeManager.get_instance()
        self._items: list[_ComboItem] = []
        self._current_index = -1
        self._expanded = False
        self._max_visible_items = 12
        self._minimum_contents_length = 0
        self._scroll_offset = 0
        self._overlay: _DropdownOverlay | None = None
        self._overlay_parent: QWidget | None = None
        self._search_enabled = True
        self._search_text = ""
        self._visible_indices_cache: list[int] = []
        self._visible_positions_cache: dict[int, int] = {}
        self._visible_cache_dirty = True

        self.clicked.connect(self._on_field_clicked)

    def _item_height(self) -> int:
        return max(28, QFontMetrics(self.font()).height() + self.ITEM_VERTICAL_PADDING)

    def _invalidate_visible_cache(self) -> None:
        self._visible_cache_dirty = True
        self._visible_indices_cache = []
        self._visible_positions_cache = {}

    def _visible_items(self) -> int:
        return min(len(self._visible_indices()), self._max_visible_items)

    def _visible_position_for_index(self, index: int) -> int:
        self._visible_indices()
        return self._visible_positions_cache.get(index, 0)

    def _ensure_current_visible(self):
        visible = self._visible_indices()
        visible_count = len(visible)
        if visible_count <= self._max_visible_items or self._current_index < 0:
            self._scroll_offset = 0
            return
        try:
            visible_position = visible.index(self._current_index)
        except ValueError:
            self._scroll_offset = 0
            return
        if visible_position < self._scroll_offset:
            self._scroll_offset = visible_position
        elif visible_position >= self._scroll_offset + self._max_visible_items:
            self._scroll_offset = visible_position - self._max_visible_items + 1

    def count(self) -> int:
        return len(self._items)

    def addItem(self, text: str, userData: Any = None):
        self._items.append(_ComboItem(str(text), userData))
        if self._current_index == -1:
            self._current_index = 0
        self._invalidate_visible_cache()
        self.update()

    def addItems(self, texts: list[str] | tuple[str, ...]):
        for text in texts:
            self.addItem(text)

    def insertItem(self, index: int, text: str, userData: Any = None):
        index = max(0, min(int(index), len(self._items)))
        self._items.insert(index, _ComboItem(str(text), userData))
        if self._current_index == -1:
            self._current_index = 0
        elif index <= self._current_index:
            self._current_index += 1
        self._invalidate_visible_cache()
        self.update()

    def removeItem(self, index: int):
        if not (0 <= index < len(self._items)):
            return
        del self._items[index]
        if not self._items:
            self._current_index = -1
        elif self._current_index >= len(self._items):
            self._current_index = len(self._items) - 1
        elif index < self._current_index:
            self._current_index -= 1
        self._invalidate_visible_cache()
        self._scroll_offset = max(0, min(self._scroll_offset, max(0, self.count() - self._max_visible_items)))
        self.update()

    def clear(self):
        self.hideDropdown()
        self._items.clear()
        self._current_index = -1
        self._scroll_offset = 0
        self._search_text = ""
        self._invalidate_visible_cache()
        self.update()

    def currentIndex(self) -> int:
        return self._current_index

    def currentText(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index].text
        return ""

    def currentData(self) -> Any:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index].data
        return None

    def items(self) -> list[tuple[str, Any]]:
        return [(item.text, item.data) for item in self._items]

    def itemText(self, index: int) -> str:
        if 0 <= index < len(self._items):
            return self._items[index].text
        return ""

    def itemData(self, index: int) -> Any:
        if 0 <= index < len(self._items):
            return self._items[index].data
        return None

    def findText(self, text: str) -> int:
        for idx, item in enumerate(self._items):
            if item.text == text:
                return idx
        return -1

    @staticmethod
    def _normalize_for_search(text: str) -> str:
        return normalize_for_search(text)

    @classmethod
    def _match_score(cls, query: str, text: str) -> int | None:
        return match_score(query, text)

    def _visible_indices(self) -> list[int]:
        if self._visible_cache_dirty:
            normalized_items = [item.normalized_text for item in self._items]
            self._visible_indices_cache = visible_indices_normalized(
                normalized_items,
                search_enabled=self._search_enabled,
                search_text=self._search_text,
            )
            self._visible_positions_cache = {
                item_index: visible_pos for visible_pos, item_index in enumerate(self._visible_indices_cache)
            }
            self._visible_cache_dirty = False
        return self._visible_indices_cache

    def setSearchEnabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._search_enabled == enabled:
            return
        self._search_enabled = enabled
        if not enabled:
            self.clearSearch()
        self._invalidate_visible_cache()
        self.update()

    def isSearchEnabled(self) -> bool:
        return self._search_enabled

    def searchText(self) -> str:
        return self._search_text

    def clearSearch(self) -> None:
        if not self._search_text:
            return
        self._search_text = ""
        self._invalidate_visible_cache()
        self._scroll_offset = 0
        if self._expanded and self._overlay is not None:
            self._ensure_current_visible()
            self._overlay._sync_scrollbar()
            self._overlay.update()
        self.update()

    def _set_search_text(self, text: str) -> None:
        if not self._search_enabled:
            return
        new_text = str(text)
        if new_text == self._search_text:
            return
        self._search_text = new_text
        self._invalidate_visible_cache()
        visible = self._visible_indices()
        self._scroll_offset = 0
        if visible:
            self.setCurrentIndex(visible[0])
        if self._expanded and self._overlay is not None:
            self._ensure_current_visible()
            self._overlay._sync_scrollbar()
            self._overlay.update()
        self.update()

    def _move_visible_selection(self, step: int) -> bool:
        visible = self._visible_indices()
        if not visible:
            return False
        try:
            current_pos = visible.index(self._current_index)
        except ValueError:
            current_pos = 0
        new_pos = max(0, min(len(visible) - 1, current_pos + step))
        self.setCurrentIndex(visible[new_pos])
        return True

    def findData(self, data: Any) -> int:
        for idx, item in enumerate(self._items):
            if item.data == data:
                return idx
        return -1

    def setItemText(self, index: int, text: str):
        if not (0 <= index < len(self._items)):
            return
        self._items[index].text = str(text)
        self._items[index].normalized_text = normalize_for_search(text)
        self._invalidate_visible_cache()
        self.update()

    def setItemData(self, index: int, data: Any):
        if not (0 <= index < len(self._items)):
            return
        self._items[index].data = data

    def setCurrentData(self, data: Any):
        idx = self.findData(data)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def setCurrentText(self, text: str):
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def setCurrentIndex(self, index: int):
        if not (0 <= index < len(self._items)) or index == self._current_index:
            return
        self._current_index = index
        self._ensure_current_visible()
        self.update()
        if self._expanded and self._overlay is not None:
            self._overlay._sync_scrollbar()
            self._overlay.update()
        if not self.signalsBlocked():
            self.currentIndexChanged.emit(index)
            self.currentTextChanged.emit(self.currentText())

    def setMaxVisibleItems(self, count: int):
        self._max_visible_items = max(1, int(count))
        if self._expanded and self._overlay is not None:
            self._overlay.show_for_owner()

    def maxVisibleItems(self) -> int:
        return self._max_visible_items

    def setMinimumContentsLength(self, count: int):
        self._minimum_contents_length = max(0, int(count))
        self.updateGeometry()

    def setSizeAdjustPolicy(self, _policy):
        pass

    def _content_width_hint(self) -> int:
        fm = QFontMetrics(self.font())
        text_width = 0
        for item in self._items:
            text_width = max(text_width, fm.horizontalAdvance(item.text))
        if self._minimum_contents_length > 0:
            text_width = max(text_width, fm.horizontalAdvance("M" * self._minimum_contents_length))
        return max(100, text_width + 24)

    def sizeHint(self) -> QSize:
        return QSize(self._content_width_hint(), self.BASE_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(max(80, self._content_width_hint()), self.BASE_HEIGHT)

    def _field_rect(self) -> QRect:
        return QRect(0, 0, self.width(), self.BASE_HEIGHT)

    def _ensure_overlay(self):
        window = self.window()
        if window is None:
            return
        if self._overlay is None or self._overlay_parent is not window:
            if self._overlay is not None:
                self._overlay.deleteLater()
            self._overlay_parent = window
            self._overlay = _DropdownOverlay(self, window)

    def showDropdown(self):
        if self.count() == 0:
            return
        self._ensure_overlay()
        if self._overlay is None:
            return
        self._expanded = True
        self._pressed = False
        self._ensure_current_visible()
        logger.debug(
            "[ComboBox.showDropdown] object=%s current=%d count=%d scroll_offset=%d",
            self.objectName() or "<unnamed>",
            self.currentIndex(),
            self.count(),
            self._scroll_offset,
        )
        self._overlay.show_for_owner()
        self.update()
        QApplication.instance().installEventFilter(self)
        window = self.window()
        if window is not None:
            window.installEventFilter(self)

    def hideDropdown(self):
        if self._overlay is not None:
            self._overlay.hide()
        self._expanded = False
        self._pressed = False
        self.clearSearch()
        self.update()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        window = self.window()
        if window is not None:
            window.removeEventFilter(self)

    def _on_field_clicked(self):
        if self._expanded:
            self.hideDropdown()
        else:
            self.showDropdown()

    def keyPressEvent(self, event):
        if self._search_enabled and event.key() == Qt.Key.Key_Backspace:
            if self._search_text:
                self._set_search_text(self._search_text[:-1])
                event.accept()
                return

        event_text = event.text()
        is_plain_text_input = (
            self._search_enabled
            and bool(event_text)
            and event_text.isprintable()
            and not (
                event.modifiers()
                & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.MetaModifier
                )
            )
            and not (event.key() == Qt.Key.Key_Space and not self._search_text and not self._expanded)
        )
        if is_plain_text_input:
            if not self._expanded:
                self.showDropdown()
            self._set_search_text(self._search_text + event_text)
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._expanded:
                self.hideDropdown()
            else:
                self.showDropdown()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Escape and self._expanded:
            self.hideDropdown()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Down and self.count() > 0:
            self._move_visible_selection(1)
            event.accept()
            return

        if event.key() == Qt.Key.Key_Up and self.count() > 0:
            self._move_visible_selection(-1)
            event.accept()
            return

        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if not self.shouldHandleWheelEvent(event):
            return
        if not self.isEnabled() or self.count() <= 1:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            new_index = (self._current_index - 1 + self.count()) % self.count()
        elif delta < 0:
            new_index = (self._current_index + 1) % self.count()
        else:
            return
        self.setCurrentIndex(new_index)
        event.accept()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        next_widget = QApplication.focusWidget()
        logger.debug(
            "[ComboBox.focusOut] object=%s next=%s expanded=%r overlay_visible=%r",
            self.objectName() or "<unnamed>",
            type(next_widget).__name__ if next_widget is not None else None,
            self._expanded,
            self._overlay.isVisible() if self._overlay is not None else False,
        )
        if not self._expanded:
            return
        QTimer.singleShot(0, self._hide_dropdown_if_focus_left)

    def _is_dropdown_widget(self, widget) -> bool:
        current = widget
        while current is not None:
            if current is self or current is self._overlay:
                return True
            current = current.parentWidget() if hasattr(current, "parentWidget") else None
        return False

    def _hide_dropdown_if_focus_left(self):
        if not self._expanded:
            return
        app = QApplication.instance()
        next_widget = app.focusWidget() if app is not None else None
        window = self.window()
        if next_widget is not None and self._is_dropdown_widget(next_widget):
            return
        if window is not None and window.isActiveWindow():
            return
        self.hideDropdown()

    def eventFilter(self, watched, event):
        if not self._expanded or self._overlay is None:
            return super().eventFilter(watched, event)

        if watched is self.window() and event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
            self._overlay.show_for_owner()
            return False

        if event.type() in (
            QEvent.Type.WindowDeactivate,
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.Hide,
            QEvent.Type.Close,
        ):
            self.hideDropdown()
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            global_pos = event.globalPosition().toPoint()
            inside_field = self.rect().contains(self.mapFromGlobal(global_pos))
            inside_overlay = self._overlay.geometry().contains(self._overlay.parentWidget().mapFromGlobal(global_pos))
            if not inside_field and not inside_overlay:
                self.hideDropdown()
        return super().eventFilter(watched, event)
