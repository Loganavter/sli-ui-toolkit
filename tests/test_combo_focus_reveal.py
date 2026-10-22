"""ComboBox showDropdown focus_index + pulse Hide isolation."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import ComboBox


def test_show_dropdown_focus_index_does_not_change_current(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = ComboBox(parent=host)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    combo.move(40, 160)
    host.show()
    qtbot.waitExposed(host)

    combo.showDropdown(focus_index=2)
    assert combo._expanded is True
    assert combo.currentIndex() == 0
    assert combo._dropdown_focus_index == 2
    assert combo.currentText() == "A"
    row = combo.dropdown_row_widget(2)
    assert row is not None
    assert row._item_index == 2
    # Content identity: each dropdown row shows ITS item's text, never a
    # neighbour's (only _item_index was asserted before).
    for idx, label in enumerate(("A", "B", "C")):
        r = combo.dropdown_row_widget(idx)
        assert r._item_index == idx
        assert r._text == label

    combo.hideDropdown()
    assert combo._dropdown_focus_index is None
    assert combo.currentIndex() == 0


def test_unrelated_overlay_hide_does_not_close_dropdown(qtbot):
    """Pulse-style overlays hide after a timer; that Hide must not dismiss us."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = ComboBox(parent=host)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    combo.move(40, 160)
    host.show()
    qtbot.waitExposed(host)

    combo.showDropdown(focus_index=2)
    assert combo._expanded is True

    decoy = QWidget(host)
    decoy.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    decoy.setGeometry(0, 0, 80, 80)
    decoy.show()
    qtbot.wait(10)
    decoy.hide()
    qtbot.wait(10)

    assert combo._expanded is True
    assert combo._overlay is not None and combo._overlay.isVisible()


# -- scrollable overflow: the popup parks on the row it scrolled to ---------

OVERFLOW_ITEMS = [f"model-{i:02d}" for i in range(40)]


def _overflow_combo(qtbot, current: int = 20, max_visible: int = 5):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = ComboBox(parent=host)
    combo.addItems(OVERFLOW_ITEMS)
    combo.setMaxVisibleItems(max_visible)
    combo.setCurrentIndex(current)
    combo.move(40, 160)
    combo._test_host = host
    host.show()
    qtbot.waitExposed(host)
    return combo


def _row_is_aligned_to_the_field(combo: ComboBox, index: int) -> bool:
    """Exact row alignment: the row's top == the field's inner top.

    No half-row slack: an even visible window must not put the field's centre
    on a row boundary (owner report 2026-10-22 — the selected row looked half a
    row off and needed a 0.5-row nudge).
    """
    from sli_ui_toolkit.ui.widgets.helpers import centered_inner_offset

    row = combo.dropdown_row_widget(index)
    assert row is not None, f"row {index} is not in the visible window"
    row_top = row.mapToGlobal(row.rect().topLeft()).y()
    field_top = combo.mapToGlobal(combo.rect().topLeft()).y()
    inner_top = field_top + centered_inner_offset(combo.rect().height(), combo._item_height())
    return row_top == inner_top


def test_overflow_open_puts_the_current_row_under_the_field(qtbot):
    combo = _overflow_combo(qtbot, current=20)

    combo.showDropdown()

    assert _row_is_aligned_to_the_field(combo, 20)


def test_overflow_open_puts_the_revealed_row_under_the_field(qtbot):
    """Regression: a reveal scrolled to its row but parked the popup on
    ``currentIndex``, leaving the revealed row below the field."""
    combo = _overflow_combo(qtbot, current=20)

    combo.showDropdown(focus_index=35)

    assert combo.currentIndex() == 20  # reveal does not change the value
    assert _row_is_aligned_to_the_field(combo, 35)


def test_a_revealed_row_above_the_current_one_is_centred_too(qtbot):
    combo = _overflow_combo(qtbot, current=35)

    combo.showDropdown(focus_index=3)

    assert _row_is_aligned_to_the_field(combo, 3)

def test_an_even_visible_window_aligns_the_row_exactly(qtbot):
    """12 visible rows: centring the list would split the field between rows."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(800, 900)
    combo = ComboBox(parent=host)
    combo.addItems(OVERFLOW_ITEMS)
    combo.setMaxVisibleItems(12)
    combo.setCurrentIndex(20)
    combo.move(40, 400)
    combo._test_host = host
    host.show()
    qtbot.waitExposed(host)

    combo.showDropdown()

    assert _row_is_aligned_to_the_field(combo, 20)


def test_an_odd_visible_window_aligns_the_row_exactly(  # parity pair
    qtbot,
):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(800, 900)
    combo = ComboBox(parent=host)
    combo.addItems(OVERFLOW_ITEMS)
    combo.setMaxVisibleItems(5)
    combo.setCurrentIndex(20)
    combo.move(40, 400)
    combo._test_host = host
    host.show()
    qtbot.waitExposed(host)

    combo.showDropdown()

    assert _row_is_aligned_to_the_field(combo, 20)

