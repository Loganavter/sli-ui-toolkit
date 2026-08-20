from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.navigation_sections import (
    IconListNavSection,
    ToolbarRowsSection,
)
from sli_ui_toolkit.widgets import IconListWidget


@pytest.fixture
def window(qapp):
    w = QWidget()
    w.setGeometry(0, 0, 400, 200)
    w.show()
    QApplication.setActiveWindow(w)
    yield w
    w.close()
    w.deleteLater()
    QApplication.processEvents()


def _make_list(window: QWidget, count: int = 3) -> IconListWidget:
    widget = IconListWidget(parent=window)
    for i in range(count):
        widget.add_item(f"Item {i}")
    widget.show()
    return widget


def test_down_moves_to_next_row(qapp, window):
    lst = _make_list(window)
    section = IconListNavSection(lst)
    btn0 = lst.row_button(0)
    btn1 = lst.row_button(1)

    assert section.navigate(Qt.Key.Key_Down, btn0) is True
    assert QApplication.focusWidget() is btn1


def test_down_at_last_row_yields(qapp, window):
    lst = _make_list(window, count=2)
    section = IconListNavSection(lst)
    last = lst.row_button(1)
    last.setFocus(Qt.FocusReason.OtherFocusReason)

    assert section.navigate(Qt.Key.Key_Down, last) is False


def test_up_at_first_row_yields(qapp, window):
    lst = _make_list(window)
    section = IconListNavSection(lst)
    first = lst.row_button(0)

    assert section.navigate(Qt.Key.Key_Up, first) is False


def test_focus_first_lands_on_current_row_not_literal_first(qapp, window):
    lst = _make_list(window)
    lst.setCurrentRow(2)
    section = IconListNavSection(lst)

    assert section.focus_first() is True
    assert QApplication.focusWidget() is lst.row_button(2)


def test_focus_first_falls_back_to_row_zero_when_nothing_selected(qapp, window):
    lst = _make_list(window)
    section = IconListNavSection(lst)

    assert section.focus_first() is True
    assert QApplication.focusWidget() is lst.row_button(0)


def test_right_key_hands_off_via_on_exit_right(qapp, window):
    lst = _make_list(window)
    calls = []
    section = IconListNavSection(lst, on_exit_right=lambda: (calls.append(1) or True))
    btn0 = lst.row_button(0)

    assert section.navigate(Qt.Key.Key_Right, btn0) is True
    assert calls == [1]


def test_right_key_without_handler_yields(qapp, window):
    lst = _make_list(window)
    section = IconListNavSection(lst)
    btn0 = lst.row_button(0)

    assert section.navigate(Qt.Key.Key_Right, btn0) is False


def test_toolbar_rows_left_at_row_start_hands_off_via_on_exit_left(qapp, window):
    row = QWidget(window)
    row.setGeometry(0, 0, 200, 30)
    btn = QWidget(row)
    btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    btn.setGeometry(10, 5, 30, 20)
    row.show()
    btn.show()

    calls = []
    section = ToolbarRowsSection(
        rows_provider=lambda: [row],
        on_exit_left=lambda: (calls.append(1) or True),
    )

    assert section.navigate(Qt.Key.Key_Left, btn) is True
    assert calls == [1]


def test_toolbar_rows_left_without_handler_still_consumes(qapp, window):
    row = QWidget(window)
    row.setGeometry(0, 0, 200, 30)
    btn = QWidget(row)
    btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    btn.setGeometry(10, 5, 30, 20)
    row.show()
    btn.show()

    section = ToolbarRowsSection(rows_provider=lambda: [row])

    # No on_exit_left configured -- original behavior: consumed, no crash,
    # no movement (single focusable item in the row).
    assert section.navigate(Qt.Key.Key_Left, btn) is True


def test_toolbar_rows_left_declined_handler_still_consumes(qapp, window):
    row = QWidget(window)
    row.setGeometry(0, 0, 200, 30)
    btn = QWidget(row)
    btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    btn.setGeometry(10, 5, 30, 20)
    row.show()
    btn.show()

    section = ToolbarRowsSection(
        rows_provider=lambda: [row],
        on_exit_left=lambda: False,
    )

    assert section.navigate(Qt.Key.Key_Left, btn) is True
