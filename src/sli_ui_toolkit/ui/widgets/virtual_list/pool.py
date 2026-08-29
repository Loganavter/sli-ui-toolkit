"""Reusable row-widget pool for virtual lists.

The pool owns a bounded set of row widgets and a rebind loop: for each item
index in the visible window, the host's ``bind(index, widget)`` callback
repopulates one pooled widget and the pool positions it inside the host
content widget. Widgets beyond the window are hidden. The host decides the
row look; the pool only manages creation/reuse/lifetime.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QWidget

RowFactory = Callable[[], QWidget]
BindFn = Callable[[int, QWidget], None]
HeightFn = Callable[[int], int]


class RowPool:
    def __init__(self, host: QWidget, factory: RowFactory) -> None:
        self._host = host
        self._factory = factory
        self._widgets: list[QWidget] = []
        self._slot_index: list[int | None] = []
        self._visible: int = 0

    def ensure(self, needed: int) -> None:
        """Grow the pool so it holds at least ``needed`` widgets."""
        needed = max(0, int(needed))
        while len(self._widgets) < needed:
            widget = self._factory()
            widget.setParent(self._host)
            widget.hide()
            self._widgets.append(widget)
            self._slot_index.append(None)

    def widgets(self) -> list[QWidget]:
        return self._widgets

    def visible_count(self) -> int:
        return self._visible

    def indexed_widgets(self) -> dict[int, QWidget]:
        """Item index → slot widget for the currently bound window."""
        return {
            idx: self._widgets[pos]
            for pos, idx in enumerate(self._slot_index)
            if idx is not None
        }

    def rebind(
        self,
        start_index: int,
        end_index: int,
        bind: BindFn,
        *,
        row_height: int,
        scroll_offset: int = 0,
        widget_height: int | None = None,
        x_margin: int = 0,
        height_fn: HeightFn | None = None,
        offset_fn: Callable[[int], int] | None = None,
        reuse: bool = False,
    ) -> None:
        """Bind item indices ``[start_index, end_index)`` to pool slots.

        Each visible slot is positioned at ``(x_margin,
        index*row_height - scroll_offset)`` and shown; surplus slots are
        hidden. ``bind(index, widget)`` runs for every shown slot so the host
        repopulates the row's content/state. ``row_height`` is the row
        *pitch* (index math); ``widget_height`` defaults to it and may be
        smaller when the host wants visual gaps between rows.

        With ``reuse=True`` slots already bound to an index still inside the
        window keep that index — they are only repositioned, and ``bind``
        runs just for rows entering the window. This keeps scroll/resize
        rebinds cheap (one bind per new row instead of per visible row) but
        is only safe when ``bind`` reflects *item identity*; hosts whose
        bind argument means something positional (e.g. a filtered-array
        position) must leave ``reuse=False`` (the default).
        ``height_fn``/``offset_fn`` override the per-row height and Y
        position for variable-height lists.
        """
        self.ensure(end_index - start_index)
        slots = self._widgets
        width = max(0, self._host.width() - 2 * x_margin)
        if reuse:
            keep = {
                idx: pos
                for pos, idx in enumerate(self._slot_index)
                if idx is not None and start_index <= idx < end_index
            }
        else:
            keep = {}
        free = [p for p in range(len(slots)) if p not in keep.values()]
        fi = 0
        new_slot_index: list[int | None] = [None] * len(slots)
        for idx in range(start_index, end_index):
            pos = keep.get(idx)
            if pos is None:
                pos = free[fi]
                fi += 1
                bind(idx, slots[pos])
                new_slot_index[pos] = idx
            else:
                new_slot_index[pos] = idx
            y = (
                offset_fn(idx)
                if offset_fn is not None
                else idx * row_height - scroll_offset
            )
            height = (
                height_fn(idx)
                if height_fn is not None
                else (widget_height if widget_height is not None else row_height)
            )
            slots[pos].setGeometry(QRect(x_margin, y, width, height))
            slots[pos].setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            slots[pos].show()
            slots[pos].raise_()
        for pos in range(end_index - start_index, len(slots)):
            slots[pos].hide()
        self._slot_index = new_slot_index
        self._visible = end_index - start_index

    def hide_all(self) -> None:
        for widget in self._widgets:
            widget.hide()
        self._slot_index = [None] * len(self._widgets)
        self._visible = 0

    def dispose(self) -> None:
        for widget in self._widgets:
            widget.setParent(None)
            widget.deleteLater()
        self._widgets = []
        self._slot_index = []
        self._visible = 0