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


class RowPool:
    def __init__(self, host: QWidget, factory: RowFactory) -> None:
        self._host = host
        self._factory = factory
        self._widgets: list[QWidget] = []
        self._visible: int = 0

    def ensure(self, needed: int) -> None:
        """Grow the pool so it holds at least ``needed`` widgets."""
        needed = max(0, int(needed))
        while len(self._widgets) < needed:
            widget = self._factory()
            widget.setParent(self._host)
            widget.hide()
            self._widgets.append(widget)

    def widgets(self) -> list[QWidget]:
        return self._widgets

    def visible_count(self) -> int:
        return self._visible

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
    ) -> None:
        """Bind item indices ``[start_index, end_index)`` to pool slots.

        Each visible slot is positioned at ``(x_margin,
        index*row_height - scroll_offset)`` and shown; surplus slots are
        hidden. ``bind(index, widget)`` runs for every shown slot so the host
        repopulates the row's content/state. ``row_height`` is the row
        *pitch* (index math); ``widget_height`` defaults to it and may be
        smaller when the host wants visual gaps between rows.
        """
        self.ensure(end_index - start_index)
        slots = self._widgets
        shown = 0
        height = widget_height if widget_height is not None else row_height
        width = max(0, self._host.width() - 2 * x_margin)
        for idx in range(start_index, end_index):
            widget = slots[shown]
            bind(idx, widget)
            widget.setGeometry(
                QRect(x_margin, idx * row_height - scroll_offset, width, height)
            )
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            widget.show()
            widget.raise_()
            shown += 1
        for widget in slots[shown:]:
            widget.hide()
        self._visible = shown

    def hide_all(self) -> None:
        for widget in self._widgets:
            widget.hide()
        self._visible = 0

    def dispose(self) -> None:
        for widget in self._widgets:
            widget.setParent(None)
            widget.deleteLater()
        self._widgets = []
        self._visible = 0