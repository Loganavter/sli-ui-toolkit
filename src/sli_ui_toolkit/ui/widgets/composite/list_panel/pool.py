"""ListPanel row-pool factory/bind wiring — split out of ``widget.py`` to
keep the facade thin. Functions take the panel as their first argument."""

from __future__ import annotations

from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

from .rows import ListRowSpec, apply_item_data
from .selection import sync_row_visuals


def row_pitch(panel) -> int:
    """Vertical pitch between row tops: row height + row gap."""
    row_h = panel.item_height if panel.item_height > 0 else 36
    return max(1, row_h) + scaled_px(panel._content_spacing_px)


def template_spec(panel) -> ListRowSpec:
    """Static spec fields shared by every pooled row; dynamic data
    (index/text/rating/position/is_current) is pushed by ``bind_row``."""
    return ListRowSpec(
        index=0,
        text="",
        full_path="",
        list_num=panel.list_num,
        is_current=False,
        item_height=panel.item_height,
        item_font=panel.item_font,
        item_type=panel._list_type or "default",
        position="only",
        on_update_drop_indicator=panel._on_update_drop_indicator,
        on_clear_drop_indicator=panel._on_clear_drop_indicator,
        rating=0,
    )


def make_row_widget(panel):
    """Pool factory: build one row widget and wire its signals once.

    Signals are connected here (not per rebind) because the pooled rows
    emit their own ``index`` attribute at emit time — rebinding just
    updates ``widget.index`` and the same connections stay correct.
    """
    factory = panel._row_factory
    if factory is None:
        raise RuntimeError(
            "ListPanel has no row factory — call set_row_factory() before "
            "populating (list_num=%s)" % panel.list_num
        )
    item_widget = factory(panel._template_spec())
    item_widget.itemSelected.connect(panel._on_item_clicked)
    item_widget.itemSelectionToggled.connect(panel._on_item_selection_toggled)
    item_widget.itemRightClicked.connect(panel._on_context_menu)
    return item_widget


def bind_row(panel, index: int, widget) -> None:
    """Push item ``index``'s data onto a pooled row widget."""
    if not (0 <= index < len(panel._items)):
        return
    total = len(panel._items)
    apply_item_data(
        widget, index, panel._items[index], panel._current_app_index, total
    )
    sync_row_visuals([widget], panel._selection.indices())
