"""IconListWidget - sidebar/nav list on a stack of toolkit Buttons (thin facade).

The class keeps construction, the items API, selection, the scroll
appearance and row plumbing; icon resolution lives in ``icons.py``,
the layout debug dump in ``debug.py``, and the row spec/factory in
``rows.py`` (the buttons/ folder split is the model).
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.comboboxes._search import (
    match_score_normalized,
    normalize_for_search,
)

from .debug import schedule_layout_debug
from .icons import (
    apply_row_icon,
    normalize_selected_icon_mode,
    update_row_fg,
    update_row_icon,
)


def _row_texts(widget: Any) -> list[str]:
    return [item.text for item in (widget.item(i) for i in range(widget.count()))]


def _row_match_score(norm_query: str, row: _RowSpec) -> int | None:
    """Best ``match_score_normalized`` over a row's pre-normalized texts."""
    best: int | None = None
    for text in row.normalized_texts:
        if not text:
            continue
        score = match_score_normalized(norm_query, text)
        if score is not None:
            best = score if best is None else min(best, score)
    return best


from .rows import (
    IconListItem,
    _ICON_TEXT_GAP,
    _LEFT_PADDING,
    _ListItem,
    _RowSpec,
    _make_nav_row_button,
    _SELECTED_ICON_MODES,
    _split_icon_pair,
    SelectedIconMode,
)


class IconListWidget(QWidget):
    currentRowChanged = Signal(int)
    currentItemChanged = Signal(object, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        icon_size: QSize | None = None,
        row_height: int = 44,
        selected_icon_mode: SelectedIconMode = "invert",
        button_factory: Callable[[IconListItem], Button] | None = None,
    ) -> None:
        super().__init__(parent)
        self._row_height = int(row_height)
        self._icon_size: QSize = icon_size if isinstance(icon_size, QSize) else QSize(24, 24)
        self._selected_icon_mode = normalize_selected_icon_mode(selected_icon_mode)
        self._button_factory = button_factory
        self._rows: list[_RowSpec] = []
        self._current_row: int = -1
        # ComboBox-style search view: rows stay built, filtering only changes
        # which ones are visible (no per-keystroke widget rebuilds).
        self._filter_query = ""
        self._visible: list[int] = []  # source-row indices, in display order
        self._no_results_row: _RowSpec | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # OverlayScrollArea floats a minimal scrollbar over the viewport with
        # no reserved layout space (reserve=False): the bar appearing or
        # disappearing never reflows the rows, so the nav content does not
        # shift sideways when the list starts/stops scrolling.
        self._scroll = OverlayScrollArea(self)
        self._scroll.set_reserve_scrollbar_space(False)

        self._host = QWidget()
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(
            scaled_px(8), scaled_px(4), scaled_px(8), scaled_px(4)
        )
        self._host_layout.setSpacing(scaled_px(8))
        self._host_layout.addStretch(1)
        self._scroll.setWidget(self._host)
        layout.addWidget(self._scroll)

        try:
            ThemeManager.get_instance().theme_changed.connect(self.refresh_icons)
        except Exception:
            pass
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)


    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        schedule_layout_debug(self, "resize")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        schedule_layout_debug(self, "show")

    def _on_scale_changed(self, _factor: float) -> None:
        self._host_layout.setContentsMargins(
            scaled_px(8), scaled_px(4), scaled_px(8), scaled_px(4)
        )
        self._host_layout.setSpacing(scaled_px(8))
        for row in self._rows:
            if row.custom:
                continue
            row.button.setGap(scaled_px(_ICON_TEXT_GAP))
            row.button.setContentPadding(
                (scaled_px(_LEFT_PADDING), 0.0, scaled_px(_LEFT_PADDING), 0.0)
            )
        # Rows grew/shrunk: a stale scroll offset keeps the *top* rows out
        # of the viewport ("eaten" rows) — jump back to the top so the first
        # section is visible after any factor change.
        self._scroll.verticalScrollBar().setValue(0)
        self.refresh_icons()
        self.updateGeometry()
        self.update()
        schedule_layout_debug(self, "scale_changed")

    # -------- public: items --------

    def set_items(
        self,
        items: Iterable[IconListItem | tuple],
    ) -> None:
        self.clear()
        for item in items:
            if isinstance(item, IconListItem):
                spec = item
            elif isinstance(item, tuple):
                spec = self._item_from_tuple(item)
            else:
                spec = IconListItem(text=str(item))
            self._append_row(spec)
        self._rebuild_visible()
        schedule_layout_debug(self, "set_items")

    def add_item(
        self,
        text: str,
        icon: object | None = None,
        data: object | None = None,
        row_height: int | None = None,
        selected_icon: object | None = None,
        search_texts: tuple[str, ...] = (),
    ) -> _ListItem:
        spec = IconListItem(
            text=text,
            icon=icon,
            data=data,
            row_height=row_height or self._row_height,
            selected_icon=selected_icon,
            search_texts=search_texts,
        )
        self._append_row(spec)
        self._rebuild_visible()
        return _ListItem(self, len(self._rows) - 1)

    def clear(self) -> None:
        for row in self._rows:
            row.button.setParent(None)
            row.button.deleteLater()
        self._rows.clear()
        # The no-results row is search chrome, not content — keep it across
        # rebuilds (hidden until a search with zero matches needs it).
        if self._no_results_row is not None:
            self._no_results_row.button.setVisible(False)
        self._filter_query = ""
        self._visible = []
        prev_current = self._current_row
        self._current_row = -1
        # Reset scroll so the first row stays visible after any rebuild —
        # otherwise a stale scroll offset "eats" the top rows.
        self._scroll.verticalScrollBar().setValue(0)
        if prev_current != -1:
            self.currentRowChanged.emit(-1)
            self.currentItemChanged.emit(None, None)

    def count(self) -> int:
        """Visible row count (filter-aware; 1 when the no-results row shows)."""
        if self._visible:
            return len(self._visible)
        if self._filter_query and self._rows:
            return 1 if self._no_results_row is not None else 0
        return len(self._rows)

    def item(self, idx: int) -> _ListItem | None:
        if idx == 0 and not self._visible and self._no_results_row is not None:
            return _ListItem(self, -1)
        if 0 <= idx < len(self._visible):
            return _ListItem(self, self._visible[idx])
        return None

    def row_button(self, idx: int) -> QWidget | None:
        """Nav-row Button for visible row ``idx``, or ``None`` if out of range.

        Host Find Action reveal uses this instead of poking ``_rows`` /
        ``_ListItem._spec``.
        """
        if idx == 0 and not self._visible and self._no_results_row is not None:
            return self._no_results_row.button
        if 0 <= idx < len(self._visible):
            return self._rows[self._visible[idx]].button
        return None

    def visible_source_index(self, idx: int) -> int:
        """Map a visible row index back to its source-row index."""
        if 0 <= idx < len(self._visible):
            return self._visible[idx]
        return -1

    # -------- public: search / filtering (ComboBox-style) --------

    def set_search_text(self, query: str) -> None:
        """Filter rows in place; no widget rebuilds per keystroke.

        Matches the display text plus each row's pre-normalized
        ``search_texts`` (cross-language haystacks), ranked by the same
        ``match_score_normalized`` scoring the toolkit ComboBox uses. Empty
        query restores the full list. Rows with no match stay hidden.
        """
        query = (query or "").strip()
        if query == self._filter_query:
            return
        self._filter_query = query
        self._rebuild_visible()

    def set_no_results_text(self, text: str) -> None:
        """Label for the single placeholder row shown when a search matches
        nothing (hidden when the search is empty or has hits)."""
        if self._no_results_row is not None:
            self._no_results_row.button.setText(text)
            self._no_results_row.text = text
            return
        if not text:
            return
        row = _RowSpec(
            text=text,
            icon=None,
            selected_icon=None,
            row_height=self._row_height,
            button=_make_nav_row_button(
                text=text,
                icon=None,
                row_height=self._row_height,
                icon_size_px=(
                    self._icon_size.height()
                    if isinstance(self._icon_size, QSize)
                    else 24
                ),
            ),
            custom=self._button_factory is not None,
        )
        row.button.setMinimumWidth(0)
        row.button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        row.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._no_results_row = row
        insert_at = max(0, self._host_layout.count() - 1)
        self._host_layout.insertWidget(insert_at, row.button)
        self._rebuild_visible()

    def _rebuild_visible(self) -> None:
        query = self._filter_query
        if not query or not self._rows:
            self._visible = list(range(len(self._rows)))
        else:
            norm_query = normalize_for_search(query)
            scored: list[tuple[int, int]] = []
            for index, row in enumerate(self._rows):
                score = _row_match_score(norm_query, row)
                if score is not None:
                    scored.append((score, index))
            scored.sort(key=lambda item: (item[0], item[1]))
            self._visible = [index for _score, index in scored]

        visible_set = set(self._visible)
        for index, row in enumerate(self._rows):
            row.button.setVisible(index in visible_set)
        if self._no_results_row is not None:
            show_no_results = bool(query) and not self._visible and bool(self._rows)
            self._no_results_row.button.setVisible(show_no_results)

        # A new visible set reflows the list — jump to the top so the first
        # result is in view (same reset ``clear()`` does on rebuild).
        self._scroll.verticalScrollBar().setValue(0)

        if self._current_row >= 0 and self._current_row not in visible_set:
            self._current_row = -1
            self.currentRowChanged.emit(-1)
            self.currentItemChanged.emit(None, None)

    # -------- public: selection --------

    def currentRow(self) -> int:
        return self._current_row

    def setCurrentRow(self, idx: int) -> None:
        # ``idx`` is a *visible* row index; map it to the source row.
        if idx < 0 or not self._visible or idx >= len(self._visible):
            source = -1
        else:
            source = self._visible[idx]
        if source == self._current_row:
            return
        prev = self._current_row
        self._current_row = source
        for row in self._rows:
            row.button.setRegionChecked("_main", row is not None and False)
        if source >= 0:
            self._rows[source].button.setRegionChecked("_main", True)
        for row in self._rows:
            update_row_icon(row)
            update_row_fg(row)
        prev_item = _ListItem(self, prev) if prev >= 0 else None
        curr_item = _ListItem(self, source) if source >= 0 else None
        self.currentRowChanged.emit(idx if source >= 0 else -1)
        self.currentItemChanged.emit(curr_item, prev_item)

    # -------- public: icons --------

    def iconSize(self) -> QSize:
        return QSize(self._icon_size)

    def setIconSize(self, size: QSize) -> None:
        if not isinstance(size, QSize) or not size.isValid():
            return
        self._icon_size = QSize(size)
        for row in self._rows:
            if row.custom:
                continue
            row.button.setIconSize(self._icon_size)
            apply_row_icon(row, self._icon_size, self._selected_icon_mode)

    def refresh_icons(self) -> None:
        for row in self._rows:
            if row.custom:
                continue
            apply_row_icon(row, self._icon_size, self._selected_icon_mode)
            update_row_fg(row)

    def selectedIconMode(self) -> SelectedIconMode:
        return self._selected_icon_mode

    def setSelectedIconMode(self, mode: str) -> None:
        normalized = normalize_selected_icon_mode(mode)
        if normalized == self._selected_icon_mode:
            return
        self._selected_icon_mode = normalized
        self.refresh_icons()

    set_selected_icon_mode = setSelectedIconMode

    def _refresh_row_icon(self, row: _RowSpec) -> None:
        """Re-resolve one row's icons (used by the ``_ListItem`` proxy)."""
        apply_row_icon(row, self._icon_size, self._selected_icon_mode)

    # -------- public: scroll appearance --------

    def enable_minimal_scrollbar(self) -> None:
        """No-op: the nav list always uses the floating overlay scrollbar
        (kept for API compatibility with older hosts)."""

    # -------- internals --------

    def _append_row(self, spec: IconListItem) -> None:
        icon, selected_icon_from_pair = _split_icon_pair(spec.icon)
        selected_icon = spec.selected_icon
        if selected_icon is None:
            selected_icon = selected_icon_from_pair

        custom = self._button_factory is not None
        if self._button_factory is not None:
            button = self._button_factory(spec)
        else:
            button = _make_nav_row_button(
                text=spec.text,
                icon=None,
                row_height=spec.row_height or self._row_height,
                icon_size_px=self._icon_size.height() if isinstance(self._icon_size, QSize) else 24,
            )
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row = _RowSpec(
            text=spec.text,
            icon=icon,
            selected_icon=selected_icon,
            row_height=spec.row_height or self._row_height,
            button=button,
            custom=custom,
            normalized_texts=tuple(
                dict.fromkeys(
                    normalize_for_search(text)
                    for text in ((spec.text, *spec.search_texts))
                    if text
                )
            ),
        )
        if spec.data is not None:
            row.data_roles[int(Qt.ItemDataRole.UserRole)] = spec.data
        self._rows.append(row)

        apply_row_icon(row, self._icon_size, self._selected_icon_mode)

        index = len(self._rows) - 1
        button.clicked.connect(lambda _i=index: self._on_row_clicked(_i))

        insert_at = self._host_layout.count() - 1
        if insert_at < 0:
            insert_at = 0
        self._host_layout.insertWidget(insert_at, button)

    def _on_row_clicked(self, source_idx: int) -> None:
        # Clicks come from source-row lambdas; map back to the visible row.
        if source_idx == self._current_row:
            return
        try:
            visible_idx = self._visible.index(source_idx)
        except ValueError:
            return
        self.setCurrentRow(visible_idx)

    def _item_from_tuple(self, item: tuple) -> IconListItem:
        if len(item) <= 4:
            return IconListItem(*item)
        text, icon, data, row_height, selected_icon = item[:5]
        return IconListItem(
            text=text,
            icon=icon,
            data=data,
            row_height=row_height,
            selected_icon=selected_icon,
        )

IconListWidget.inspect_spec = InspectSpec(  # type: ignore[attr-defined]
    family="IconListWidget",
    state=(
        SpecField("count", "count"),
        SpecField("current_row", "currentRow"),
        SpecField("rows", _row_texts),
    ),
    token_family=(
        "list_item.background.normal",
        "list_item.background.hover",
        "list_item.background.selected",
        "list_item.icon.selected",
        "accent",
    ),
    docs='docs/user/LIST_ITEMS_API.md',
)