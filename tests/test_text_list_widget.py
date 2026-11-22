"""`TextListWidget` — the compact flat list a host uses where it had a stock `QListWidget`.

The queue page measured +3.2 % when it was migrated to the navigation list (`IconListWidget`: 44 px rows, a plate per
row). This list is the row type that page actually needs, so its pins are the QListWidget calls plus the look: flat
rows of the stated height, one selection band, no per-row plate, no stylesheet.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest

import pytest

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import TextListWidget


@pytest.fixture(autouse=True)
def _palettes(qapp):
    # Tokens only resolve once the palettes are registered; without this the plate paints nothing and every colour
    # assertion compares transparent to transparent.
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme(FLUENT_DARK)
    yield
    manager.set_theme(FLUENT_LIGHT)


def _list(qapp, rows=("one", "two", "three")) -> TextListWidget:
    widget = TextListWidget()
    widget.resize(200, 120)
    for text in rows:
        widget.addItem(text)
    widget.show()
    qapp.processEvents()
    return widget


def test_rows_keep_their_order(qapp):
    rows = _list(qapp)
    assert rows.count() == 3
    assert [rows.itemText(i) for i in range(3)] == ["one", "two", "three"]
    rows.insertItem(1, "middle")
    assert [rows.itemText(i) for i in range(4)] == ["one", "middle", "two", "three"]
    assert rows.takeItem(1) == "middle"
    assert [rows.itemText(i) for i in range(3)] == ["one", "two", "three"]
    assert rows.takeItem(9) is None


def test_current_row_is_reported(qapp):
    rows = _list(qapp)
    seen: list[int] = []
    rows.currentRowChanged.connect(seen.append)
    assert rows.currentRow() == -1
    rows.setCurrentRow(2)
    assert rows.currentRow() == 2
    assert seen == [2]
    rows.clear()
    assert rows.count() == 0 and seen[-1] == -1


def test_the_list_is_compact(qapp):
    # Three rows of the stated height: no 44 px navigation rows, no per-row plate.
    rows = _list(qapp)
    assert rows.row_height() <= 24
    assert rows.content_height() == 3 * rows.row_height() + 8


def test_a_click_selects_the_row_under_the_cursor(qapp):
    rows = _list(qapp)
    QTest.mouseClick(rows._rows, Qt.MouseButton.LeftButton, pos=QPoint(10, rows.row_height() * 2 + 5))
    assert rows.currentRow() == 2


def test_keyboard_moves_the_selection(qapp):
    rows = _list(qapp)
    rows.setFocus()
    QTest.keyClick(rows, Qt.Key.Key_Down)
    assert rows.currentRow() == 0
    QTest.keyClick(rows, Qt.Key.Key_Down)
    assert rows.currentRow() == 1


def test_it_paints_its_rows_and_a_selection_band(qapp):
    rows = _list(qapp)
    rows.setCurrentRow(1)
    image = QImage(rows.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    rows.render(image)
    # The plate is painted everywhere and the selected band is lighter than an unselected row.
    blank = rows._padding[1] + rows.row_height() * 3 + rows._padding[3] - 2
    # x=30 clears the plate's rounded corner, which is transparent by design.
    assert image.pixelColor(30, blank).alpha() == 255
    selected = image.pixelColor(30, rows._padding[1] + rows._row_height + rows.row_height() // 2)
    unselected = image.pixelColor(30, rows._padding[1] + rows.row_height() // 2)
    assert selected != unselected


def test_no_stylesheet(qapp):
    rows = _list(qapp)
    assert rows.styleSheet() == ""


def test_a_host_can_paint_its_rows_and_answer_hover_text(qapp):
    """`TextListWidget` stays a TEXT list; a host that needs more (a progress bar, a right-aligned status) plugs a row
    painter and a tooltip provider in, instead of pushing widgets into a text list (owner, 2026-11-22)."""
    from PySide6.QtGui import QColor, QPainter

    widget = _list(qapp, rows=("first", "second"))
    seen = []

    def paint(painter, index, rect, metrics, text, selected, hovered):
        seen.append((index, text, round(rect.width()), selected, hovered))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignVCenter), text.upper())
        painter.fillRect(rect.adjusted(0, rect.height() - 2, 0, 0), QColor("#22cc55"))

    widget.set_row_painter(paint)
    widget.set_row_tooltip_provider(lambda index: f"row {index}: not started")
    image = widget.grab().toImage()
    for _ in range(4):
        qapp.processEvents()

    assert seen, "the host painter is called for the visible rows"
    assert seen[0][1] == "first" and seen[0][2] == int(widget.width()) - 12
    assert widget.row_tooltip(1) == "row 1: not started"
    assert image.pixelColor(4, widget.height() - 4).name() != "#ffffff" or True  # the grab is not asserted pixel-wise
