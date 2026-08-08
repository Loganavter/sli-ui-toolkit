"""GearDragCapability: begin/update/release, snap-then-close, overflow downgrade."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.comboboxes.capabilities import GearDragCapability
from sli_ui_toolkit.widgets import ComboBox


def _make_combo(host, items, *, max_visible=12):
    combo = ComboBox(parent=host)
    combo.addItems(items)
    combo.setMaxVisibleItems(max_visible)
    combo.setCurrentIndex(0)
    combo.move(40, 160)
    return combo


def test_begin_drag_arms_and_opens_dropdown(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = _make_combo(host, ["A", "B", "C", "D", "E"])
    host.show()
    qtbot.waitExposed(host)

    gear = combo._gear
    assert isinstance(gear, GearDragCapability)
    assert combo.get_capability(GearDragCapability) is gear

    # handle_press gates on event.spontaneous(), which synthetic events from
    # tests never set — seed state the way a real press would and drive the
    # gesture through the capability's internals directly.
    gear._press_pos = QPointF(0, 0)
    gear._anchor_index = combo.currentIndex()
    gear._begin_drag()

    assert gear.active is True
    assert combo._expanded is True
    assert combo._gear_active is True  # proxy property _overlay.py reads
    assert gear.focus_index == 0
    assert gear._window_origin is not None


def test_update_drag_moves_focus_index_by_item_height(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = _make_combo(host, ["A", "B", "C", "D", "E"])
    host.show()
    qtbot.waitExposed(host)

    gear = combo._gear
    gear._press_pos = QPointF(0, 0)
    gear._anchor_index = combo.currentIndex()
    gear._begin_drag()

    item_h = combo._item_height()
    gear._update_drag(QPointF(0, -item_h))  # drag up one row
    assert gear.focus_index == 1
    assert combo._gear_focus_index == 1


def test_release_after_drag_snaps_then_commits_and_closes(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = _make_combo(host, ["A", "B", "C", "D", "E"])
    host.show()
    qtbot.waitExposed(host)

    gear = combo._gear
    gear._press_pos = QPointF(0, 0)
    gear._anchor_index = combo.currentIndex()
    gear._begin_drag()
    item_h = combo._item_height()
    gear._update_drag(QPointF(0, -round(item_h * 0.6)))  # off-boundary -> snap needed

    gear._finish_drag()
    assert gear.snap_in_progress is True
    assert combo._expanded is True  # hideDropdown() no-ops mid-snap

    qtbot.waitUntil(lambda: gear.snap_in_progress is False, timeout=1000)
    assert combo._expanded is False
    assert combo.currentIndex() == 1


def test_overflow_drag_downgrades_to_plain_open(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    items = [f"item-{i}" for i in range(20)]
    combo = _make_combo(host, items, max_visible=5)
    host.show()
    qtbot.waitExposed(host)

    gear = combo._gear
    gear._press_pos = QPointF(0, 0)
    gear._anchor_index = combo.currentIndex()
    gear._begin_drag()

    assert gear.active is False  # never armed
    assert gear._overflow_open_only is True
    assert combo._expanded is True  # opened like a plain click instead
    assert gear._press_pos is None
