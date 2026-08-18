"""ListPanel - scrollable multi-select list panel with drag&drop.

The panel owns the widget tree (scroll area, rows, drop indicator, marquee
gesture) and orchestrates its pieces; all decision logic lives outside it
in state-owning objects and pure functions with explicit inputs:

- ``selection.MarqueeSelectionModel`` - the selection set + band semantics
  (the panel only applies visuals);
- ``drag_drop.drop_target_index`` / ``should_hide_indicator`` - insertion
  math and no-op-drop detection (pure, widget-free);
- ``rows`` - the row spec contract and pure item/position transforms.

The panel keeps thin delegator methods with the same public names hosts
and tests rely on.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.config import get_dragdrop_service
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from sli_ui_toolkit.ui.widgets.helpers.multi_move import payload_indices
from sli_ui_toolkit.ui.widgets.overlays.marquee_band_gesture import MarqueeBandGesture
from sli_ui_toolkit.ui.widgets.virtual_list import VirtualListController

from .drag_drop import _DropIndicator, drop_target_index, should_hide_indicator
from .rows import (
    ListRowSpec,
    RowFactory,
    apply_item_data,
)
from .selection import (
    MarqueeSelectionModel,
    indices_intersecting_rect,
    sync_row_visuals,
)


class ListPanel(QWidget):
    """Scrollable list panel: marquee selection, drag&drop, host-built rows.

    The panel renders whatever widgets ``row_factory`` returns for each
    item; rows must expose the duck-typed protocol the panel relies on:
    ``itemSelected``/``itemSelectionToggled``/``itemRightClicked`` signals,
    ``index``/``full_path``/``is_current``/``position`` attributes, a
    ``name_label`` (and optionally ``rating_label``) for in-place data
    refresh, and — for hosts that support selection/drag visuals —
    ``set_selected(bool)`` / ``set_dragging_state(bool)``.
    """

    # Panel scrolls after ~7.5 rows of content (compact-density default).
    MAX_VISIBLE_ITEMS = 7

    def __init__(
        self,
        list_num: int,
        item_height: int,
        item_font,
        get_current_index: Callable[[int], int],
        on_item_selected: Callable[[int, int], None],
        on_item_context_menu: Callable[[int, int], None],
        on_reorder: Callable[[int, Any, int], None],
        on_move_between_lists: Callable[[int, Any, int, int], None],
        on_update_drop_indicator: Callable[[QPointF], None],
        on_clear_drop_indicator: Callable[[], None],
        parent=None,
    ):
        super().__init__(parent)
        self.list_num = list_num
        self.item_height = item_height
        self.item_font = item_font
        self._get_current_index = get_current_index
        self._on_item_selected_cb = on_item_selected
        self._on_item_context_menu_cb = on_item_context_menu
        self._on_reorder = on_reorder
        self._on_move_between_lists = on_move_between_lists
        self._on_update_drop_indicator = on_update_drop_indicator
        self._on_clear_drop_indicator = on_clear_drop_indicator
        self._row_factory: RowFactory | None = None
        self.theme_manager = ThemeManager.get_instance()
        self.drop_indicator_y = -1
        self._container_height = 50
        self._list_type: str = "default"
        self._selection = MarqueeSelectionModel()
        self._marquee_gesture = None

        self.setObjectName("ListPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.layout_outer = QVBoxLayout(self)
        self.layout_outer.setContentsMargins(1, 1, 1, 1)
        self.layout_outer.setSpacing(0)

        self.scroll_area = OverlayScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.set_corner_radius(8)

        self.content_widget = QWidget()

        # Compat shim: hosts still read content_layout.spacing() for panel
        # height math. Rows are positioned absolutely by the virtual-list
        # controller below, not by this layout.
        self.content_layout = QVBoxLayout(self.content_widget)
        # Compact panel padding: design px, scaled by the UiScale factor so
        # the row gaps grow with the rows (see _reapply_scale_padding).
        self._content_margin_px = 4
        self._content_spacing_px = 2
        self._reapply_scale_padding()

        self.scroll_area.setWidget(self.content_widget)
        self.layout_outer.addWidget(self.scroll_area)

        self.drop_overlay = _DropIndicator(self.content_widget)

        self.setMinimumHeight(0)
        self.scroll_area.setMinimumHeight(0)

        self.content_widget.setMouseTracking(True)
        self.content_widget.installEventFilter(self)

        # Virtualized row pool: only the visible window of rows exists as
        # widgets; scrolling/search/refresh rebinds the pooled rows instead
        # of building one widget per item. See ui.widgets.virtual_list.
        self._items: list = []
        self._current_app_index = -1
        self._controller = VirtualListController(
            self.scroll_area, self.content_widget,
            factory=self._make_row_widget,
            bind=self._bind_row,
            row_height=self._row_pitch(),
            widget_height=self.item_height,
            x_margin=scaled_px(self._content_margin_px),
            overscan=2,
        )

        self._apply_style()
        self.theme_manager.theme_changed.connect(self._apply_style)
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

    # -------- row factory --------

    def set_row_factory(self, factory: RowFactory | None) -> None:
        """Set the callable building one row widget per ``ListRowSpec``.

        ``None`` restores the "no factory" state; building rows then raises
        until a factory is provided.
        """
        self._row_factory = factory

    def row_factory(self) -> RowFactory | None:
        return self._row_factory

    # -------- scaling / padding --------

    def _reapply_scale_padding(self) -> None:
        self.content_layout.setContentsMargins(
            *[scaled_px(self._content_margin_px)] * 4
        )
        self.content_layout.setSpacing(scaled_px(self._content_spacing_px))

    def _on_scale_changed(self, _factor: float) -> None:
        # Panel persists across opens (rows rebuild per open); keep the row
        # gaps in step with the interface scale.
        self._reapply_scale_padding()
        self._controller.set_row_height(self._row_pitch())
        self.recalculate_and_set_height()
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        try:
            width_hint = max(self.scroll_area.sizeHint().width(), 200)
        except Exception:
            width_hint = 200
        return QSize(width_hint, self._container_height)

    def _apply_style(self):
        try:
            accent = self.theme_manager.get_color("accent")
        except Exception:
            accent = QColor("#00b7ff")
        self.drop_overlay.set_color(accent)

        # Paint the panel surface ourselves so the widget renders correctly
        # without a host-supplied QSS sheet. Selector keyed on the widget's
        # own objectName — subclasses that keep their legacy name (e.g. the
        # flyout panel) still match their own rule.
        try:
            bg_color = self.theme_manager.get_color("flyout.background").name(
                QColor.NameFormat.HexArgb
            )
            border_color = self.theme_manager.get_color("flyout.border").name(
                QColor.NameFormat.HexArgb
            )
        except Exception:
            return
        self.setStyleSheet(
            f"#{self.objectName()} {{"
            f"background-color: {bg_color};"
            f"border: 1px solid {border_color};"
            "border-radius: 8px;"
            "}"
        )
        try:
            self.scroll_area.setStyleSheet(
                "background-color: transparent; border: none;"
            )
            self.content_widget.setStyleSheet("background: transparent;")
        except Exception:
            pass

    # -------- row building / list content --------

    def _row_pitch(self) -> int:
        """Vertical pitch between row tops: row height + row gap."""
        row_h = self.item_height if self.item_height > 0 else 36
        return max(1, row_h) + scaled_px(self._content_spacing_px)

    def _template_spec(self) -> ListRowSpec:
        """Static spec fields shared by every pooled row; dynamic data
        (index/text/rating/position/is_current) is pushed by ``_bind_row``."""
        return ListRowSpec(
            index=0,
            text="",
            full_path="",
            list_num=self.list_num,
            is_current=False,
            item_height=self.item_height,
            item_font=self.item_font,
            item_type=self._list_type or "default",
            position="only",
            on_update_drop_indicator=self._on_update_drop_indicator,
            on_clear_drop_indicator=self._on_clear_drop_indicator,
            rating=0,
        )

    def _make_row_widget(self):
        """Pool factory: build one row widget and wire its signals once.

        Signals are connected here (not per rebind) because the pooled rows
        emit their own ``index`` attribute at emit time — rebinding just
        updates ``widget.index`` and the same connections stay correct.
        """
        factory = self._row_factory
        if factory is None:
            raise RuntimeError(
                "ListPanel has no row factory — call set_row_factory() before "
                "populating (list_num=%s)" % self.list_num
            )
        item_widget = factory(self._template_spec())
        item_widget.itemSelected.connect(self._on_item_clicked)
        item_widget.itemSelectionToggled.connect(self._on_item_selection_toggled)
        item_widget.itemRightClicked.connect(self._on_context_menu)
        return item_widget

    def _bind_row(self, index: int, widget) -> None:
        """Push item ``index``'s data onto a pooled row widget."""
        if not (0 <= index < len(self._items)):
            return
        total = len(self._items)
        apply_item_data(
            widget, index, self._items[index], self._current_app_index, total
        )
        sync_row_visuals([widget], self._selection.indices())

    def clear_and_rebuild(
        self,
        items,
        item_height,
        item_font,
        list_type: str = "default",
        current_index=-1,
    ):
        PathTooltip.get_instance().hide_tooltip()
        self.clear_drop_indicator()

        self._list_type = list_type
        self.item_height = item_height
        self.item_font = item_font
        self._items = list(items)
        if current_index == -1:
            self._current_app_index = self._get_current_index(self.list_num)
        else:
            self._current_app_index = current_index

        # Virtualized: rebinding the visible window is cheap, so a "rebuild"
        # is just a count change + rebind — no per-row widget churn.
        preserve_scroll = self.isVisible()
        self._controller.set_row_height(self._row_pitch())
        self._controller.set_count(len(self._items))
        self._controller.rebind()
        self.recalculate_and_set_height()
        self.clear_selection()
        if not preserve_scroll and self._current_app_index >= 0:
            QTimer.singleShot(0, lambda: self._ensure_visible(self._current_app_index))

    def sync_with_list(
        self,
        items,
        item_height,
        item_font,
        list_type: str = "default",
        current_index=-1,
    ):
        self._list_type = list_type
        self.item_height = item_height
        self.item_font = item_font
        new_items = list(items)
        # Selection survives when the list content is unchanged (paths equal),
        # matching the old in-place refresh semantics; a real content change
        # clears it like a full rebuild.
        old_paths = [getattr(item, "path", "") for item in self._items]
        new_paths = [getattr(item, "path", "") for item in new_items]
        content_changed = old_paths != new_paths

        self._items = new_items
        if current_index == -1:
            self._current_app_index = self._get_current_index(self.list_num)
        else:
            self._current_app_index = current_index

        preserve_scroll = self.isVisible()
        self._controller.set_row_height(self._row_pitch())
        self._controller.set_count(len(self._items))
        self._controller.rebind()
        self.recalculate_and_set_height()
        if content_changed:
            self.clear_selection()
        if not preserve_scroll and self._current_app_index >= 0:
            QTimer.singleShot(0, lambda: self._ensure_visible(self._current_app_index))

    def _ensure_visible(self, index):
        self._controller.ensure_visible(index)

    def _item_widgets(self):
        """Materialized (visible-window) row widgets."""
        widgets = []
        start, end = self._controller.window()
        for i in range(start, end):
            widget = self._controller.widget_for_index(i)
            if widget is not None:
                widgets.append(widget)
        return widgets

    # -------- sizing --------

    def recalculate_and_set_height(self, max_height: int | None = None):
        """Size the panel: natural height up to 8 rows, else MAX_VISIBLE_ITEMS.

        The virtual-list controller owns the content height and row
        positioning; this only clamps the panel/scroll-area viewport height.
        """
        num_items = self._controller.count

        if num_items <= 0:
            row_h = self.item_height if self.item_height > 0 else 36
            final_height = self._constrained_height(row_h, max_height)
            self._container_height = final_height
            self.setMinimumHeight(0)
            self.setMaximumHeight(final_height)
            self.scroll_area.setMinimumHeight(0)
            self.scroll_area.setMaximumHeight(final_height)
            self._deferred_scrollbar_sync()
            return final_height

        pitch = self._row_pitch()

        if num_items <= 8:
            natural_h = num_items * pitch + 10
            final_h = self._constrained_height(natural_h, max_height)
            self._container_height = final_h
            self.setMinimumHeight(0 if final_h < natural_h else final_h)
            self.setMaximumHeight(final_h)
            self.scroll_area.setMinimumHeight(0 if final_h < natural_h else final_h)
            self.scroll_area.setMaximumHeight(final_h)
        else:
            visible_items = min(num_items, self.MAX_VISIBLE_ITEMS)
            max_h = visible_items * pitch + 10
            final_h = self._constrained_height(max_h, max_height)
            self._container_height = final_h
            self.setMinimumHeight(0)
            self.setMaximumHeight(final_h)
            self.scroll_area.setMinimumHeight(0)
            self.scroll_area.setMaximumHeight(final_h)

        self._deferred_scrollbar_sync()
        return final_h

    def _deferred_scrollbar_sync(self):
        # The viewport height settles on the next layout pass; re-derive the
        # visible window + scrollbar range after it does. The singleShot is
        # not cancelled by widget destruction — guard against it (same
        # pattern as SimpleOptionsFlyout._deferred_update_size).
        def _rebind():
            try:
                import shiboken6  # type: ignore[attr-defined]

                if not shiboken6.Shiboken.isValid(self):
                    return
            except Exception:
                pass
            controller = self._controller
            if controller is not None:
                try:
                    controller.rebind()
                except RuntimeError:
                    pass

        QTimer.singleShot(20, _rebind)

    def _constrained_height(self, height: int, max_height: int | None) -> int:
        if max_height is None:
            return height
        return max(1, min(height, int(max_height)))

    # -------- drag&drop --------

    def find_drop_target(self, local_pos_y: int) -> tuple[int, int]:
        """Insertion index + indicator Y — pure math over the visible rows."""
        return drop_target_index(self._row_geometries(), local_pos_y)

    def _should_hide_drop_indicator(self, dest_index: int) -> bool:
        try:
            service = get_dragdrop_service()
        except Exception:
            return False

        if not service or not service.is_dragging():
            return False

        payload = None
        try:
            payload = (
                service.get_source_data()
                if hasattr(service, "get_source_data")
                else None
            )
        except Exception:
            payload = None
        if not payload:
            payload = getattr(service, "_source_data", None)

        return should_hide_indicator(payload, self.list_num, dest_index)

    def update_drop_indicator(self, global_pos: QPointF):
        local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())
        dest_index, indicator_y = self.find_drop_target(local_pos.y())

        if self._should_hide_drop_indicator(dest_index):
            indicator_y = -1

        if self.drop_indicator_y != indicator_y:
            self.drop_indicator_y = indicator_y
            self._show_overlay_indicator()

    def _show_overlay_indicator(self):
        if self.drop_indicator_y < 0:
            self.drop_overlay.hide()
            return

        x = 2
        width = max(4, self.content_widget.width() - 4)
        height = 3

        y = int(self.drop_indicator_y) - height // 2

        self.drop_overlay.setGeometry(x, y, width, height)
        self.drop_overlay.raise_()
        self.drop_overlay.show()

    def clear_drop_indicator(self):
        if self.drop_indicator_y != -1:
            self.drop_indicator_y = -1
            self.drop_overlay.hide()

    def handle_drop(self, payload: dict, global_pos: QPointF):
        self.clear_drop_indicator()
        source_list_num = payload.get("list_num", -1)
        indices = payload_indices(payload)
        if not indices:
            return

        local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())
        dest_index, _ = self.find_drop_target(local_pos.y())

        if source_list_num == self.list_num:
            QTimer.singleShot(
                0,
                lambda: self._on_reorder(
                    self.list_num,
                    indices,
                    dest_index,
                ),
            )
        else:
            self._on_move_between_lists(
                source_list_num,
                indices,
                self.list_num,
                dest_index,
            )
        self.clear_selection()

    @property
    def image_number(self) -> int:
        return self.list_num

    @image_number.setter
    def image_number(self, value: int) -> None:
        self.list_num = int(value)

    # -------- selection --------

    def selected_indices(self) -> set[int]:
        return self._selection.indices()

    def clear_selection(self) -> None:
        self._selection.clear()
        self._sync_selection_visuals()

    def set_selected_indices(self, indices) -> None:
        self._selection.set_indices(indices)
        self._sync_selection_visuals()

    def set_items_dragging(self, indices, dragging: bool) -> None:
        wanted = {int(i) for i in (indices or [])}
        for widget in self._item_widgets():
            if widget.index in wanted:
                widget.set_dragging_state(dragging)

    def _sync_selection_visuals(self) -> None:
        sync_row_visuals(self._item_widgets(), self._selection.indices())

    def _on_item_selection_toggled(self, index: int) -> None:
        self._selection.toggle(index)
        self._sync_selection_visuals()

    # -------- marquee selection --------

    def _ensure_marquee_gesture(self):
        if self._marquee_gesture is None:
            self._marquee_gesture = MarqueeBandGesture(
                self.content_widget,
                parent=self,
                clip_widget=self.scroll_area.viewport(),
                on_update=self._on_marquee_rect_update,
                on_finish=self._on_marquee_rect_finish,
            )
            try:
                accent = QColor(self.theme_manager.get_color("accent"))
                base = QColor(self.theme_manager.get_color("flyout.background"))
                pastel = QColor(
                    int(round(accent.red() * 0.38 + base.red() * 0.62)),
                    int(round(accent.green() * 0.38 + base.green() * 0.62)),
                    int(round(accent.blue() * 0.38 + base.blue() * 0.62)),
                )
                self._marquee_gesture.set_accent(pastel)
            except Exception:
                pass
        else:
            self._marquee_gesture.set_clip_widget(self.scroll_area.viewport())
        return self._marquee_gesture

    def _row_geometries(self) -> list[tuple[int, QRect]]:
        """(item index, geometry) for the materialized rows, in content coords.

        Only visible-window rows exist as widgets; their item indices and
        geometries are exactly what the marquee and drop-target math need.
        """
        rows = []
        start, end = self._controller.window()
        for index in range(start, end):
            widget = self._controller.widget_for_index(index)
            if widget is not None and not widget.isHidden():
                rows.append((index, widget.geometry()))
        return rows

    def _on_marquee_rect_update(self, rect: QRect) -> None:
        band = indices_intersecting_rect(rect, self._row_geometries())
        preview = self._selection.preview(band)
        # Preview without committing until finish.
        for widget in self._item_widgets():
            setter = getattr(widget, "set_selected", None)
            if callable(setter):
                setter(widget.index in preview)

    def _on_marquee_rect_finish(self, rect: QRect) -> None:
        if rect.isEmpty():
            self._selection.finish_empty()
            self._sync_selection_visuals()
            return
        band = indices_intersecting_rect(rect, self._row_geometries())
        self._selection.commit(band)
        self._sync_selection_visuals()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.content_widget and isinstance(event, QMouseEvent):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    pos = event.position().toPoint()
                    child = self.content_widget.childAt(pos)
                    edge_gap = getattr(child, "marquee_edge_gap_px", 0) or 0
                    if edge_gap > 0:
                        # Rows whose background is visually inset (e.g. 2px)
                        # plus the layout spacing leave a strip that *looks*
                        # like a gap between rows but still belongs to the
                        # row widgets. Treat presses in that edge strip as
                        # empty space so the marquee can start "between" rows.
                        geo = child.geometry()
                        if (
                            pos.y() - geo.top() <= edge_gap
                            or geo.bottom() - pos.y() <= edge_gap
                        ):
                            # PySide6-stubs types childAt() as returning
                            # QWidget (non-Optional), though it returns None
                            # at runtime when the point hits empty space —
                            # the `if child is None:` check below relies on it.
                            child = None  # type: ignore[assignment]
                    if child is None:
                        mods = event.modifiers()
                        self._selection.begin_band(
                            bool(
                                mods
                                & (
                                    Qt.KeyboardModifier.ControlModifier
                                    | Qt.KeyboardModifier.MetaModifier
                                )
                            )
                        )
                        gesture = self._ensure_marquee_gesture()
                        ok = gesture.start(event.position().toPoint())
                        if ok:
                            if not self._selection.additive:
                                self._on_marquee_rect_update(QRect())
                            return True
        return super().eventFilter(watched, event)

    # -------- host-facing row refresh hooks --------

    def update_item(self, index: int):
        """Refresh a materialized row's data in place (no-op when hidden —
        hidden pooled rows get fresh data on the next rebind anyway)."""
        if not (0 <= index < len(self._items)):
            return
        widget = self._controller.widget_for_index(index)
        if widget is None:
            return
        update_label = getattr(widget, "_update_label_from_store", None)
        if callable(update_label):
            update_label()
        else:
            apply_item_data(
                widget, index, self._items[index], self._current_app_index,
                len(self._items),
            )

    def _on_item_clicked(self, index):
        self._on_item_selected_cb(self.list_num, index)

    def _on_context_menu(self, index):
        self._on_item_context_menu_cb(self.list_num, index)


ListPanel.inspect_spec = InspectSpec(  # type: ignore[attr-defined]
    family="ListPanel",
    state=(
        SpecField("list_num", "list_num"),
        SpecField("item_height", "item_height"),
        SpecField("list_type", "_list_type", private=True),
        SpecField("selected_indices", "selected_indices"),
        SpecField("drop_indicator_y", "drop_indicator_y"),
    ),
    token_family=("flyout.background", "flyout.border", "accent"),
    docs='docs/user/LIST_ITEMS_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

ListPanel.widget_descriptor = WidgetDescriptor(
    family=ListPanel.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ListPanel.inspect_spec, 'config', ()),
        state=ListPanel.inspect_spec.state,
        token_family=getattr(ListPanel.inspect_spec, 'token_family', ()),
        regions=getattr(ListPanel.inspect_spec, 'regions', False),
        layers=getattr(ListPanel.inspect_spec, 'layers', False),
        docs=getattr(ListPanel.inspect_spec, 'docs', ''),
        preview_seed=getattr(ListPanel.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ListPanel.inspect_spec, 'apply_config_refresh', None),
    ),
)