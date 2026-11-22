"""`TextListWidget` selection: multi-select, rubber band, and the context-menu right press.

The render queue is the host that needs this (owner, 2026-11-22: three buttons removed, right-click menu instead,
selection by dragging like a file manager). Every assertion here is a user gesture, not an internal field: a press
selects, Ctrl adds, Shift extends, a drag draws a band over the rows it touches, and a right press inside the selection
must leave it alone so the menu can act on everything the user picked.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

import pytest

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import TextListWidget

ROW = 20
PAD_TOP = 4


@pytest.fixture(autouse=True)
def _palettes(qapp):
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme(FLUENT_DARK)
    yield
    manager.set_theme(FLUENT_LIGHT)


def _list(qapp, rows: int = 20) -> TextListWidget:
    widget = TextListWidget(row_height=ROW)
    widget.resize(260, 200)
    for index in range(rows):
        widget.addItem(f"file-{index}.mkv")
    widget.show()
    qapp.processEvents()
    widget.setSelectionMode("extended")
    return widget


def _press(widget: TextListWidget, row: int, *, button=Qt.MouseButton.LeftButton,
           modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    target = widget._rows
    point = QPointF(10, PAD_TOP + row * ROW + 5)
    target.mousePressEvent(
        QMouseEvent(QEvent.Type.MouseButtonPress, point, target.mapToGlobal(point), button, button, modifiers)
    )


def _drag(widget: TextListWidget, start_row: int, end_row: int,
          modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    target = widget._rows
    point = QPointF(10, PAD_TOP + end_row * ROW + ROW - 2)
    target.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.MouseMove, point, target.mapToGlobal(point),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, modifiers,
        )
    )


def test_single_selection_is_still_the_default_and_still_works(qapp):
    from sli_ui_toolkit.widgets import TextListWidget as Control

    widget = Control()
    widget.resize(200, 120)
    for text in ("one", "two", "three"):
        widget.addItem(text)
    widget.show()
    qapp.processEvents()

    assert widget.selectionMode() == "single"
    _press(widget, 1)
    assert widget.selectedRows() == [1]
    assert widget.currentRow() == 1


def test_click_replaces_ctrl_toggles_shift_extends(qapp):
    widget = _list(qapp)
    _press(widget, 2)
    assert widget.selectedRows() == [2]

    _press(widget, 5, modifiers=Qt.KeyboardModifier.ControlModifier)
    assert widget.selectedRows() == [2, 5]

    _press(widget, 5, modifiers=Qt.KeyboardModifier.ControlModifier)
    assert widget.selectedRows() == [2], "a second Ctrl+click must toggle the row off"

    # Shift extends from the last click (row 5), not from the oldest row: the anchor moves with every press, which is
    # what a file manager does after a Ctrl+click.
    _press(widget, 8, modifiers=Qt.KeyboardModifier.ShiftModifier)
    assert widget.selectedRows() == [5, 6, 7, 8]


def test_band_drag_selects_the_rows_it_touches(qapp):
    widget = _list(qapp)
    _press(widget, 3)
    _drag(widget, 3, 6)
    assert widget.selectedRows() == [3, 4, 5, 6]
    assert widget._band is not None, "the rectangle is painted while the drag is live"

    widget._on_rows_release(None)
    assert widget._band is None


def test_a_plain_drag_replaces_and_a_ctrl_drag_adds(qapp):
    widget = _list(qapp)
    _press(widget, 10)
    _drag(widget, 10, 12)
    assert widget.selectedRows() == [10, 11, 12]

    _press(widget, 0)
    _drag(widget, 0, 1)
    assert widget.selectedRows() == [0, 1], "a plain drag starts a fresh selection"

    _press(widget, 5, modifiers=Qt.KeyboardModifier.ControlModifier)
    _drag(widget, 5, 6, modifiers=Qt.KeyboardModifier.ControlModifier)
    assert widget.selectedRows() == [0, 1, 5, 6]


def test_right_press_keeps_a_selection_it_lands_in_and_moves_one_it_does_not(qapp):
    widget = _list(qapp)
    _press(widget, 10)
    _drag(widget, 10, 12)
    widget._on_rows_release(None)

    _press(widget, 11, button=Qt.MouseButton.RightButton)
    assert widget.selectedRows() == [10, 11, 12], "the menu must act on what the user selected"

    _press(widget, 18, button=Qt.MouseButton.RightButton)
    assert widget.selectedRows() == [18]


def test_taking_a_row_keeps_the_selection_pointing_at_the_same_items(qapp):
    widget = _list(qapp, rows=6)
    widget.setSelectedRows([1, 4])
    widget.takeItem(0)
    assert widget.selectedRows() == [0, 3], "rows shift with the model"

    widget.insertItem(0, "new")
    assert widget.selectedRows() == [1, 4]


def test_switching_back_to_single_collapses_a_multi_selection(qapp):
    widget = _list(qapp)
    widget.setSelectedRows([2, 5, 7])
    widget.setSelectionMode("single")
    assert len(widget.selectedRows()) == 1


def test_ctrl_a_selects_all_only_in_a_multi_selection_list(qapp):
    from PySide6.QtGui import QKeyEvent

    widget = _list(qapp, rows=5)
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    widget.keyPressEvent(event)
    assert widget.selectedRows() == [0, 1, 2, 3, 4]

    widget.setSelectionMode("single")
    widget.clearSelection()
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier))
    assert widget.selectedRows() == [], "single mode keeps one row; Ctrl+A is not a selection there"
