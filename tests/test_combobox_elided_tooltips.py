"""ComboBox: a truncated label must reveal its full text as a tooltip.

Owner request 2026-10-22 ("навел — появился в тултипе полное название, на
случай если где-то обрезается"): the dropdown elides long row labels and the
closed field elides a long current value, and neither used to say what the
whole text was.

Rule pinned here: the tooltip is present **only** while the painted text is
actually elided (the same ``QFontMetrics.elidedText`` comparison the painters
use), it follows the rebound value of a pooled row, it is re-evaluated on
resize / selection change, and a tooltip the host set itself is never
overwritten.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFontMetrics, QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.widgets import ComboBox

LONG = "Сбалансированное (0.75x) с очень длинным пояснением для проверки"
SHORT = "Быстро"
NARROW = 120
WIDE = 900


def _text_width(widget, text: str) -> int:
    return QFontMetrics(paint_font(widget)).horizontalAdvance(text)


def _field_text_width(combo: ComboBox) -> int:
    return combo.width() - 2 * scaled_px(combo.TEXT_HORIZONTAL_PADDING)


def _make_combo(qtbot, items, width: int):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1000, 600)
    combo = ComboBox(parent=host)
    combo.addItems(items)
    combo.setCurrentIndex(0)
    combo.move(20, 20)
    combo.resize(width, ComboBox.BASE_HEIGHT)
    host.show()
    qtbot.waitExposed(host)
    return host, combo


def _drop(combo: ComboBox, qtbot, index: int = 0) -> QWidget:
    combo.showDropdown()
    qtbot.waitUntil(lambda: combo.dropdown_row_widget(index) is not None)
    row = combo.dropdown_row_widget(index)
    assert row is not None
    return row


# -------- dropdown rows --------


def test_elided_row_carries_the_full_item_text(qtbot):
    items = [LONG, SHORT]
    _host, combo = _make_combo(qtbot, items, NARROW)
    # Precondition: the row really is too narrow for the long label.
    assert _text_width(combo, LONG) > combo.width()

    row = _drop(combo, qtbot, 0)
    assert row.toolTip() == LONG


def test_row_without_elision_has_no_tooltip(qtbot):
    _host, combo = _make_combo(qtbot, [SHORT, "Ещё"], WIDE)
    assert _text_width(combo, SHORT) + 40 < combo.width()

    row = _drop(combo, qtbot, 0)
    assert row.toolTip() == ""


def test_row_tooltip_of_a_short_item_is_cleared_on_rebind(qtbot):
    """A pooled row that showed a long item must drop its tooltip when the
    same slot is rebound to a short one (scroll) — a stale tooltip on a fully
    visible row is the failure this pins."""
    items = [LONG, SHORT] * 12
    _host, combo = _make_combo(qtbot, items, NARROW)
    combo.setMaxVisibleItems(4)

    long_row = _drop(combo, qtbot, 0)
    assert long_row.toolTip() == LONG

    combo._scroll_offset = 1  # short item lands in the same first slot
    combo._overlay._rebind_slots()
    qtbot.waitUntil(lambda: combo.dropdown_row_widget(1) is not None)

    short_row = combo.dropdown_row_widget(1)
    assert short_row is not None
    assert short_row.toolTip() == ""
    assert long_row.toolTip() == ""


# -------- closed field --------


def test_closed_field_reveals_the_elided_current_value(qtbot):
    _host, combo = _make_combo(qtbot, [LONG, SHORT], NARROW)
    assert _text_width(combo, LONG) > _field_text_width(combo)

    assert combo.currentText() == LONG
    assert combo.toolTip() == LONG


def test_closed_field_without_elision_has_no_tooltip(qtbot):
    _host, combo = _make_combo(qtbot, [SHORT], WIDE)
    assert _text_width(combo, SHORT) < _field_text_width(combo)

    assert combo.toolTip() == ""


def test_field_tooltip_follows_the_current_value(qtbot):
    _host, combo = _make_combo(qtbot, [LONG, SHORT], NARROW)
    assert combo.toolTip() == LONG

    combo.setCurrentIndex(1)
    assert combo.toolTip() == ""

    combo.setCurrentIndex(0)
    assert combo.toolTip() == LONG


def test_field_tooltip_follows_a_width_change(qtbot):
    _host, combo = _make_combo(qtbot, [LONG], NARROW)
    assert combo.toolTip() == LONG

    combo.resize(WIDE, ComboBox.BASE_HEIGHT)
    assert _text_width(combo, LONG) < _field_text_width(combo)
    assert combo.toolTip() == ""

    combo.resize(NARROW, ComboBox.BASE_HEIGHT)
    assert combo.toolTip() == LONG


def test_empty_field_has_no_tooltip(qtbot):
    _host, combo = _make_combo(qtbot, [], NARROW)
    assert combo.currentText() == ""
    assert combo.toolTip() == ""


def test_open_field_with_search_reveals_the_painted_line(qtbot):
    """While the field paints ``"<query> -> <value>"`` that whole line is what
    gets elided, so it is what the tooltip must reveal — and closing the list
    returns to the plain value."""
    long_latin = "Balanced (0.75x) with a very long explanation line"
    _host, combo = _make_combo(qtbot, [long_latin, "Fast"], NARROW)
    combo.showDropdown()
    # A real key event, not a private search setter: this is the path that
    # puts the query into the painted line.
    QApplication.sendEvent(
        combo,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier, "b"),
    )

    assert combo.searchText() == "b"
    assert combo.currentText() == long_latin
    assert combo.toolTip() == f"b -> {long_latin}"

    combo.hideDropdown()
    assert combo.toolTip() == long_latin


def test_explicit_host_tooltip_wins(qtbot):
    _host, combo = _make_combo(qtbot, [LONG], NARROW)
    combo.setToolTip("explicit")

    # Both a value change and a resize must leave the host's own tooltip be.
    combo.resize(WIDE, ComboBox.BASE_HEIGHT)
    combo.resize(NARROW, ComboBox.BASE_HEIGHT)
    combo.setCurrentIndex(0)
    assert combo.toolTip() == "explicit"
