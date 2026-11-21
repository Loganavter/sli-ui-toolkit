"""A compact flat text list — the toolkit's answer to a stock `QListWidget` of names.

`IconListWidget` is a *navigation* list: one `Button` per row, 44 px rows, a gutter and a plate behind each row. That is
the right control for a sidebar and the wrong one for a queue of file names: a host migrating such a queue measured
+3.2 % on the page because the row chrome is a different control, not a different style of the same one.

`TextListWidget` is the missing row type: text rows of a stated height, no per-row plate, one painted selection band,
hover feedback, scrolling when the rows overflow, and the handful of calls a `QListWidget` host makes
(``addItem``/``insertItem``/``takeItem``/``clear``/``count``/``itemText``/``currentRow``/``setCurrentRow``). The plate
behind the whole list is a theme token, so no stylesheet is involved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.atomic.surface_panel import SurfacePanel

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


#: `QListWidget`'s own default size hint. NOT scaled: the stock widget reports this box at every UI scale, and a
#: migrating layout was laid out against it - scaling it multiplied the hint by the live factor and the list clamped to
#: its own maximum instead (measured: 335 px where the stock is 256).
_STOCK_LIST_HINT = (256, 192)


class _Rows(QWidget):
    """The painted rows: the whole model, drawn inside the scroll area's content widget."""

    def __init__(self, owner: "TextListWidget") -> None:
        super().__init__()
        self._owner = owner
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(0, self._owner.content_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802
        self._owner.paint_rows(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        row = self._owner.row_at(event.position().y())
        if row is not None:
            self._owner.setCurrentRow(row)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        row = self._owner.row_at(event.position().y())
        if row != self._owner._hover_row:
            self._owner._hover_row = row
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._owner._hover_row is not None:
            self._owner._hover_row = None
            self.update()
        super().leaveEvent(event)


class TextListWidget(SurfacePanel):
    """Compact flat list of text rows on a token plate (no per-row plate, no stylesheet)."""

    currentRowChanged = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        row_height: int = 22,
        padding: tuple[int, int, int, int] | None = None,
        surface_token: str | None = "surface.list",
        radius: int = 10,
        scrollbar_width: int | None = None,
        text_pixel_size: int = 12,
    ) -> None:
        super().__init__(parent, background_token=surface_token, radius=radius)
        self.widget_descriptor: "WidgetDescriptor | None" = None
        self._items: list[str] = []
        self._current = -1
        self._hover_row: int | None = None
        self._row_height = max(8, scaled_px(row_height))
        self._padding = tuple(scaled_px(v) for v in (padding or (6, 4, 6, 4)))
        self._text_pixel_size = max(1, int(text_pixel_size))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # No layout inset: the plate IS the widget, and its rounded corners are painted by `SurfacePanel`. Insetting by
        # the radius shrank the plate by 20 px inside its own rect - measured on an empty queue list, whose whole visible
        # content is that plate (2.7 % against the stock 1.4 %).
        self._scroll = OverlayScrollArea(self, reserve_scrollbar_space=True)
        if scrollbar_width is not None:
            self._scroll.set_scrollbar_width(scrollbar_width)
        self._rows = _Rows(self)
        self._scroll.setWidget(self._rows)
        # The rows paint their own band; the scroll area must not put a plate behind them.
        self._scroll.viewport().setAutoFillBackground(False)
        self._rows.setAutoFillBackground(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._scroll)

    # -- model ----------------------------------------------------------

    def count(self) -> int:
        return len(self._items)

    def itemText(self, index: int) -> str:  # noqa: N802 - QListWidget spelling
        return self._items[index] if 0 <= index < len(self._items) else ""

    def addItem(self, text: str) -> None:  # noqa: N802
        self.insertItem(len(self._items), text)

    def insertItem(self, index: int, text: str) -> None:  # noqa: N802
        index = max(0, min(int(index), len(self._items)))
        self._items.insert(index, str(text))
        if self._current >= index:
            self._current += 1
        self._resize_rows()

    def takeItem(self, index: int) -> str | None:  # noqa: N802
        if not 0 <= index < len(self._items):
            return None
        removed = self._items.pop(int(index))
        if self._current == index:
            self._current = -1
            self.currentRowChanged.emit(-1)
        elif self._current > index:
            self._current -= 1
        self._resize_rows()
        return removed

    def clear(self) -> None:
        self._items.clear()
        self._current = -1
        self._resize_rows()
        self.currentRowChanged.emit(-1)

    def setItems(self, items) -> None:  # noqa: N802
        self._items = [str(item) for item in items]
        self._current = -1
        self._resize_rows()
        self.currentRowChanged.emit(-1)

    def currentRow(self) -> int:  # noqa: N802
        return self._current

    def setCurrentRow(self, index: int) -> None:  # noqa: N802
        index = int(index)
        if index < -1 or index >= len(self._items):
            return
        if index == self._current:
            return
        self._current = index
        self._rows.update()
        self.currentRowChanged.emit(index)

    # -- geometry -------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """The stock `QListWidget`'s own default (256x192, scaled).

        A migrating layout was laid out against that box: with any other hint the list takes a different share of the
        row and squeezes its neighbour - measured on a queue page where the button column lost 79 px to the list and the
        output list grew 48 px taller.
        """
        return QSize(*_STOCK_LIST_HINT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 0)

    def row_height(self) -> int:
        return self._row_height

    def content_height(self) -> int:
        return len(self._items) * self._row_height + self._padding[1] + self._padding[3]

    def row_at(self, y: float) -> int | None:
        top = self._padding[1]
        index = int((y - top) // self._row_height)
        return index if 0 <= index < len(self._items) else None

    def _resize_rows(self) -> None:
        height = self.content_height()
        self._rows.setMinimumHeight(height)
        self._rows.setFixedHeight(height)
        self._rows.updateGeometry()
        self._rows.update()

    # -- painting -------------------------------------------------------

    def _token(self, name: str, fallback: str) -> QColor:
        manager = ThemeManager.get_instance()
        return QColor(manager.try_get_color(name) or fallback)

    def paint_rows(self, target: QWidget) -> None:
        painter = QPainter(target)
        font = QFont(target.font())
        font.setPixelSize(self._text_pixel_size)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_color = self._token("dialog.text", "#ffffff")
        selected_fill = self._token("button.dialog.default.background.pressed", "#676e7b")
        hover_fill = self._token("dialog.button.hover", "#343b47")
        left, top, right, _bottom = self._padding
        width = target.width() - left - right
        for index, text in enumerate(self._items):
            row = QRectF(left, top + index * self._row_height, width, self._row_height)
            if index == self._current:
                painter.fillRect(row, selected_fill)
            elif index == self._hover_row:
                painter.fillRect(row, hover_fill)
            painter.setPen(text_color)
            baseline = row.y() + (self._row_height + metrics.ascent() - metrics.descent()) / 2
            painter.drawText(
                QRectF(row.x(), row.y(), row.width(), row.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(row.width())),
            )

    # -- keyboard -------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._items:
            if self._current < 0:
                # First arrow from "nothing selected" lands on the first row, whichever direction (QListWidget's own
                # behaviour): starting from 0 and then stepping made the first Down select the second row.
                self.setCurrentRow(0)
                return
            step = 1 if key == Qt.Key.Key_Down else -1
            self.setCurrentRow(max(0, min(len(self._items) - 1, self._current + step)))
            return
        super().keyPressEvent(event)
