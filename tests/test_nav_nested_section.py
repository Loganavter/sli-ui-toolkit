"""Nested sub-sections: a grid can occupy one row slot of a row section.

Owner case (BlinkTable ``src/ui/widgets/color/recents_nav.py:26-31``): the
recent-colours picker is a column of toolbar rows and the recent chips are a
2-D grid that belongs *between* two of those rows. Registering the grid as a
second ``NavigationSection`` cannot express that: when the grid declines a
vertical key at its edge, ``NavigationManager`` hands the key to the adjacent
*section* (``_neighbor`` → that section's ``focus_first``/``focus_last``), i.e.
to the whole picker's outer edge instead of the row above/below. The host
worked around it by swapping the dialog's section class — a host-side bypass of
the library's model.

``ToolbarRowsSection.add_sub_section(row_index, section)`` keeps one graph
node: the grid replaces its row in the vertical slot, so its top/bottom edges
continue on the neighbouring rows, while everything inside it — including
Left/Right, which a flat x-sort of a grid's cells would turn into a vertical
step — belongs to the grid.

The second test is the no-sub-section oracle: a ``ToolbarRowsSection`` with no
sub-sections must walk exactly the way it did before (the existing
``test_navigation_graph`` / ``test_nav_auto_section_rows`` /
``test_nav_modal_section`` suites remain the broader oracle).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.managers.navigation_sections import (
    AutoNavigationSection,
    ToolbarRowsSection,
)


class _Cell(QWidget):
    """Focusable leaf with a printable label (plain QWidget: no paint code)."""

    def __init__(self, label: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.label = label
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def _row(host: QWidget, top: int, height: int = 30) -> QWidget:
    row = QWidget(host)
    row.setGeometry(0, top, 500, height)
    return row


def _place(label: str, row: QWidget, x: int, y: int, w: int = 60, h: int = 22) -> _Cell:
    cell = _Cell(label, row)
    cell.setGeometry(x, y, w, h)
    return cell


def _show(host: QWidget, qtbot) -> None:
    host.show()
    qtbot.waitExposed(host)
    for child in host.findChildren(QWidget):
        child.show()
    QApplication.processEvents()


def _press(key) -> None:
    focused = QApplication.focusWidget()
    assert focused is not None, "test setup: nothing has focus"
    QApplication.sendEvent(
        focused,
        QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier),
    )
    QApplication.processEvents()


def _label() -> str:
    focused = QApplication.focusWidget()
    return getattr(focused, "label", type(focused).__name__ if focused else "<none>")


def _picker_with_grid(qtbot):
    """Four toolbar rows, the third slot walked by a 3x3 grid.

    Global centres: row 1 y=15, row 2 y=55, grid rows y=105/145/185,
    row 4 y=225; columns x=40/180/320 for the grid and x=40/180 elsewhere.
    """
    host = QWidget()
    host.resize(500, 400)
    qtbot.addWidget(host)

    row1 = _row(host, 0)
    row2 = _row(host, 40)
    row3 = _row(host, 80, height=120)
    row4 = _row(host, 210)

    cells = {}
    for name, row in (("r1a", row1), ("r2a", row2), ("r4a", row4)):
        cells[name] = _place(name, row, 10, 4)
    for name, row in (("r1b", row1), ("r2b", row2), ("r4b", row4)):
        cells[name] = _place(name, row, 150, 4)
    for grid_row in range(3):
        for grid_col in range(3):
            label = f"g{grid_row}{grid_col}"
            cells[label] = _place(label, row3, 10 + grid_col * 140, 10 + grid_row * 40, h=30)

    _show(host, qtbot)

    section = ToolbarRowsSection(lambda: [row1, row2, row3, row4], tag="picker")
    grid = AutoNavigationSection(row3, tag="chip-grid", yield_at_edges=True)
    section.add_sub_section(2, grid)
    NavigationManager.get_instance().register(host, section)
    QApplication.processEvents()

    cells.update({"row1": row1, "row2": row2, "row3": row3, "row4": row4})
    return {"host": host, "section": section, "grid": grid, **cells}


def _plain_rows(qtbot):
    """The same four rows with no sub-section (the base-behaviour oracle)."""
    host = QWidget()
    host.resize(500, 400)
    qtbot.addWidget(host)

    rows = [_row(host, top) for top in (0, 40, 80, 120)]
    cells = {}
    for index, row in enumerate(rows):
        cells[f"r{index + 1}a"] = _place(f"r{index + 1}a", row, 10, 4)
        cells[f"r{index + 1}b"] = _place(f"r{index + 1}b", row, 150, 4)

    _show(host, qtbot)

    section = ToolbarRowsSection(lambda: rows, tag="plain")
    NavigationManager.get_instance().register(host, section)
    QApplication.processEvents()
    return {"host": host, "section": section, "rows": rows, **cells}


def test_grid_slot_hands_vertical_edges_to_adjacent_rows(qapp, qtbot, navigation_manager_reset):
    """Up/Down enter the grid from row 2, walk it, and leave to rows 2 and 4."""
    built = _picker_with_grid(qtbot)
    built["r2a"].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    _press(Qt.Key.Key_Down)
    assert _label() == "g00", f"Down from row 2 must enter the grid's nearest cell, got {_label()}"

    _press(Qt.Key.Key_Down)
    assert _label() == "g10", (
        f"Down inside the grid must stay in the grid (next grid row), got {_label()}; "
        "a parent x/row walk would have jumped straight to row 4"
    )

    _press(Qt.Key.Key_Down)
    assert _label() == "g20", _label()

    _press(Qt.Key.Key_Down)
    assert _label() == "r4a", f"grid bottom edge must continue on row 4, got {_label()}"

    _press(Qt.Key.Key_Up)
    assert _label() == "g20", f"Up from row 4 must re-enter the grid's bottom row, got {_label()}"

    _press(Qt.Key.Key_Up)
    _press(Qt.Key.Key_Up)
    assert _label() == "g00", _label()

    _press(Qt.Key.Key_Up)
    assert _label() == "r2a", (
        f"grid top edge must continue on row 2, got {_label()}; "
        "the whole-section fallback would have landed on row 1 (focus_first)"
    )

    # Entering from the right half of row 2 keeps the column.
    built["r2b"].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    _press(Qt.Key.Key_Down)
    assert _label() == "g01", f"Down must land on the nearest grid column, got {_label()}"


def test_horizontal_keys_inside_the_grid_never_fall_through(qapp, qtbot, navigation_manager_reset):
    """Left/Right are the grid's: a declined edge is consumed, not x-walked."""
    built = _picker_with_grid(qtbot)
    built["g00"].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    _press(Qt.Key.Key_Right)
    assert _label() == "g01", _label()
    _press(Qt.Key.Key_Right)
    assert _label() == "g02", _label()

    _press(Qt.Key.Key_Right)
    assert _label() == "g02", (
        f"Right at the grid's right edge must be consumed, got {_label()}; "
        "the parent's flat x-walk would have stepped to g12 (a different grid row)"
    )

    _press(Qt.Key.Key_Down)
    assert _label() == "g12", (
        f"Down must keep the column inside the grid, got {_label()}"
    )

    _press(Qt.Key.Key_Left)
    assert _label() == "g11", _label()
    _press(Qt.Key.Key_Left)
    assert _label() == "g10", _label()
    _press(Qt.Key.Key_Left)
    assert _label() == "g10", f"Left at the grid's left edge must stay inside, got {_label()}"


def test_section_without_sub_sections_keeps_the_base_walk(qapp, qtbot, navigation_manager_reset):
    """No sub-sections: rows, edges, focus_first/last/nearest are unchanged."""
    built = _plain_rows(qtbot)
    section = built["section"]

    walk = section._walk()
    assert [row for row, sub in walk] == built["rows"]
    assert all(sub is None for _row, sub in walk)
    assert section.extra_keys == frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})

    built["r1a"].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    for expected in ("r2a", "r3a", "r4a", "r4a"):
        _press(Qt.Key.Key_Down)
        assert _label() == expected, f"Down: expected {expected}, got {_label()}"
    for expected in ("r3a", "r2a", "r1a", "r1a"):
        _press(Qt.Key.Key_Up)
        assert _label() == expected, f"Up: expected {expected}, got {_label()}"

    _press(Qt.Key.Key_Right)
    assert _label() == "r1b", _label()
    _press(Qt.Key.Key_Right)
    assert _label() == "r1b", f"row right edge must be consumed, got {_label()}"
    _press(Qt.Key.Key_Left)
    assert _label() == "r1a", _label()

    assert section.focus_first(reason=Qt.FocusReason.OtherFocusReason) is True
    assert _label() == "r1a", _label()
    assert section.focus_last(reason=Qt.FocusReason.OtherFocusReason) is True
    assert _label() == "r4a", _label()

    row3b = built["r3b"]
    assert section.focus_nearest(
        row3b.mapToGlobal(row3b.rect().center()), reason=Qt.FocusReason.OtherFocusReason
    ) is True
    assert _label() == "r3b", _label()


def test_negative_row_index_is_rejected(qapp, qtbot):
    section = ToolbarRowsSection(lambda: [], tag="empty")
    empty = QWidget()
    qtbot.addWidget(empty)
    try:
        section.add_sub_section(-1, AutoNavigationSection(empty, yield_at_edges=True))
    except ValueError:
        pass
    else:  # pragma: no cover - the raise is the contract
        raise AssertionError("negative row index must be rejected")
