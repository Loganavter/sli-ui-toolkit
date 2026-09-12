"""Top-level in-window overlay infrastructure.

The overlay fills its parent window, stays inside Qt's normal widget hierarchy,
and can host arbitrary child widgets from this toolkit or from the host app.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget


class OverlaySlot(Enum):
    """Relative widget placement around the anchor center."""

    CENTER = (0, 0)
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)
    UP_LEFT = (-1, -1)
    UP_RIGHT = (1, -1)
    DOWN_LEFT = (-1, 1)
    DOWN_RIGHT = (1, 1)


@dataclass(slots=True)
class OverlayItem:
    """Registered child widget metadata."""

    key: str | None
    widget: QWidget
    slot: OverlaySlot | None
    distance: int | None
    geometry: QRect | None


class TopLevelInWindowOverlay(QWidget):
    """A modal full-parent overlay that can host arbitrary widgets.

    Widgets can be placed either in an ``OverlaySlot`` around the anchor center
    or with an explicit geometry in overlay-local coordinates.
    """

    dismissed = Signal()

    def __init__(
        self,
        parent: QWidget,
        *,
        anchor: QWidget | None = None,
        close_on_background: bool = True,
        close_on_escape: bool = True,
        close_on_deactivate: bool = True,
        default_distance: int = 96,
    ):
        if parent is None:
            raise ValueError("TopLevelInWindowOverlay requires an in-window parent widget")
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._anchor = anchor
        self._close_on_background = close_on_background
        self._close_on_escape = close_on_escape
        self._close_on_deactivate = close_on_deactivate
        self._default_distance = default_distance
        self._items: list[OverlayItem] = []
        self._filters_installed = False
        self._filter_parent: QWidget | None = None
        self._filter_window: QWidget | None = None
        self.hide()

    def set_anchor(self, anchor: QWidget | None) -> None:
        self._anchor = anchor
        if self.isVisible():
            self.reposition()

    def add_widget(
        self,
        widget: QWidget,
        *,
        key: str | None = None,
        slot: OverlaySlot | None = OverlaySlot.CENTER,
        distance: int | None = None,
        geometry: QRect | None = None,
    ) -> QWidget:
        """Add any child widget to the overlay.

        ``geometry`` takes precedence over slot placement. When no explicit
        geometry is supplied, the widget keeps its current size if valid,
        otherwise its ``sizeHint()`` is used.
        """
        widget.setParent(self)
        item = OverlayItem(
            key=key,
            widget=widget,
            slot=slot,
            distance=distance,
            geometry=QRect(geometry) if geometry is not None else None,
        )
        self._items.append(item)
        widget.show()
        if self.isVisible():
            self.reposition()
        return widget

    def remove_widget(self, widget: QWidget) -> None:
        self._items = [item for item in self._items if item.widget is not widget]
        widget.hide()
        widget.setParent(None)

    def clear_widgets(self, *, delete: bool = False) -> None:
        items = list(self._items)
        self._items.clear()
        for item in items:
            item.widget.hide()
            if delete:
                item.widget.deleteLater()
            else:
                item.widget.setParent(None)

    def widget_for_key(self, key: str) -> QWidget | None:
        for item in self._items:
            if item.key == key:
                return item.widget
        return None

    def items(self) -> tuple[OverlayItem, ...]:
        return tuple(self._items)

    def show_overlay(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.reposition()
        self._install_filters()

    def dismiss(self, *, emit_signal: bool = True) -> None:
        if emit_signal:
            self.dismissed.emit()
        self.hide()

    def hideEvent(self, event):
        self._remove_filters()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reposition()

    def reposition(self) -> None:
        center = self._anchor_center()
        for item in self._items:
            if item.geometry is not None:
                item.widget.setGeometry(item.geometry)
                continue
            slot = item.slot or OverlaySlot.CENTER
            distance = item.distance if item.distance is not None else self._default_distance
            size = self._item_size(item.widget)
            dx, dy = slot.value
            target_center = QPoint(center.x() + dx * distance, center.y() + dy * distance)
            rect = QRect(QPoint(0, 0), size)
            rect.moveCenter(target_center)
            item.widget.setGeometry(self._clamp_rect(rect))

    def _item_size(self, widget: QWidget) -> QSize:
        size = widget.size()
        if size.width() <= 0 or size.height() <= 0:
            size = widget.sizeHint()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(1, 1)
        return size

    def _anchor_center(self) -> QPoint:
        if self._anchor is not None and self._anchor.isVisible():
            top_left = self.mapFromGlobal(self._anchor.mapToGlobal(QPoint(0, 0)))
            return QPoint(
                top_left.x() + self._anchor.width() // 2,
                top_left.y() + self._anchor.height() // 2,
            )
        return QPoint(self.width() // 2, self.height() // 2)

    def _clamp_rect(self, rect: QRect) -> QRect:
        result = QRect(rect)
        bounds = self.rect()
        if result.width() > bounds.width():
            result.setWidth(bounds.width())
        if result.height() > bounds.height():
            result.setHeight(bounds.height())
        if result.right() > bounds.right():
            result.moveRight(bounds.right())
        if result.left() < bounds.left():
            result.moveLeft(bounds.left())
        if result.bottom() > bounds.bottom():
            result.moveBottom(bounds.bottom())
        if result.top() < bounds.top():
            result.moveTop(bounds.top())
        return result

    def _install_filters(self) -> None:
        if self._filters_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._filter_parent = self.parentWidget()
        self._filter_window = self.window()
        if self._filter_parent is not None:
            self._filter_parent.installEventFilter(self)
        if self._filter_window is not None and self._filter_window is not self._filter_parent:
            self._filter_window.installEventFilter(self)
        self._filters_installed = True

    def _remove_filters(self) -> None:
        if not self._filters_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._filter_parent is not None:
            self._filter_parent.removeEventFilter(self)
        if self._filter_window is not None and self._filter_window is not self._filter_parent:
            self._filter_window.removeEventFilter(self)
        self._filter_parent = None
        self._filter_window = None
        self._filters_installed = False

    def keyPressEvent(self, event):
        if self._close_on_escape and event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._close_on_background:
            self.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def eventFilter(self, watched, event):
        et = event.type()
        if self._close_on_deactivate and et in (
            QEvent.Type.WindowDeactivate,
            QEvent.Type.ApplicationDeactivate,
        ):
            self.dismiss()
            return False
        parent = self.parentWidget()
        if parent is not None and watched is parent and et == QEvent.Type.Resize:
            self.setGeometry(parent.rect())
            self.reposition()
        return super().eventFilter(watched, event)
