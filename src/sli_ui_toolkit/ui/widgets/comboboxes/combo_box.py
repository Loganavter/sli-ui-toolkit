from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import time
from typing import TYPE_CHECKING, Any, ClassVar

from PySide6.QtCore import (
    QEvent,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFontMetrics, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_FONT, AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import FocusLayer, RippleLayer
from sli_ui_toolkit.ui.widgets.comboboxes._layers import (
    _ComboFieldBgLayer,
    _ComboFieldContentLayer,
)
from sli_ui_toolkit.ui.widgets.comboboxes._models import _ComboItem
from sli_ui_toolkit.ui.widgets.comboboxes._overlay import (
    _DropdownOverlay,
    apply_elided_tooltip,
)
from sli_ui_toolkit.ui.widgets.comboboxes._search import (
    match_score,
    match_score_normalized,
    normalize_for_search,
    visible_indices_normalized,
)
from sli_ui_toolkit.ui.widgets.comboboxes.capabilities import GearDragCapability


class ComboBox(Button):
    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar["WidgetDescriptor"]

    currentIndexChanged = Signal(int)
    currentTextChanged = Signal(str)

    BASE_HEIGHT = 33
    RADIUS = 6
    ITEM_VERTICAL_PADDING = 12
    TEXT_HORIZONTAL_PADDING = 12

    # "Gear-shifter" drag-select: hold the field for GEAR_HOLD_MS, or drag it
    # sideways/vertically past GEAR_DRAG_THRESHOLD_PX right after pressing, to
    # open the dropdown and scrub through rows by dragging — like sliding a
    # gearbox knob into its slot. Releasing commits whichever row is under the
    # field at that moment, immediately (no settle animation, no hold); a plain
    # click/release still just toggles the list.
    GEAR_HOLD_MS = 450
    GEAR_DRAG_THRESHOLD_PX = 8
    # Keyboard typeahead window (typing_mode="jump"): keys typed within this
    # interval extend the query; a longer pause starts a new one.
    TYPEAHEAD_TIMEOUT_MS = 900

    def __init__(
        self,
        parent=None,
        *,
        wheel_requires_focus: bool = False,
        typing_mode: str = "jump",
    ):
        # Validate before any QWidget work: a bad mode must not leave a
        # half-constructed widget on the appearance bus (its live-scale
        # callback would fire on an object whose fields were never set).
        typing_mode = self._normalize_typing_mode(typing_mode)
        super().__init__(
            text="",
            size=(0, self.BASE_HEIGHT),
            corner_radius=self.RADIUS,
            wheel_requires_focus=wheel_requires_focus,
            long_press=True,
            long_press_ms=self.GEAR_HOLD_MS,
            layers=[
                _ComboFieldBgLayer(),
                RippleLayer(),
                _ComboFieldContentLayer(),
                FocusLayer(),
            ],
            parent=parent,
        )
        self._theme = ThemeManager.get_instance()
        self._items: list[_ComboItem] = []
        self._current_index = -1
        # While expanded, optional scroll/center target that does not change
        # ``currentIndex`` (Find Action "show me this option" without applying).
        self._dropdown_focus_index: int | None = None
        self._expanded = False
        self._max_visible_items = 12
        self._minimum_contents_length = 0
        self._scroll_offset = 0
        self._overlay: _DropdownOverlay | None = None
        self._overlay_parent: QWidget | None = None
        self._search_enabled = True
        self._search_text = ""
        # Typing policy: "jump" (default) is file-manager typeahead — the list
        # keeps every row and the highlight walks to the first match; "filter"
        # is the legacy mode that narrows visible rows and applies the first
        # match immediately. See setTypingMode.
        self._typing_mode = typing_mode
        # Typeahead buffer + its expiry (time.monotonic) and the row the
        # buffer currently points at. The row is HELD in
        # ``_dropdown_focus_index`` (highlight/scroll only) and committed by
        # Enter or a click — never by the keystroke itself.
        self._typeahead_text = ""
        self._typeahead_deadline = 0.0
        self._typing_focus = False
        self._visible_indices_cache: list[int] = []
        self._visible_positions_cache: dict[int, int] = {}
        self._visible_cache_dirty = True

        # Gear-shifter drag-select (see GEAR_HOLD_MS above) — behavior lives
        # in GearDragCapability, mirroring Button's own capability system
        # (LongPressCapability). Cached directly here (in addition to being
        # reachable via get_capability) since hideDropdown() and the proxy
        # properties below need cheap, frequent access.
        self._gear = GearDragCapability(
            hold_ms=self.GEAR_HOLD_MS,
            drag_threshold_px=scaled_px(self.GEAR_DRAG_THRESHOLD_PX),
        )
        self.attach_capability(self._gear)

        self.clicked.connect(self._on_field_clicked)
        connect_ui_metrics(
            self, self.on_scale_changed, axes=frozenset({AXIS_FONT, AXIS_SCALE})
        )
        self._sync_field_tooltip()

    def on_scale_changed(self, *_args: object) -> None:
        # ``Button.on_scale_changed`` re-derives from the live ``UiScale`` and
        # reads no payload; the bus hands the merged axes frozenset, so the
        # factor forwarded below is a no-op.
        super().on_scale_changed(1.0)
        self._gear.drag_threshold_px = scaled_px(self.GEAR_DRAG_THRESHOLD_PX)
        self.updateGeometry()
        self._sync_field_tooltip()
        self.update()

    def _item_height(self) -> int:
        return max(
            scaled_px(28),
            QFontMetrics(paint_font(self)).height()
            + scaled_px(self.ITEM_VERTICAL_PADDING),
        )

    def _typing_query_text(self) -> str:
        """The query the user is currently typing, whichever mode produced it.

        Both typing policies share the field's ``"<query> -> <value>"``
        painted line: a filter narrows the rows, a jump only walks the
        highlight, but the field must show what was typed either way (in jump
        mode the value itself does not move until Enter).
        """
        if self._typing_mode == "jump":
            return self._typeahead_text
        return self._search_text

    def _field_display_text(self) -> str:
        """Exactly what ``_ComboFieldContentLayer`` paints in the field."""
        current_text = self.currentText()
        if not current_text:
            return ""
        query = self._typing_query_text()
        if query and self._expanded:
            return f"{query} -> {current_text}"
        return current_text

    def _sync_field_tooltip(self) -> None:
        """Field tooltip = the full painted value while the label elides.

        Same font and text rect as ``_ComboFieldContentLayer.draw``. Every
        path that can change the painted string or the field width calls
        this explicitly: the field commits its own text through these public
        mutators, and deciding a tooltip from inside a paint layer would make
        painting mutate widget state.
        """
        apply_elided_tooltip(
            self,
            self._field_display_text(),
            self.width() - 2 * scaled_px(self.TEXT_HORIZONTAL_PADDING),
        )

    @property
    def _gear_active(self) -> bool:
        """Proxy to GearDragCapability.active — _overlay.py reads this as a
        plain ComboBox attribute and has no reason to know capabilities
        exist."""
        return self._gear.active

    @property
    def _gear_focus_index(self) -> int:
        """Proxy to GearDragCapability.focus_index — see _gear_active."""
        return self._gear.focus_index

    @property
    def _typing_focus_index(self) -> int:
        """Row the typeahead buffer points at, or -1 when typing focus is off.

        Unlike ``currentIndex`` this is highlight-only state: the dropdown row
        is scrolled to and ringed, while the field value and
        ``currentIndexChanged`` stay untouched until Enter/click commits it.
        """
        if not self._typing_focus:
            return -1
        index = self._dropdown_focus_index
        return index if index is not None else -1

    @property
    def _focus_row_index(self) -> int:
        """The one row drawn as "this is what a commit takes", or -1.

        Two owners share that role and never overlap: an active gear-drag
        (row under the field frame) wins; otherwise the typeahead highlight.
        """
        if self._gear.active:
            return self._gear.focus_index
        return self._typing_focus_index

    def _invalidate_visible_cache(self) -> None:
        self._visible_cache_dirty = True
        self._visible_indices_cache = []
        self._visible_positions_cache = {}

    def _visible_items(self) -> int:
        return min(len(self._visible_indices()), self._max_visible_items)

    def _visible_position_for_index(self, index: int) -> int:
        self._visible_indices()
        return self._visible_positions_cache.get(index, 0)

    def _focus_or_current_index(self) -> int:
        if self._dropdown_focus_index is not None and 0 <= self._dropdown_focus_index < len(
            self._items
        ):
            return self._dropdown_focus_index
        return self._current_index

    def _ensure_index_visible(self, index: int) -> None:
        visible = self._visible_indices()
        visible_count = len(visible)
        if visible_count <= self._max_visible_items or index < 0:
            self._scroll_offset = 0
            return
        try:
            visible_position = visible.index(index)
        except ValueError:
            self._scroll_offset = 0
            return
        if visible_position < self._scroll_offset:
            self._scroll_offset = visible_position
        elif visible_position >= self._scroll_offset + self._max_visible_items:
            self._scroll_offset = visible_position - self._max_visible_items + 1

    def _ensure_current_visible(self):
        self._ensure_index_visible(self._focus_or_current_index())

    def count(self) -> int:
        return len(self._items)

    def addItem(self, text: str, userData: Any = None):
        self._items.append(_ComboItem(str(text), userData))
        if self._current_index == -1:
            self._current_index = 0
        self._invalidate_visible_cache()
        self._sync_field_tooltip()
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
        self._sync_field_tooltip()
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
        self._sync_field_tooltip()
        self.update()

    def clear(self):
        self.hideDropdown()
        self._items.clear()
        self._current_index = -1
        self._scroll_offset = 0
        self._search_text = ""
        self._invalidate_visible_cache()
        self._sync_field_tooltip()
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

    @staticmethod
    def _normalize_typing_mode(mode: str) -> str:
        normalized = str(mode).strip().lower()
        if normalized not in ("jump", "filter"):
            raise ValueError(
                f"unknown typing_mode {mode!r}; use 'jump' or 'filter'"
            )
        return normalized

    def typingMode(self) -> str:
        return self._typing_mode

    def setTypingMode(self, mode: str) -> None:
        """Choose how keystrokes pick a row.

        ``"jump"`` (default) — file-manager typeahead: the list is never
        filtered, keys walk a buffer-driven highlight to the first row that
        matches, and Enter/click commits it. ``"filter"`` — legacy: the visible
        rows narrow to the matches and the first match becomes ``currentIndex``
        immediately.
        """
        normalized = self._normalize_typing_mode(mode)
        if normalized == self._typing_mode:
            return
        self._typing_mode = normalized
        self._reset_typeahead()
        # A filter query cannot survive a switch in either direction: "jump"
        # never filters, and a fresh filter mode must start unfiltered.
        self.clearSearch()
        self._invalidate_visible_cache()
        if self._expanded and self._overlay is not None:
            self._ensure_current_visible()
            self._overlay._sync_scrollbar()
            self._overlay.update()
        self.update()

    def setSearchEnabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._search_enabled == enabled:
            return
        self._search_enabled = enabled
        if not enabled:
            self.clearSearch()
            self._reset_typeahead()
        self._invalidate_visible_cache()
        self.update()

    def acceptsTextKeys(self) -> bool:
        """True when unmodified letter/space keys are input for this widget.

        Host keyboard routers use this duck-typed protocol to keep global
        canvas shortcuts (W/A/S/D/Q/E, Space) from swallowing typing aimed at
        the focused field — the ComboBox is a painted Button, not a
        ``QLineEdit``, so type-based text-input checks miss it. Typing is
        disabled as soon as the widget is disabled or search is turned off.
        """
        return bool(self.isEnabled() and self._search_enabled)

    def isSearchEnabled(self) -> bool:
        return self._search_enabled

    def searchText(self) -> str:
        """The active typing query (filter text, or the jump buffer)."""
        return self._typing_query_text()

    def _clear_filter_text(self) -> None:
        """Drop the filter query only (the jump buffer has its own lifetime)."""
        if not self._search_text:
            return
        self._search_text = ""
        self._invalidate_visible_cache()
        self._scroll_offset = 0
        if self._expanded and self._overlay is not None:
            self._ensure_current_visible()
            self._overlay._sync_scrollbar()
            self._overlay.update()
        self._sync_field_tooltip()
        self.update()

    def clearSearch(self) -> None:
        """End the typing session: drop the query the user typed (either mode).

        Closing the popup is NOT a session end — ``hideDropdown`` calls
        ``_clear_filter_text`` instead — because the jump buffer is
        time-boxed, and a transient close mid-typing must not restart the
        search from one character (owner report 2026-10-22).
        """
        self._reset_typeahead()
        self._sync_field_tooltip()
        self._clear_filter_text()

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
        self._sync_field_tooltip()
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

    # -------- typeahead jump (typing_mode="jump") --------

    def _clear_typing_highlight(self) -> None:
        """Drop the walked-row highlight, keep the query buffer.

        Closing the popup is not the end of a typing session: the query is
        time-boxed (``TYPEAHEAD_TIMEOUT_MS``), so a transient close — e.g. the
        flyout manager dismissing this dropdown because another flyout was
        shown, or the focus restoration of that flyout — must not restart the
        search from a single character (owner report 2026-10-22: "one letter
        works, then it stops searching"; the reveal-overlay left open by
        settings navigation dismissed the dropdown between keystrokes).
        """
        if self._typing_focus:
            self._typing_focus = False
            self._dropdown_focus_index = None
            if self._expanded and self._overlay is not None:
                self._overlay.update()

    def _reset_typeahead(self) -> None:
        """End the typing session: query, deadline and highlight."""
        self._typeahead_text = ""
        self._typeahead_deadline = 0.0
        self._clear_typing_highlight()

    def _set_typing_focus(self, index: int) -> None:
        self._typing_focus = True
        self._dropdown_focus_index = index
        self._ensure_index_visible(index)
        if self._expanded and self._overlay is not None:
            self._overlay._sync_scrollbar()
            self._overlay.update()
        self.update()

    def _step_typing_focus(self, step: int) -> bool:
        current = self._typing_focus_index
        visible = self._visible_indices()
        if current < 0 or not visible:
            return False
        try:
            pos = visible.index(current)
        except ValueError:
            pos = 0
        new_pos = max(0, min(len(visible) - 1, pos + step))
        self._set_typing_focus(visible[new_pos])
        return True

    def _typeahead_index(self, query: str, *, cycle: bool) -> int | None:
        """First row matching ``query`` in list order, walking from the anchor.

        ``cycle=True`` (a fresh query) starts one row past the anchor, so
        pressing the same key again advances to the next match like a file
        manager. An extension of the current query starts AT the anchor: the
        row already highlighted must be able to stay put while the query grows.
        Both variants wrap, so "any match" never depends on where the list
        happens to be scrolled.
        """
        norm_query = normalize_for_search(query)
        count = len(self._items)
        if not norm_query or count == 0:
            return None
        anchor = self._typing_focus_index
        if anchor < 0:
            anchor = self._current_index
        anchor = max(0, min(count - 1, anchor))
        start = (anchor + 1) % count if cycle else anchor
        for step in range(count):
            index = (start + step) % count
            if match_score_normalized(norm_query, self._items[index].normalized_text) is not None:
                return index
        return None

    def _handle_typeahead_text(self, text: str) -> bool:
        if not text:
            return False
        now = time.monotonic()
        fresh = not self._typeahead_text or now > self._typeahead_deadline
        self._typeahead_text = text if fresh else self._typeahead_text + text
        self._typeahead_deadline = now + self.TYPEAHEAD_TIMEOUT_MS / 1000.0
        index = self._typeahead_index(self._typeahead_text, cycle=fresh)
        if index is not None:
            self._set_typing_focus(index)
        else:
            # No match still changes the painted query line.
            self.update()
        self._sync_field_tooltip()
        return True

    def _handle_typeahead_backspace(self) -> bool:
        if not self._typeahead_text:
            return False
        now = time.monotonic()
        if now > self._typeahead_deadline:
            self._reset_typeahead()
            return False
        self._typeahead_text = self._typeahead_text[:-1]
        self._typeahead_deadline = now + self.TYPEAHEAD_TIMEOUT_MS / 1000.0
        if not self._typeahead_text:
            self._typing_focus = False
            self._dropdown_focus_index = None
            if self._expanded and self._overlay is not None:
                self._overlay.update()
            self.update()
            self._sync_field_tooltip()
            return True
        index = self._typeahead_index(self._typeahead_text, cycle=False)
        if index is not None:
            self._set_typing_focus(index)
        else:
            self.update()
        self._sync_field_tooltip()
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
        self._sync_field_tooltip()
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
        self._sync_field_tooltip()
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
        # Measure with the paint font (design size × UiScale) — the field
        # layer draws through ``paint_font``, so a raw-font hint under-
        # measures at scale > 1.0 and long labels elide inside the field.
        fm = QFontMetrics(paint_font(self))
        text_width = 0
        for item in self._items:
            text_width = max(text_width, fm.horizontalAdvance(item.text))
        if self._minimum_contents_length > 0:
            text_width = max(text_width, fm.horizontalAdvance("M" * self._minimum_contents_length))
        return max(scaled_px(100), text_width + scaled_px(24))

    def sizeHint(self) -> QSize:
        return QSize(self._content_width_hint(), scaled_px(self.BASE_HEIGHT))

    def minimumSizeHint(self) -> QSize:
        return QSize(max(scaled_px(80), self._content_width_hint()), scaled_px(self.BASE_HEIGHT))

    def _field_rect(self) -> QRect:
        return QRect(0, 0, self.width(), scaled_px(self.BASE_HEIGHT))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A pure geometry change only repaints the elided label; it reaches no
        # state hook, so without this the tooltip would keep a decision made
        # at the previous width until the next value change.
        self._sync_field_tooltip()

    def _ensure_overlay(self):
        window = self.window()
        if window is None:
            return
        if self._overlay is None or self._overlay_parent is not window:
            if self._overlay is not None:
                self._overlay.deleteLater()
            self._overlay_parent = window
            self._overlay = _DropdownOverlay(self, window)

    def showDropdown(self, focus_index: int | None = None):
        """Open the dropdown.

        ``focus_index`` scrolls that row into view without changing
        ``currentIndex`` (button label stays put until the user picks a row).
        """
        if self.count() == 0:
            return
        self._ensure_overlay()
        if self._overlay is None:
            return
        # A stale query (typed, then left alone past the timeout) does not
        # follow the user into a new open; a fresh one is resumed below, so a
        # transient close between keystrokes keeps the query growing.
        if self._typeahead_text and time.monotonic() > self._typeahead_deadline:
            self._reset_typeahead()
        if focus_index is not None and 0 <= int(focus_index) < self.count():
            self._dropdown_focus_index = int(focus_index)
        else:
            self._dropdown_focus_index = None
        self._expanded = True
        self._pressed = False
        self._ensure_current_visible()
        self._sync_field_tooltip()
        self._overlay.show_for_owner()
        if self._typeahead_text:
            index = self._typeahead_index(self._typeahead_text, cycle=False)
            if index is not None:
                self._set_typing_focus(index)
        self.update()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        window = self.window()
        if window is not None:
            window.installEventFilter(self)

    def dropdown_row_widget(self, index: int):
        """Visible dropdown row for ``index`` after ``showDropdown``, or ``None``."""
        if self._overlay is None:
            return None
        return self._overlay.slot_for_index(index)

    def hideDropdown(self):
        self._gear.cancel()
        if self._overlay is not None:
            self._overlay.clear_hover()
            self._overlay.hide()
        self._expanded = False
        self._pressed = False
        # The query buffer survives the close (it expires on its own timeout);
        # only the highlight is visibility-bound. Explicit ends of the typing
        # session — Escape, Enter/click commit, mode or search changes — call
        # _reset_typeahead().
        self._clear_typing_highlight()
        self._dropdown_focus_index = None
        self._clear_filter_text()
        self._sync_field_tooltip()
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

    # -------- gear-shifter drag-select (see GearDragCapability) --------

    def mousePressEvent(self, event: QMouseEvent):
        self._gear.handle_press(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._gear.handle_move(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        outcome = self._gear.handle_release(event)
        if outcome is not None:
            self._suppress_next_click = outcome.suppress_click
            super().mouseReleaseEvent(event)
            self._suppress_next_click = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._search_enabled and event.key() == Qt.Key.Key_Backspace:
            if self._typing_mode == "jump":
                if self._handle_typeahead_backspace():
                    event.accept()
                    return
            elif self._search_text:
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
            if self._typing_mode == "jump":
                self._handle_typeahead_text(event_text)
            else:
                self._set_search_text(self._search_text + event_text)
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._expanded:
                # Typeahead is highlight-only: Enter is what turns the walked
                # highlight into the value (a plain arrow-navigated selection
                # already committed through setCurrentIndex).
                focus = self._typing_focus_index
                if 0 <= focus < self.count():
                    self.setCurrentIndex(focus)
                self._reset_typeahead()
                self.hideDropdown()
            else:
                self.showDropdown()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Space:
            if self._expanded:
                self.hideDropdown()
            else:
                self.showDropdown()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Escape and self._expanded:
            self._reset_typeahead()
            self.hideDropdown()
            event.accept()
            return

        # Only steer the selection while the dropdown is actually open
        # (entered via Enter/Space above) -- collapsed, Up/Down must not
        # silently spin the value. This also matters for row-to-row
        # navigation: NavigationManager's ToolbarRowsSection trial-dispatches
        # arrow keys to the focused widget first (see its _widget_handles),
        # and a collapsed combo accepting them here would swallow the key
        # instead of letting the section move focus to the next/previous row.
        if event.key() == Qt.Key.Key_Down and self._expanded and self.count() > 0:
            if not self._step_typing_focus(1):
                self._move_visible_selection(1)
            event.accept()
            return

        if event.key() == Qt.Key.Key_Up and self._expanded and self.count() > 0:
            if not self._step_typing_focus(-1):
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
        expanded = getattr(self, "_expanded", False)
        overlay = getattr(self, "_overlay", None)
        if not expanded or overlay is None:
            return super().eventFilter(watched, event)

        if watched is self.window() and event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
            self._overlay.show_for_owner()
            return False

        # Outside-click and window/app deactivate dismiss are now handled by
        # FlyoutManager._dismiss_passive — _DropdownOverlay is a registered
        # BaseFlyout (see docs/legacy/plan_combobox_baseflyout_unification.md
        # Phase 2). Hide/Close still needs handling here: FlyoutManager
        # doesn't listen for QEvent.Type.Close at all, and only this combo's
        # own host leaving should collapse it — an app-wide filter would
        # otherwise collapse the list when Find Action's pulse overlay hides
        # after its blink timer.
        if event.type() in (QEvent.Type.Hide, QEvent.Type.Close) and watched in (
            self,
            self._overlay,
            self.window(),
        ):
            self.hideDropdown()
            return False

        return super().eventFilter(watched, event)

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


def _spec_items(w: Any) -> Any:
    return [t for t, _d in w.items()]


ComboBox.inspect_spec = InspectSpec(
    family="ComboBox",
    state=(
        SpecField("current_index", "currentIndex"),
        SpecField("current_text", "currentText"),
        SpecField("count", "count"),
        SpecField("items", _spec_items),
        SpecField("max_visible_items", "maxVisibleItems"),
    ),
    token_family=(
        "surface.background",
        "input.border.thin",
        "list_item.background.hover",
        "surface.background",
    ),
    docs='docs/user/INPUTS_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

ComboBox.widget_descriptor = WidgetDescriptor(
    family=ComboBox.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ComboBox.inspect_spec, 'config', ()),
        state=ComboBox.inspect_spec.state,
        token_family=getattr(ComboBox.inspect_spec, 'token_family', ()),
        regions=getattr(ComboBox.inspect_spec, 'regions', False),
        layers=getattr(ComboBox.inspect_spec, 'layers', False),
        docs=getattr(ComboBox.inspect_spec, 'docs', ''),
        preview_seed=getattr(ComboBox.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ComboBox.inspect_spec, 'apply_config_refresh', None),
    ),
)