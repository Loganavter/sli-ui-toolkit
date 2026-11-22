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

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.overlays.marquee_state import MarqueeState, paint_marquee_band
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
        return QSize(0, self._owner.rows_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802
        # Fill FIRST, then draw the rows. A content host that only draws its rows leaves the rest of its own rect
        # untouched, so when the widget changes width the vacated strip keeps the previous frame - the owner saw a
        # selection band's tail stuck at the right of the queue after Move Up (2026-11-22). This is the reference host's
        # rule for a content well: paint your fill explicitly, do not rely on whatever is behind you
        # (`OpaqueFillHost.paintEvent` -> `fillRect(event.rect(), self._fill)` in BlinkTable).
        painter = QPainter(self)
        # Clip to the plate's SHAPE, not just its rect: the list is a rounded panel, and a band that the pointer drags
        # outside it (the marquee keeps tracking past the widget by design) must not paint over the corners or past the
        # rounded edge - the owner saw the selector draw outside the visible list (2026-11-22).
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipPath(self._owner.panel_path(QRectF(self.rect())))
        fill = self._owner.fill_colour()
        if fill is not None:
            painter.fillRect(event.rect(), fill)
        painter.end()
        self._owner.paint_rows(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # The list owns the selection model; the rows widget only reports where the pointer landed. A right press that
        # lands inside the selection must NOT collapse it - the context menu then acts on what the user selected.
        self._owner._on_rows_press(event)
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._owner._on_rows_move(event):
            event.accept()
            return
        row = self._owner.row_at(event.position().y())
        if row != self._owner._hover_row:
            self._owner._hover_row = row
            self._owner.setToolTip(self._owner.row_tooltip(row) if row is not None else "")
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._owner._on_rows_release(event)
        super().mouseReleaseEvent(event)

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
        self._selected: set[int] = set()
        self._anchor: int | None = None
        self._selection_mode = "single"
        # The drag itself belongs to the toolkit's ONE marquee mechanism (`MarqueeState`): it installs a short-lived
        # application filter while active, so a band keeps tracking when the pointer leaves the widget, and it maps
        # through globalPosition. The list owns hit-testing (which rows the rect touches) and the selection.
        self._marquee_additive = False
        self._band_base: set[int] = set()
        self._row_height = max(8, scaled_px(row_height))
        self._padding = tuple(scaled_px(v) for v in (padding or (6, 4, 6, 4)))
        self._text_pixel_size = max(1, int(text_pixel_size))
        #: Host hook: `painter, index, rect, metrics, text, selected, hovered -> None`. The default draws the elided text
        #: (this widget stays a TEXT list). A host whose rows carry more than text - a progress bar, a right-aligned
        #: status - paints them here instead of pushing widgets into a text list (owner, 2026-11-22).
        self._row_painter = None
        #: Host hook: `index -> str`, read when the cursor moves onto a row (the toolkit's tooltip interceptor shows it).
        self._row_tooltip_provider = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Preferred, like the `QListWidget` this replaces. NOT Expanding: a box layout caches an item's expanding
        # directions when it is inserted, so a host that sets `Preferred` AFTER inserting the widget leaves the layout
        # believing it expands - measured on a queue row where the list took 330 px against the stock 256 and squeezed
        # the button column from 200 to 104. Preferred by default makes the host's own call a no-op.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        # No layout inset: the plate IS the widget, and its rounded corners are painted by `SurfacePanel`. Insetting by
        # the radius shrank the plate by 20 px inside its own rect - measured on an empty queue list, whose whole visible
        # content is that plate (2.7 % against the stock 1.4 %).
        self._scroll = OverlayScrollArea(self, reserve_scrollbar_space=True)
        # The INNER scroll area must not be Expanding: a layout item inherits the expansion of the widget's own layout,
        # and an Expanding child made the whole list claim its row's leftover - measured on a queue page where the list
        # took 330 px against the stock 256 and the button column beside it lost 79 px. With Preferred the split is
        # exactly QListWidget's.
        self._scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        if scrollbar_width is not None:
            self._scroll.set_scrollbar_width(scrollbar_width)
        self._rows = _Rows(self)
        # Created after the rows exist: the marquee tracks ITS drags and the rows own the coordinates.
        self._marquee = MarqueeState(
            self._rows,
            min_drag_px=3,
            on_update=self._on_marquee_update,
            on_finish=self._on_marquee_finish,
        )
        self._scroll.setWidget(self._rows)
        # The rows paint their own band; the scroll area must not put a plate behind them.
        self._scroll.viewport().setAutoFillBackground(False)
        self._rows.setAutoFillBackground(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._scroll)
        # The rows' height depends on the viewport (see `rows_height`), so a resize of the list has to re-run it.
        self._scroll.viewport().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.Resize and getattr(self, "_scroll", None) is not None:
            if watched is self._scroll.viewport():
                self._resize_rows()
        elif event.type() in (QEvent.Type.Hide, QEvent.Type.WindowDeactivate) and self._marquee.active:
            # Any way the list can stop being the gesture's owner ends the gesture: a band whose filter outlives its
            # widget eats drags for the whole application.
            self._marquee.cancel()
            self._band_base = set()
            self._marquee_additive = False
        return super().eventFilter(watched, event)

    # -- model ----------------------------------------------------------

    def set_row_painter(self, painter) -> None:
        """Paint rows yourself: `painter(painter, index, rect, metrics, text, selected, hovered)`."""
        self._row_painter = painter
        self._rows.update()

    def row_painter(self):
        return self._row_painter

    def set_row_tooltip_provider(self, provider) -> None:
        """Hover text per row: `provider(index) -> str`; ``None`` clears it."""
        self._row_tooltip_provider = provider

    def row_tooltip(self, index: int) -> str:
        if self._row_tooltip_provider is None or index is None or index < 0:
            return ""
        try:
            return str(self._row_tooltip_provider(int(index)) or "")
        except Exception:
            return ""

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
        self._selected = {row + 1 if row >= index else row for row in self._selected}
        if self._anchor is not None and self._anchor >= index:
            self._anchor += 1
        self._resize_rows()

    def takeItem(self, index: int) -> str | None:  # noqa: N802
        if not 0 <= index < len(self._items):
            return None
        removed = self._items.pop(int(index))
        self._selected.discard(int(index))
        self._selected = {row - 1 if row > index else row for row in self._selected}
        if self._anchor is not None and self._anchor > index:
            self._anchor -= 1
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
        self._selected.clear()
        self._anchor = None
        self._resize_rows()
        self.currentRowChanged.emit(-1)

    def setItems(self, items) -> None:  # noqa: N802
        self._items = [str(item) for item in items]
        self._current = -1
        self._selected.clear()
        self._anchor = None
        self._resize_rows()
        self.currentRowChanged.emit(-1)

    def currentRow(self) -> int:  # noqa: N802
        return self._current

    def setCurrentRow(self, index: int) -> None:  # noqa: N802
        index = int(index)
        if index < -1 or index >= len(self._items):
            return
        self._current = index
        self._select_only(index) if index >= 0 else self.clearSelection()
        self._anchor = index if index >= 0 else None
        self._rows.update()
        self.currentRowChanged.emit(index)

    # -- selection ------------------------------------------------------
    #
    # One model for all three ways a user picks rows: click, ctrl/shift+click, and a rubber band dragged across the
    # rows (the file-manager gesture the owner asked for, 2026-11-22). A single-selection list keeps behaving exactly
    # as before - `SelectionMode.Single` is the default, so an existing host changes nothing by not calling
    # `setSelectionMode`.

    selectionChanged = Signal()

    def selectionMode(self) -> str:  # noqa: N802 - QListWidget spelling
        return self._selection_mode

    def setSelectionMode(self, mode) -> None:  # noqa: N802 - QListWidget spelling
        """``Single``/``Multi``/``Extended`` as Qt enums or strings; anything unrecognised means single.

        Extended is the file-manager behaviour: a plain click selects one row, Ctrl toggles, Shift extends from the last
        click, and dragging anywhere over the rows draws a band that selects what it touches.
        """
        name = getattr(mode, "name", None) or str(mode)
        name = name.lower().replace("selection", "")
        self._selection_mode = name if name in ("single", "multi", "extended") else "single"
        if self._selection_mode == "single" and len(self._selected) > 1:
            keep = self._current if self._current in self._selected else max(self._selected)
            self._selected = {keep}
        self._rows.update()

    def selectedRows(self) -> list[int]:  # noqa: N802 - QListWidget spelling
        return sorted(self._selected)

    def selectedItems(self) -> list[str]:  # noqa: N802 - QListWidget spelling
        return [self._items[row] for row in self.selectedRows()]

    def selectedCount(self) -> int:  # noqa: N802 - QListWidget spelling
        return len(self._selected)

    def setSelectedRows(self, rows) -> None:
        wanted = {int(row) for row in rows if 0 <= int(row) < len(self._items)}
        if wanted == self._selected:
            return
        self._selected = wanted
        self._rows.update()
        self.selectionChanged.emit()

    def selectAll(self) -> None:  # noqa: N802 - QListWidget spelling
        self.setSelectedRows(range(len(self._items)))

    def clearSelection(self) -> None:  # noqa: N802 - QListWidget spelling
        self._anchor = None
        self.setSelectedRows(())

    def isSelected(self, row: int) -> bool:  # noqa: N802 - QListWidget spelling
        return int(row) in self._selected

    def _select_only(self, row: int) -> None:
        self.setSelectedRows((row,))

    def _select_range(self, first: int, last: int) -> None:
        low, high = (first, last) if first <= last else (last, first)
        self.setSelectedRows(range(low, high + 1))

    def _toggle(self, row: int) -> None:
        selection = set(self._selected)
        selection.symmetric_difference_update({row})
        self.setSelectedRows(selection)

    def _on_rows_press(self, event) -> None:
        index = self.row_at(event.position().y())
        modifiers = event.modifiers()
        if event.button() == Qt.MouseButton.RightButton:
            # A right press means "context menu", i.e. the user is DONE with a band. `MarqueeState` deliberately keeps a
            # band alive across a non-left press, and its application-wide filter then stays installed: the left
            # release goes to the popup, the gesture never finishes, and every later drag anywhere in the app is
            # consumed as an update of this list. The owner saw exactly that - "after this list breaks, every control
            # stops updating until I click somewhere" (2026-11-22). Cancel here.
            if self._marquee.active:
                self._marquee.cancel()
                self._band_base = set()
                self._marquee_additive = False
                self._rows.update()
            # A right press outside the selection moves it to the row under the cursor (file-manager behaviour); a
            # right press INSIDE it keeps the selection so the menu acts on everything the user picked.
            if index is not None and index not in self._selected:
                self._current = index
                self._select_only(index)
                self._anchor = index
                self._rows.update()
                self.currentRowChanged.emit(index)
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        additive = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        if index is None:
            if not additive:
                self.clearSelection()
            self._start_band(event.position(), additive)
            return
        self._current = index
        if additive:
            self._toggle(index)
            self._anchor = index
        elif (modifiers & Qt.KeyboardModifier.ShiftModifier) and self._anchor is not None:
            self._select_range(self._anchor, index)
        else:
            self._select_only(index)
            self._anchor = index
        self._rows.update()
        self.currentRowChanged.emit(index)
        self._start_band(event.position(), additive)

    def _start_band(self, position, additive: bool) -> None:
        if self._selection_mode == "single":
            return
        self._marquee_additive = bool(additive)
        self._band_base = set(self._selected) if additive else set()
        self._marquee.start(QPoint(int(position.x()), int(position.y())))

    def _rows_touched_by(self, rect) -> set[int]:
        """The rows a content-space band rect touches (a zero-height band still takes the row under it)."""
        if rect.isEmpty() or not rect.isValid():
            return set()
        top, bottom = rect.top(), rect.bottom()
        first = self.row_at(top)
        if first is None:
            first = 0 if top < self.content_height() else None
        last = self.row_at(bottom)
        if last is None:
            last = len(self._items) - 1 if bottom >= 0 else None
        if first is None or last is None:
            return set()
        return set(range(min(first, last), max(first, last) + 1))

    def _on_marquee_update(self, rect) -> None:
        # A press alone must not touch the selection: the click logic already decided it (a Ctrl+click toggles a row
        # OFF, and re-applying the one-pixel band would put it back - measured). The band takes over once it is a real
        # drag.
        if rect.width() < 3 and rect.height() < 3:
            return
        touched = set(self._band_base) if self._marquee_additive else set()
        touched.update(self._rows_touched_by(rect))
        self.setSelectedRows(touched)
        self._rows.update()

    def _on_marquee_finish(self, rect) -> None:
        """Commit the band; a tiny drag is a CLICK and leaves the press-time selection alone."""
        if not rect.isEmpty() and rect.isValid():
            touched = set(self._band_base) if self._marquee_additive else set()
            touched.update(self._rows_touched_by(rect))
            self.setSelectedRows(touched)
        self._band_base = set()
        self._marquee_additive = False
        self._rows.update()

    def _on_rows_move(self, event) -> bool:
        """Forward a drag the widget itself receives; the marquee's own filter covers moves that leave it."""
        if not self._marquee.active:
            return False
        pos = event.position()
        self._marquee.update_at(QPoint(int(pos.x()), int(pos.y())))
        return True

    def _on_rows_release(self, event) -> None:
        if not self._marquee.active:
            return
        if event is None:                      # a caller that has no event still needs the gesture finished
            band = self._marquee.band_rect
            pos = band.bottomRight() if not band.isEmpty() else QPoint(0, 0)
        else:
            pos = self._rows.mapFromGlobal(event.globalPosition().toPoint())
        self._marquee.finish_at(QPoint(int(pos.x()), int(pos.y())))

    # -- geometry -------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """The stock `QListWidget`'s own default (256x192, scaled).

        A migrating layout was laid out against that box: with any other hint the list takes a different share of the
        row and squeezes its neighbour - measured on a queue page where the button column lost 79 px to the list and the
        output list grew 48 px taller.
        """
        return QSize(*_STOCK_LIST_HINT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """`QListWidget`'s own floor (70x70, scaled).

        Not zero: `QBoxLayout` distributes a row's leftover space using each item's minimum, and a zero minimum lets the
        list take the whole slack - measured on a queue page where the list was 335 px against the stock 256 and the
        button column beside it lost 79 px.
        """
        return QSize(scaled_px(70), scaled_px(70))

    def row_height(self) -> int:
        return self._row_height

    def content_height(self) -> int:
        return len(self._items) * self._row_height + self._padding[1] + self._padding[3]

    def row_at(self, y: float) -> int | None:
        top = self._padding[1]
        index = int((y - top) // self._row_height)
        return index if 0 <= index < len(self._items) else None

    def rows_height(self) -> int:
        import os as _rows_env

        if _rows_env.environ.get("RVE_UI_NO_ROWS_VIEWPORT"):   # bisect: back to "content height only"
            return self.content_height()
        """The painted rows' height: the content, or the viewport when the content is shorter.

        A `_Rows` exactly as tall as its content leaves the rest of the viewport to the scroll area - and a press there
        (or a rubber band dragged from empty space, which is the ordinary file-manager gesture) never reaches the list at
        all. Measured live: the queue with one item is 28 px of rows inside a 248 px viewport, so three quarters of the
        list ignored the mouse.
        """
        viewport = getattr(getattr(self, "_scroll", None), "viewport", None)
        height = self.content_height()
        if viewport is not None:
            try:
                height = max(height, int(viewport().height()))
            except Exception:
                pass
        return height

    def _resize_rows(self) -> None:
        height = self.rows_height()
        self._rows.setMinimumHeight(height)
        self._rows.setFixedHeight(height)
        self._rows.updateGeometry()
        self._rows.update()

    # -- painting -------------------------------------------------------

    def fill_colour(self) -> QColor | None:
        """The colour the rows sit on (the list's own plate), or ``None`` when the host paints no plate."""
        token = self.background_token() or "surface.list"
        try:
            colour = QColor(ThemeManager.get_instance().try_get_color(token))
        except Exception:
            colour = QColor()
        if colour.isValid():
            colour.setAlpha(255)
            return colour
        return None

    def _token(self, name: str, fallback: str) -> QColor:
        manager = ThemeManager.get_instance()
        return QColor(manager.try_get_color(name) or fallback)

    def paint_rows(self, target: QWidget) -> None:
        painter = QPainter(target)
        # Rows and the marquee band live under the same rounded plate: clip before anything is drawn, so neither the
        # selection fill nor the band can reach the rounded corners (owner, 2026-11-22).
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipPath(self.panel_path(QRectF(target.rect())))
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
            if index in self._selected:
                painter.fillRect(row, selected_fill)
            elif index == self._hover_row:
                painter.fillRect(row, hover_fill)
            if self._row_painter is not None:
                self._row_painter(
                    painter, index, row, metrics, text,
                    index in self._selected, index == self._hover_row,
                )
            else:
                painter.setPen(text_color)
                painter.drawText(
                    QRectF(row.x(), row.y(), row.width(), row.height()),
                    int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                    metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(row.width())),
                )
        self._paint_band(painter, target)
        # ALWAYS end the painter: leaving it active makes Qt print "QBackingStore::endPaint() called with active painter"
        # and painting stalls - the window stops answering (measured 2026-11-22, the row painter made this path run).
        painter.end()

    def panel_radius(self) -> int:
        """The plate's corner radius in px (0 = square)."""
        return int(getattr(self, "_radius", 0) or 0)

    def panel_path(self, rect) -> QPainterPath:
        """The plate's outline as a path, so content can be clipped to it."""
        path = QPainterPath()
        radius = self.panel_radius()
        if radius > 0:
            path.addRoundedRect(rect, radius, radius)
        else:
            path.addRect(rect)
        return path

    def _paint_band(self, painter: QPainter, target: QWidget) -> None:
        """The rubber rectangle, clamped to the visible rows.

        A drag keeps tracking outside the list (`MarqueeState`'s application filter), so `band_rect` can be far bigger
        than the widget. Clamping the rect here - rather than painting a huge rect and letting the widget clip it - keeps
        the band's border inside the visible list: the owner saw the кайма reach past it (2026-11-22). The border stays on
        all four sides of the CLAMPED rect, because that rect is the selection's real extent.
        """
        band = self._marquee.band_rect
        if band.isEmpty():
            return
        visible = target.rect()
        clamped = band.intersected(visible)
        if clamped.isEmpty():
            return
        accent = self._token("accent", "#0078d4")
        self._marquee.set_accent(accent)
        paint_marquee_band(painter, clamped, accent)

    # -- keyboard -------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_A:
            if self._selection_mode != "single":
                self.selectAll()
                event.accept()
                return
        if key == Qt.Key.Key_Escape:
            self.clearSelection()
            self._rows.update()
            event.accept()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._items:
            if self._current < 0:
                # First arrow from "nothing selected" lands on the first row, whichever direction (QListWidget's own
                # behaviour): starting from 0 and then stepping made the first Down select the second row.
                self.setCurrentRow(0)
                return
            step = 1 if key == Qt.Key.Key_Down else -1
            target = max(0, min(len(self._items) - 1, self._current + step))
            if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) and self._anchor is not None:
                self._current = target
                self._select_range(self._anchor, target)
                self._rows.update()
                self.currentRowChanged.emit(target)
                return
            self.setCurrentRow(target)
            return
        super().keyPressEvent(event)
