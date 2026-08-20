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
    assert section.focus_nearest(click_pos) is True
    assert QApplication.focusWidget() is btn_row1
    assert QApplication.focusWidget() is not btn_row0


def test_focus_nearest_picks_nearest_x_within_chosen_row(window):
    row0 = _make_row(window, y=0)
    left_btn = _make_focusable(row0, x=10, y=5)
    right_btn = _make_focusable(row0, x=300, y=5)

    section = ToolbarRowsSection(rows_provider=lambda: [row0])

    click_pos = right_btn.mapToGlobal(QPoint(5, 5))
    assert section.focus_nearest(click_pos) is True
    assert QApplication.focusWidget() is right_btn
    assert QApplication.focusWidget() is not left_btn


def test_focus_nearest_empty_rows_returns_false(window):
    section = ToolbarRowsSection(rows_provider=lambda: [])
    assert section.focus_nearest(QPoint(0, 0)) is False


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
    assert section.focus_first(ref_x) is True
    assert QApplication.focusWidget() is btn_row0
    assert QApplication.focusWidget() is not btn_row1
