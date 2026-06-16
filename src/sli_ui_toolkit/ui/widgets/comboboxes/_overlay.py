from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.helpers import (
    calculate_centered_overlay_geometry,
    draw_rounded_shadow,
)

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.comboboxes.combo_box import ComboBox

logger = logging.getLogger(__name__)


class _SlotBgLayer(Layer):
    """Прозрачный фон, list_item.background.hover на hover/pressed."""

    def applies(self, ctx) -> bool:
        states = ctx.effective_states
        return ButtonState.HOVERED in states or ButtonState.PRESSED in states

    def draw(self, ctx, tm: ThemeManager) -> None:
        rect = ctx.rect.toRect().adjusted(0, 1, 0, -1)
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tm.get_color("list_item.background.hover")))
        p.drawRoundedRect(rect, 6, 6)


class _SlotContentLayer(Layer):
    """Текст слева с TEXT_HORIZONTAL_PADDING, эллипс справа."""

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        rect = ctx.rect.toRect()
        padding = widget._text_padding
        text_rect = rect.adjusted(padding, 0, -padding, 0)
        p = ctx.painter
        p.setPen(QPen(tm.get_color("dialog.text")))
        p.setFont(widget.font())
        fm = QFontMetrics(widget.font())
        elided = fm.elidedText(widget._text, Qt.TextElideMode.ElideRight, text_rect.width())
        p.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )


class _DropdownItemSlot(Button):
    """Один переиспользуемый «слот» строки в dropdown'е ComboBox'а.

    Виртуальный список держит K = maxVisibleItems слотов; при скролле/фильтре
    каждому слоту переназначается `(item_index, text)`.
    """

    def __init__(self, text_padding: int, parent: QWidget):
        super().__init__(
            text="",
            size=(0, 0),
            corner_radius=6,
            layers=[_SlotBgLayer(), RippleLayer(), _SlotContentLayer()],
            parent=parent,
        )
        self._text = ""
        self._item_index = -1
        self._text_padding = text_padding

    def bind(self, *, text: str, item_index: int) -> None:
        self._text = text
        self._item_index = item_index
        self.update()


class _DropdownOverlay(QWidget):
    RADIUS = 8
    SHADOW = 10
    GAP = 6

    def __init__(self, owner: "ComboBox", parent: QWidget):
        if parent is None:
            raise ValueError("_DropdownOverlay requires an in-window parent widget")
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self._owner = owner
        self._theme = owner._theme
        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar_width = 10
        self._scrollbar_gap = 0
        self._slots: list[_DropdownItemSlot] = []
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMouseTracking(True)
        self.custom_v_scrollbar.valueChanged.connect(self._on_scrollbar_value_changed)
        self.custom_v_scrollbar.setVisible(False)
        self.hide()

    def _item_height(self) -> int:
        return self._owner._item_height()

    def _visible_items(self) -> int:
        return self._owner._visible_items()

    def _visible_item_indices(self) -> list[int]:
        return self._owner._visible_indices()

    def _list_height(self) -> int:
        return self._visible_items() * self._item_height()

    def _content_rect(self) -> QRect:
        return self.rect().adjusted(self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW)

    def _has_scrollbar(self) -> bool:
        return len(self._visible_item_indices()) > self._owner.maxVisibleItems()

    def _list_rect(self) -> QRect:
        width = self._content_rect().width()
        if self._has_scrollbar():
            width -= self._scrollbar_width + self._scrollbar_gap
        return QRect(0, 0, max(0, width), self._list_height())

    def _item_rect(self, visible_index: int) -> QRect:
        list_rect = self._list_rect()
        return QRect(
            list_rect.x(),
            list_rect.y() + visible_index * self._item_height(),
            list_rect.width(),
            self._item_height(),
        )

    # -------- slot pool management --------

    def _ensure_slots(self, count: int) -> None:
        while len(self._slots) < count:
            slot = _DropdownItemSlot(
                text_padding=self._owner.TEXT_HORIZONTAL_PADDING, parent=self
            )
            slot.clicked.connect(lambda s=slot: self._on_slot_clicked(s))
            self._slots.append(slot)
        for extra in self._slots[count:]:
            extra.hide()

    def _rebind_slots(self) -> None:
        visible_count = self._visible_items()
        visible_indices = self._visible_item_indices()
        self._ensure_slots(visible_count)
        content_top_left = self._content_rect().topLeft()
        for visible_idx in range(visible_count):
            source_pos = self._owner._scroll_offset + visible_idx
            if source_pos >= len(visible_indices):
                break
            item_index = visible_indices[source_pos]
            item = self._owner._items[item_index]
            slot = self._slots[visible_idx]
            slot.bind(text=item.text, item_index=item_index)
            rect = self._item_rect(visible_idx).translated(content_top_left)
            slot.setGeometry(rect)
            slot.show()
        # Hide unused slots in this round.
        for slot in self._slots[visible_count:]:
            slot.hide()

    def _on_slot_clicked(self, slot: _DropdownItemSlot) -> None:
        idx = slot._item_index
        if idx >= 0:
            self._owner.setCurrentIndex(idx)
        self._owner.hideDropdown()

    # -------- show/position --------

    def show_for_owner(self):
        self._owner._ensure_current_visible()
        self._reposition()
        self._sync_scrollbar()
        self._rebind_slots()
        self.show()
        self.raise_()
        self.update()
        logger.debug(
            "[ComboBox.overlay.show] object=%s current=%d scroll_offset=%d visible=%d geom=(%d,%d,%d,%d)",
            self._owner.objectName() or "<unnamed>",
            self._owner.currentIndex(),
            self._owner._scroll_offset,
            self._visible_items(),
            self.x(),
            self.y(),
            self.width(),
            self.height(),
        )

    def _reposition(self):
        owner = self._owner
        window = self.parentWidget()
        if window is None:
            return

        outer = calculate_centered_overlay_geometry(
            anchor_widget=owner,
            owner_window=window,
            content_size=QSize(max(owner.width(), owner.minimumWidth()), self._list_height()),
            shadow_radius=self.SHADOW,
            current_index=owner.currentIndex(),
            visible_index=max(0, owner._visible_position_for_index(owner.currentIndex()) - owner._scroll_offset),
            row_height=self._item_height(),
            scrollable=len(self._visible_item_indices()) > owner.maxVisibleItems(),
        )
        self.setGeometry(outer)
        self._position_scrollbar()

    def _position_scrollbar(self):
        content = self._content_rect()
        if not self._has_scrollbar():
            self.custom_v_scrollbar.setVisible(False)
            return
        x = content.right() - self._scrollbar_width + 1
        self.custom_v_scrollbar.setGeometry(
            x,
            content.y(),
            self._scrollbar_width,
            content.height(),
        )
        self.custom_v_scrollbar.raise_()

    def _sync_scrollbar(self):
        max_offset = max(0, len(self._visible_item_indices()) - self._visible_items())
        if max_offset <= 0:
            self.custom_v_scrollbar.setVisible(False)
            return
        self.custom_v_scrollbar.blockSignals(True)
        self.custom_v_scrollbar.setRange(0, max_offset)
        self.custom_v_scrollbar.setPageStep(self._visible_items())
        self.custom_v_scrollbar.setSingleStep(1)
        self.custom_v_scrollbar.setValue(self._owner._scroll_offset)
        self.custom_v_scrollbar.blockSignals(False)
        self.custom_v_scrollbar.setVisible(True)
        self._position_scrollbar()

    def _on_scrollbar_value_changed(self, value: int):
        new_offset = max(0, min(int(value), max(0, len(self._visible_item_indices()) - self._visible_items())))
        if new_offset == self._owner._scroll_offset:
            return
        self._owner._scroll_offset = new_offset
        self._rebind_slots()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scrollbar()
        self._sync_scrollbar()

    def update(self):
        # ComboBox дёргает overlay.update() при изменении items/scroll/search →
        # пересвязываем слоты, чтобы текст и индексы соответствовали текущему окну.
        super().update()
        if self.isVisible():
            self._rebind_slots()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        content = QRectF(self._content_rect())
        draw_rounded_shadow(painter, content, steps=self.SHADOW, radius=self.RADIUS)

        bg = self._theme.get_color("flyout.background")
        border = self._theme.get_color("flyout.border")

        path = QPainterPath()
        path.addRoundedRect(content.adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)
        painter.setPen(QPen(border))
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)
        painter.end()
        # Сами строки отрисовывают child-Button-слоты.

    # -------- scrollbar pass-through --------

    def _forward_to_scrollbar(self, event: QMouseEvent) -> bool:
        if not (self.custom_v_scrollbar.isVisible() and self.custom_v_scrollbar.geometry().contains(
            event.position().toPoint()
        )):
            return False
        scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(event.globalPosition().toPoint())
        QApplication.sendEvent(
            self.custom_v_scrollbar,
            QMouseEvent(
                event.type(),
                QPointF(scrollbar_pos),
                event.globalPosition(),
                event.button(),
                event.buttons(),
                event.modifiers(),
            ),
        )
        event.accept()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._forward_to_scrollbar(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._forward_to_scrollbar(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._forward_to_scrollbar(event):
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        visible_count = len(self._visible_item_indices())
        if visible_count <= self._owner._max_visible_items:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._owner._scroll_offset = max(0, self._owner._scroll_offset - 1)
        elif delta < 0:
            self._owner._scroll_offset = min(
                visible_count - self._owner._max_visible_items,
                self._owner._scroll_offset + 1,
            )
        self._sync_scrollbar()
        self._rebind_slots()
        super().update()
        event.accept()
