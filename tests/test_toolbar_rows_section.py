from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection


def _make_focusable(parent: QWidget, x: int, y: int, w: int = 30, h: int = 20) -> QWidget:
    widget = QWidget(parent)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.setGeometry(x, y, w, h)
    widget.show()
    return widget


def _make_row(parent: QWidget, y: int) -> QWidget:
    row = QWidget(parent)
    row.setGeometry(0, y, 400, 30)
    row.show()
    return row


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


def test_focus_nearest_picks_row_closest_to_click_y(window):
    """A click below the first row must land in the row nearest its y --
    not always the topmost row like focus_first(ref_x) does (that method
    models a fixed cross-section entry direction, not an arbitrary click).
    """
    row0 = _make_row(window, y=0)
    row1 = _make_row(window, y=100)
    btn_row0 = _make_focusable(row0, x=10, y=5)
    btn_row1 = _make_focusable(row1, x=10, y=5)

    section = ToolbarRowsSection(rows_provider=lambda: [row0, row1])

    # Click point far closer to row1 (y~=110) than row0 (y~=10).
    click_pos = btn_row1.mapToGlobal(QPoint(5, 5))
    assert section.focus_nearest(click_pos, reason=Qt.FocusReason.OtherFocusReason) is True
    assert QApplication.focusWidget() is btn_row1
    assert QApplication.focusWidget() is not btn_row0


def test_focus_nearest_picks_nearest_x_within_chosen_row(window):
    row0 = _make_row(window, y=0)
    left_btn = _make_focusable(row0, x=10, y=5)
    right_btn = _make_focusable(row0, x=300, y=5)

    section = ToolbarRowsSection(rows_provider=lambda: [row0])

    click_pos = right_btn.mapToGlobal(QPoint(5, 5))
    assert section.focus_nearest(click_pos, reason=Qt.FocusReason.OtherFocusReason) is True
    assert QApplication.focusWidget() is right_btn
    assert QApplication.focusWidget() is not left_btn


def test_focus_nearest_empty_rows_returns_false(window):
    section = ToolbarRowsSection(rows_provider=lambda: [])
    assert section.focus_nearest(QPoint(0, 0), reason=Qt.FocusReason.OtherFocusReason) is False


def test_focus_first_still_always_picks_top_row(window):
    """Regression: focus_nearest must not change focus_first's existing
    cross-section-entry semantics (always the fixed row, ref_x only picks
    left/right within it).
    """
    row0 = _make_row(window, y=0)
    row1 = _make_row(window, y=100)
    btn_row0 = _make_focusable(row0, x=10, y=5)
    btn_row1 = _make_focusable(row1, x=10, y=5)

    section = ToolbarRowsSection(rows_provider=lambda: [row0, row1])

    ref_x = btn_row1.mapToGlobal(QPoint(5, 5)).x()
    assert section.focus_first(ref_x, reason=Qt.FocusReason.OtherFocusReason) is True
    assert QApplication.focusWidget() is btn_row0
    assert QApplication.focusWidget() is not btn_row1


def _make_line_edit(row: QWidget, x: int = 60) -> "object":
    from PySide6.QtWidgets import QLineEdit

    edit = QLineEdit(row)
    edit.setGeometry(x, 5, 120, 20)
    edit.setText("abc")
    edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    edit.show()
    return edit


def test_left_from_text_field_at_caret_start_exits_row(window):
    """A line edit must not TRAP Left: at the caret start the row is exited.

    Regression (gallery filter "consumed (no movement)"): the field accepted
    Left for caret movement and the section returned consumed, so focus could
    never leave the field leftward.
    """
    row = _make_row(window, y=0)
    left_btn = _make_focusable(row, x=10, y=5)
    edit = _make_line_edit(row)

    section = ToolbarRowsSection(rows_provider=lambda: [row])

    edit.setFocus(Qt.FocusReason.OtherFocusReason)
    edit.setCursorPosition(0)
    assert section.navigate(Qt.Key.Key_Left, edit) is True
    assert QApplication.focusWidget() is left_btn


def test_left_from_text_field_mid_caret_stays_and_moves_caret(window):
    """With the caret inside the text, Left is caret movement — focus stays."""
    row = _make_row(window, y=0)
    _make_focusable(row, x=10, y=5)
    edit = _make_line_edit(row)

    section = ToolbarRowsSection(rows_provider=lambda: [row])

    edit.setFocus(Qt.FocusReason.OtherFocusReason)
    edit.setCursorPosition(2)
    assert section.navigate(Qt.Key.Key_Left, edit) is True
    assert QApplication.focusWidget() is edit
