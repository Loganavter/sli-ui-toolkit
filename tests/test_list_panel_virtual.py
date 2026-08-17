"""ListPanel virtualization tests — bounded row pool + scroll rebinding.

The panel must materialize only the visible window of rows (plus overscan),
rebind them on scroll, and keep the public API (populate, selection,
row access) working.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.ui.widgets.composite.list_panel import ListPanel


class Row(QLabel):
    itemSelected = Signal(int)
    itemSelectionToggled = Signal(int)
    itemRightClicked = Signal(int)

    def __init__(self, spec):
        super().__init__()
        self.index = spec.index
        self.full_path = ""
        self.is_current = False
        self.position = spec.position
        self.name_label = self

    def set_selected(self, s):
        self.is_selected = s

    def set_dragging_state(self, s):
        pass


def _make_item(i, prefix="item"):
    return type("I", (), {
        "display_name": f"{prefix}-{i}",
        "path": f"/x/{prefix}-{i}",
        "rating": 0,
    })()


def _build_panel(qtbot, count=40, item_height=36, max_height=None):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 400)
    panel = ListPanel(
        list_num=1,
        item_height=item_height,
        item_font=None,
        get_current_index=lambda n: 0,
        on_item_selected=lambda *a: None,
        on_item_context_menu=lambda *a: None,
        on_reorder=lambda *a: None,
        on_move_between_lists=lambda *a: None,
        on_update_drop_indicator=lambda *a: None,
        on_clear_drop_indicator=lambda *a: None,
        parent=host,
    )
    panel.set_row_factory(lambda spec: Row(spec))
    items = [_make_item(i) for i in range(count)]
    panel.clear_and_rebuild(items, item_height, None, current_index=0)
    if max_height is not None:
        panel.recalculate_and_set_height(max_height=max_height)
    host.show()
    qtbot.waitExposed(host)
    qtbot.wait(50)
    return host, panel, items


def _visible_rows(panel):
    return [w for w in panel._item_widgets() if not w.isHidden()]


def test_long_list_materializes_only_visible_window(qtbot):
    host, panel, items = _build_panel(qtbot, count=500)
    live = _visible_rows(panel)
    # MAX_VISIBLE_ITEMS=7 rows fit in the viewport; overscan adds a few.
    assert len(live) < 20
    assert len(live) >= 7
    # Data bound correctly: first row shows item 0.
    assert live[0].index == 0
    assert live[0].text() == "item-0"
    # Content sized for all 500 rows so scrolling has range.
    assert panel._controller.count == 500
    assert panel.content_widget.minimumHeight() >= 500 * 36


def test_scroll_rebinds_rows(qtbot):
    host, panel, items = _build_panel(qtbot, count=500)
    pitch = panel._row_pitch()
    panel.scroll_area.verticalScrollBar().setValue(400 * pitch)
    qtbot.wait(30)
    live = _visible_rows(panel)
    indices = {w.index for w in live}
    assert 0 not in indices  # top rows scrolled away
    assert 400 in indices  # the requested row is materialized
    texts = {w.text() for w in live}
    assert "item-400" in texts


def test_small_list_materializes_all_rows(qtbot):
    host, panel, items = _build_panel(qtbot, count=5)
    live = _visible_rows(panel)
    assert len(live) == 5
    assert panel.scroll_area.verticalScrollBar().maximum() == 0


def test_row_data_refreshes_on_rebind(qtbot):
    host, panel, items = _build_panel(qtbot, count=20)
    pitch = panel._row_pitch()
    # Scroll down and back: pooled rows must show fresh data for the new
    # window (stale text from a previous binding must not leak).
    panel.scroll_area.verticalScrollBar().setValue(5 * pitch)
    qtbot.wait(30)
    panel.scroll_area.verticalScrollBar().setValue(0)
    qtbot.wait(30)
    texts = {w.text() for w in _visible_rows(panel)}
    assert "item-0" in texts
    assert "item-19" not in texts  # far tail not materialized


def test_empty_list_materializes_nothing(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    panel = ListPanel(
        list_num=1,
        item_height=36,
        item_font=None,
        get_current_index=lambda n: 0,
        on_item_selected=lambda *a: None,
        on_item_context_menu=lambda *a: None,
        on_reorder=lambda *a: None,
        on_move_between_lists=lambda *a: None,
        on_update_drop_indicator=lambda *a: None,
        on_clear_drop_indicator=lambda *a: None,
        parent=host,
    )
    panel.set_row_factory(lambda spec: Row(spec))
    panel.clear_and_rebuild([], 36, None)
    assert _visible_rows(panel) == []
    assert panel._controller.count == 0