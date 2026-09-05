"""ListPanel top margin — rows must not hug the content's top edge.

Regression: rows are positioned absolutely by VirtualListController (the
content_layout's own 4px margins never reach them vertically), and the
controller only knew ``x_margin`` — so the first row sat at y=0 while the
left gap was 4px. The controller now takes ``y_margin`` (default 0) and
ListPanel passes its top content margin, symmetric with the horizontal one.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.composite.list_panel import ListPanel


class Row(QWidget):
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


def _make_item(i):
    return type("I", (), {
        "display_name": f"item-{i}",
        "path": f"/x/item-{i}",
        "rating": 0,
    })()


def _build_panel(qtbot, count=5, item_height=36):
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
    panel.clear_and_rebuild([_make_item(i) for i in range(count)], item_height, None)
    host.show()
    qtbot.waitExposed(host)
    qtbot.wait(50)
    return host, panel


def test_first_row_starts_below_top_margin(qtbot):
    _host, panel = _build_panel(qtbot)
    margin = scaled_px(panel._content_margin_px)
    assert margin > 0
    rows = sorted(panel._item_widgets(), key=lambda w: w.index)
    assert len(rows) == 5
    first = rows[0]
    # Symmetric gaps: same inset from the left and from the top.
    assert first.geometry().x() == margin
    assert first.geometry().y() == margin


def test_row_offsets_include_top_margin(qtbot):
    _host, panel = _build_panel(qtbot)
    margin = scaled_px(panel._content_margin_px)
    pitch = panel._row_pitch()
    assert panel._controller._offset_of_index(0) == margin
    assert panel._controller._offset_of_index(2) == margin + 2 * pitch
    assert panel._controller._content_height() == margin + 5 * pitch
