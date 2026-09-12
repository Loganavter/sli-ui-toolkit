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

import math
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
        y_margin: int = 0,
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
        # Fixed top inset for the first row (the vertical counterpart of
        # ``x_margin``). Defaults to 0 — existing hosts are unaffected.
        # Hosts with symmetric content padding (e.g. ListPanel) pass their
        # top margin so rows don't hug the content's top edge.
        self._y_margin = max(0, int(y_margin))
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
            self.rebind(force=True)
            return
        self._count = count
        if self._heights is not None:
            self._heights.set_count(count)
            self._measure_all()
        self.rebind(force=True)

    def set_row_height(self, height: int) -> None:
        self._row_height = max(1, int(height))
        self.rebind()

    def set_widget_height(self, height: int | None) -> None:
        """Update the row widget height (may be smaller than the pitch so
        rows keep visual gaps) + rebind. ``None`` falls back to the pitch.

        Hosts that rebuild rows at a new height (e.g. ListPanel repopulated
        from a different anchor) must call this alongside
        ``set_row_height`` — otherwise pooled rows keep the construction
        height, the content overflows by the delta, and a scrollbar appears
        over a list that actually fits.
        """
        height = None if height is None else max(1, int(height))
        if height == self._widget_height:
            return
        self._widget_height = height
        self.rebind()

    def set_overscan(self, rows: int) -> None:
        self._overscan = max(0, int(rows))
        self.rebind()

    def set_y_margin(self, margin: int) -> None:
        """Update the fixed top inset (e.g. on UI-scale change) + rebind."""
        margin = max(0, int(margin))
        if margin == self._y_margin:
            return
        self._y_margin = margin
        self.rebind()

    def set_x_margin(self, margin: int) -> None:
        """Update the horizontal inset (e.g. on UI-scale change) + rebind."""
        margin = max(0, int(margin))
        if margin == self._x_margin:
            return
        self._x_margin = margin
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
        if self._row_height is not None:
            bottom = top + self._widget_height_or_pitch()
            if index == self._count - 1:
                bottom += self._y_margin
        elif self._heights is not None:
            bottom = top + self._heights.height(index)
        else:
            bottom = top + 1
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
        # Content-local coordinates are already absolute (rows are
        # positioned absolutely; Qt moves the content widget itself) —
        # no scroll compensation here.
        if self._row_height is not None:
            index = (local.y() - self._y_margin) // self._row_height
        elif self._heights is not None:
            index = self._heights.index_at_offset(local.y())
        else:
            return -1
        return index if 0 <= index < self._count else -1

    # -------- sizing --------

    def _measure_all(self) -> None:
        if self._heights is None or self._height_provider is None:
            return
        for i in range(self._count):
            self._heights.set_height(i, self._height_provider(i))

    def _widget_height_or_pitch(self) -> int:
        if self._widget_height is not None:
            return self._widget_height
        return self._row_height or 0

    def _content_height(self) -> int:
        if self._row_height is not None:
            if self._count <= 0:
                return self._y_margin
            # Symmetric vertical insets: the top margin (y_offset of row 0)
            # is mirrored below the last widget, so the last row never hugs
            # the content's bottom edge. Only the inter-row pitch separates
            # rows — the last row contributes its widget height, not a full
            # pitch (its trailing spacing belongs between rows, not after
            # the list).
            return (
                2 * self._y_margin
                + (self._count - 1) * self._row_height
                + self._widget_height_or_pitch()
            )
        return self._heights.total() if self._heights is not None else 0

    def _viewport_height(self) -> int:
        return self._scroll_area.viewport().height()

    def _max_scroll(self) -> int:
        if self._row_height is not None:
            return max(0, self._content_height() - self._viewport_height())
        return self._heights.max_scroll(self._viewport_height()) if self._heights is not None else 0

    def _index_at(self, offset_px: int) -> int:
        if self._row_height is not None:
            if self._row_height <= 0:
                return 0
            return int((offset_px - self._y_margin) // self._row_height)
        return self._heights.index_at_offset(offset_px) if self._heights is not None else 0

    def _offset_of_index(self, index: int) -> int:
        if self._row_height is not None:
            return self._y_margin + index * self._row_height
        return self._heights.offset_of_index(index) if self._heights is not None else 0

    def _window(self) -> tuple[int, int]:
        if self._row_height is not None:
            if self._y_margin <= 0:
                return visible_window(
                    self._count, self._viewport_height(), self._row_height,
                    self._scroll_offset, self._overscan,
                )
            pitch = self._row_height
            viewport = self._viewport_height()
            if self._count <= 0 or pitch <= 0 or viewport <= 0:
                return (0, 0)
            # Content row i occupies [margin + i*pitch, margin + (i+1)*pitch):
            # shift the scroll origin by the margin and materialize one
            # extra row to cover the inset.
            first = max(0, (self._scroll_offset - self._y_margin) // pitch)
            visible = math.ceil(viewport / pitch) + 1
            start = max(0, first - self._overscan)
            end = min(self._count, first + visible + self._overscan)
            return (start, end)
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

    def rebind(self, *, force: bool = False) -> None:
        """Recompute scroll range, content height, and the visible window.

        ``force=True`` re-runs ``bind()`` for every row in the window (item
        data may have changed, e.g. after a rebuild). The default keeps
        already-bound rows in place and only binds rows entering the window
        — cheap scroll/resize/overscan changes, safe because ``bind``
        reflects item identity.
        """
        self._scroll_offset = max(0, min(self._scroll_offset, self._max_scroll()))
        self._sync_scrollbar()
        self._rebind_rows(reuse=not force)

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

    def _rebind_rows(self, *, reuse: bool = True) -> None:
        if self._count <= 0:
            self._pool.hide_all()
            self._index_to_widget.clear()
            self._last_window = (0, 0)
            return
        start, end = self._window()
        self._last_window = (start, end)
        row_h = self._row_height
        # Rows are positioned at ABSOLUTE content coordinates — the scroll
        # offset is NOT subtracted here. The host content widget lives
        # inside an OverlayScrollArea whose native scrollbar already moves
        # it by -value; subtracting the offset again scrolled every list at
        # 2x and parked ~2 pitches of dead space under the last row at max
        # scroll. (RowPool keeps its scroll_offset param for non-Qt-scrolled
        # hosts like the ComboBox overlay, which position relatively.)
        if row_h is None:
            self._pool.rebind(
                start, end, self._bind,
                row_height=1,
                x_margin=self._x_margin,
                height_fn=lambda idx: (
                    self._heights.height(idx) if self._heights is not None else 1
                ),
                offset_fn=lambda idx: self._offset_of_index(idx),
                reuse=reuse,
            )
        else:
            self._pool.rebind(
                start, end, self._bind,
                row_height=row_h,
                widget_height=self._widget_height,
                x_margin=self._x_margin,
                y_offset=self._y_margin,
                reuse=reuse,
            )
        self._index_to_widget = self._pool.indexed_widgets()