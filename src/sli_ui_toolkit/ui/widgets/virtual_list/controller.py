"""VirtualListController — wires the window math + row pool to an
OverlayScrollArea.

The controller owns the content host widget's height, drives the scroll
area's native scrollbar (the custom MinimalistScrollBar mirrors it via
OverlayScrollArea's own plumbing), and rebinds the row pool on scroll,
resize, count changes, or an explicit filter change. Hosts provide a row
factory and a ``bind(index, widget)`` callback; everything else (which rows
exist, positioning, scrollbar range, overscan) is handled here.

Usage::

    controller = VirtualListController(
        scroll_area, host,
        factory=lambda: MyRow(parent=host),
        bind=lambda index, row: row.set_item(items[index]),
        row_height=36,
    )
    controller.set_count(len(items))
    controller.rebind()  # after the viewport has a size
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea

from .pool import BindFn, RowFactory, RowPool
from .window import MeasuredHeights, max_scroll_px, visible_window

HeightProvider = Callable[[int], int]


class VirtualListController(QObject):
    """See module docstring."""

    def __init__(
        self,
        scroll_area: OverlayScrollArea,
        host: QWidget,
        *,
        factory: RowFactory,
        bind: BindFn,
        row_height: int | None = None,
        height_provider: HeightProvider | None = None,
        overscan: int = 2,
        widget_height: int | None = None,
        x_margin: int = 0,
    ) -> None:
        if row_height is None and height_provider is None:
            raise ValueError("pass row_height or height_provider")
        super().__init__(scroll_area)
        self._scroll_area = scroll_area
        self._host = host
        self._factory = factory
        self._bind = bind
        self._row_height = int(row_height) if row_height is not None else None
        self._height_provider = height_provider
        self._overscan = max(0, int(overscan))
        self._widget_height = int(widget_height) if widget_height is not None else None
        self._x_margin = max(0, int(x_margin))
        self._count = 0
        self._scroll_offset = 0
        self._syncing = False
        self._last_window = (0, 0)
        self._pool = RowPool(host, factory)
        self._heights = MeasuredHeights() if height_provider is not None else None
        self._index_to_widget: dict[int, QWidget] = {}

        native = scroll_area.verticalScrollBar()
        native.valueChanged.connect(self._on_scroll_value)
        scroll_area.installEventFilter(self)

    # -------- configuration --------

    def set_count(self, count: int) -> None:
        count = max(0, int(count))
        if count == self._count and self._heights is None:
            self.rebind()
            return
        self._count = count
        if self._heights is not None:
            self._heights.set_count(count)
            self._measure_all()
        self.rebind()

    def set_row_height(self, height: int) -> None:
        self._row_height = max(1, int(height))
        self.rebind()

    def set_overscan(self, rows: int) -> None:
        self._overscan = max(0, int(rows))
        self.rebind()

    @property
    def count(self) -> int:
        return self._count

    @property
    def scroll_offset(self) -> int:
        return self._scroll_offset

    def window(self) -> tuple[int, int]:
        """The currently materialized half-open item window [start, end)."""
        return self._last_window

    def scroll_to(self, offset_px: int) -> None:
        native = self._scroll_area.verticalScrollBar()
        native.setValue(max(0, min(int(offset_px), self._max_scroll())))

    def ensure_visible(self, index: int) -> None:
        """Scroll minimally so item ``index`` enters the viewport."""
        if index < 0 or index >= self._count:
            return
        top = self._offset_of_index(index)
        bottom = top + (self._row_height or 1)
        viewport = self._viewport_height()
        if top < self._scroll_offset:
            self.scroll_to(top)
        elif bottom > self._scroll_offset + viewport:
            self.scroll_to(bottom - viewport)

    def widget_for_index(self, index: int) -> QWidget | None:
        return self._index_to_widget.get(index)

    def index_at(self, global_pos) -> int:
        """Item index under a global screen position, or -1 when out of range.

        Hit-testing hosts (drop targets, hover mapping) use this instead of
        iterating row widgets. Accepts ``QPoint`` or ``QPointF``.
        """
        point = global_pos
        if hasattr(global_pos, "toPoint"):
            point = global_pos.toPoint()
        local = self._host.mapFromGlobal(point)
        if not self._host.rect().contains(local):
            return -1
        offset_y = local.y() + self._scroll_offset
        if self._row_height is not None:
            index = offset_y // self._row_height
        elif self._heights is not None:
            index = self._heights.index_at_offset(offset_y)
        else:
            return -1
        return index if 0 <= index < self._count else -1

    # -------- sizing --------

    def _measure_all(self) -> None:
        if self._heights is None or self._height_provider is None:
            return
        for i in range(self._count):
            self._heights.set_height(i, self._height_provider(i))

    def _content_height(self) -> int:
        if self._row_height is not None:
            return self._count * self._row_height
        return self._heights.total() if self._heights is not None else 0

    def _viewport_height(self) -> int:
        return self._scroll_area.viewport().height()

    def _max_scroll(self) -> int:
        if self._row_height is not None:
            return max_scroll_px(self._count, self._viewport_height(), self._row_height)
        return self._heights.max_scroll(self._viewport_height()) if self._heights is not None else 0

    def _index_at(self, offset_px: int) -> int:
        if self._row_height is not None:
            if self._row_height <= 0:
                return 0
            return int(offset_px // self._row_height)
        return self._heights.index_at_offset(offset_px) if self._heights is not None else 0

    def _offset_of_index(self, index: int) -> int:
        if self._row_height is not None:
            return index * self._row_height
        return self._heights.offset_of_index(index) if self._heights is not None else 0

    def _window(self) -> tuple[int, int]:
        if self._row_height is not None:
            return visible_window(
                self._count, self._viewport_height(), self._row_height,
                self._scroll_offset, self._overscan,
            )
        return self._heights.visible_window(self._viewport_height(), self._scroll_offset, self._overscan)

    # -------- events --------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._scroll_area and event.type() == QEvent.Type.Resize:
            # The event filter runs BEFORE the scroll area processes the
            # resize, so the viewport is still the old size here. Defer the
            # rebind one event-loop tick so the new viewport height is read;
            # the receiver-context form cancels the timer if the controller
            # (and its widget tree) is destroyed first.
            QTimer.singleShot(0, self, self.rebind)
        return super().eventFilter(watched, event)

    def _on_scroll_value(self, value: int) -> None:
        if self._syncing:
            return
        self._scroll_offset = max(0, min(int(value), self._max_scroll()))
        self._rebind_rows()

    # -------- rebinding --------

    def rebind(self) -> None:
        """Recompute scroll range, content height, and the visible window."""
        self._scroll_offset = max(0, min(self._scroll_offset, self._max_scroll()))
        self._sync_scrollbar()
        self._rebind_rows()

    def _sync_scrollbar(self) -> None:
        native = self._scroll_area.verticalScrollBar()
        viewport = self._viewport_height()
        max_scroll = self._max_scroll()
        self._syncing = True
        try:
            native.blockSignals(True)
            native.setRange(0, max_scroll)
            native.setPageStep(max(1, viewport))
            native.setSingleStep(self._row_height or 1)
            native.setValue(self._scroll_offset)
            native.blockSignals(False)
        finally:
            self._syncing = False
        # Content height drives the scrollbar range and the custom bar's
        # visibility (OverlayScrollArea mirrors the native range). Ask the
        # scroll area to re-sync its custom bar explicitly instead of relying
        # solely on the resize event the height change happens to trigger.
        self._host.setMinimumHeight(self._content_height())
        self._host.setMaximumHeight(16777215)
        queue_sync = getattr(self._scroll_area, "_queue_scrollbar_sync", None)
        if callable(queue_sync):
            queue_sync()

    def _rebind_rows(self) -> None:
        if self._count <= 0:
            self._pool.hide_all()
            self._index_to_widget.clear()
            self._last_window = (0, 0)
            return
        start, end = self._window()
        self._last_window = (start, end)
        self._index_to_widget = {}
        row_h = self._row_height
        if row_h is None:
            row_h = 1
            self._pool.ensure(end - start)
            slots = self._pool.widgets()
            shown = 0
            for idx in range(start, end):
                widget = slots[shown]
                self._bind(idx, widget)
                self._index_to_widget[idx] = widget
                h = self._heights.height(idx) if self._heights is not None else 1
                widget.setGeometry(
                    self._x_margin,
                    self._offset_of_index(idx) - self._scroll_offset,
                    max(0, self._host.width() - 2 * self._x_margin),
                    h,
                )
                widget.show()
                widget.raise_()
                shown += 1
            for widget in slots[shown:]:
                widget.hide()
            return
        self._pool.rebind(
            start, end, self._bind,
            row_height=row_h, scroll_offset=self._scroll_offset,
            widget_height=self._widget_height, x_margin=self._x_margin,
        )
        slots = self._pool.widgets()
        for i, idx in enumerate(range(start, end)):
            self._index_to_widget[idx] = slots[i]