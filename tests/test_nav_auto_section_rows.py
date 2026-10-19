"""``AutoNavigationSection`` must walk VISUAL ROWS — the dialog case.

Owner report 2026-10-19 (colour picker): a dialog registered an
``AutoNavigationSection`` and an arrow walk did **nothing at all** — the
section claimed only its own descendants and the registered owner was an
inner container, so focus sitting on the dialog window meant no section owned
the key and ``NavigationManager`` dropped it (12× Down, focus unmoved). The
one row that could be reached walked by x only, and ``focus_nearest()`` always
returned ``False`` because the inherited implementation read row *containers*
the auto section never had.

These tests build a dialog-shaped host whose container carries a full-width
row, a row with two side-by-side controls and a right-aligned row, register it
through ``AutoNavigationSection`` and walk it with real widgets (offscreen).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.managers.navigation_sections import AutoNavigationSection


class _Focusable(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def _dialog_with_rows(qtbot):
    """Dialog → container(owner) → three rows with deterministic geometry.

    centre points: Row1-full x=60 y=22 · Row2-left x=40 y=62 ·
    Row2-right x=180 y=62 · Row3-tail x=330 y=102.
    """
    dialog = QWidget()
    dialog.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    dialog.resize(400, 300)
    qtbot.addWidget(dialog)

    container = QWidget(dialog)
    container.setGeometry(0, 0, 400, 300)

    row1 = _Focusable("Row1-full", container)
    row1.setGeometry(10, 10, 100, 24)
    row2_left = _Focusable("Row2-left", container)
    row2_left.setGeometry(10, 50, 60, 24)
    row2_right = _Focusable("Row2-right", container)
    row2_right.setGeometry(150, 50, 60, 24)
    row3 = _Focusable("Row3-right-aligned", container)
    row3.setGeometry(300, 90, 60, 24)

    dialog.show()
    qtbot.waitExposed(dialog)
    for w in container.findChildren(QWidget):
        w.show()
    QApplication.processEvents()

    section = AutoNavigationSection(container, tag="auto-dialog")
    NavigationManager.get_instance().register(container, section)
    return {
        "dialog": dialog,
        "container": container,
        "section": section,
        "row1": row1,
        "row2_left": row2_left,
        "row2_right": row2_right,
        "row3": row3,
    }


def _press(key) -> None:
    focused = QApplication.focusWidget()
    assert focused is not None
    QApplication.sendEvent(
        focused,
        QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier),
    )
    QApplication.processEvents()


def _label() -> str:
    focused = QApplication.focusWidget()
    return getattr(focused, "label", type(focused).__name__ if focused else "<none>")


def test_down_from_dialog_bootstraps_and_walks_rows(qapp, qtbot):
    """Down on the dialog itself enters the rows, then steps row by row."""
    built = _dialog_with_rows(qtbot)
    built["dialog"].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is built["dialog"], (
        "test setup: the dialog must hold focus (the live report's state)"
    )

    _press(Qt.Key.Key_Down)
    assert _label() == "Row1-full", _label()

    # Down keeps the COLUMN: full row's centre (60) is nearest Row2-left (40).
    _press(Qt.Key.Key_Down)
    assert _label() == "Row2-left", _label()

    _press(Qt.Key.Key_Down)
    assert _label() == "Row3-right-aligned", _label()

    # At the bottom edge Down must NOT step sideways (Row3 has no sibling).
    _press(Qt.Key.Key_Down)
    assert _label() == "Row3-right-aligned", _label()


def test_up_from_right_half_goes_to_row_above_not_sideways(qapp, qtbot):
    built = _dialog_with_rows(qtbot)
    built["row2_right"].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    _press(Qt.Key.Key_Up)
    assert _label() == "Row1-full", _label()
    assert _label() != "Row2-left", "Up moved sideways inside the row"

    # At the top edge Up is consumed (nothing above this section).
    _press(Qt.Key.Key_Up)
    assert _label() == "Row1-full", _label()


def test_right_moves_inside_the_row_only(qapp, qtbot):
    built = _dialog_with_rows(qtbot)
    built["row2_left"].setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    _press(Qt.Key.Key_Right)
    assert _label() == "Row2-right", _label()

    # At the row's right edge Right stays put (no wrap into another row).
    _press(Qt.Key.Key_Right)
    assert _label() == "Row2-right", _label()

    _press(Qt.Key.Key_Left)
    assert _label() == "Row2-left", _label()


def test_focus_nearest_moves_and_reports_true(qapp, qtbot):
    built = _dialog_with_rows(qtbot)
    section = built["section"]

    tail_pos = built["row3"].mapToGlobal(QPoint(5, 5))
    assert section.focus_nearest(tail_pos, reason=Qt.FocusReason.OtherFocusReason) is True
    assert QApplication.focusWidget() is built["row3"]

    # A click nearer the right half of row 2 lands there, not on the row's left.
    right_pos = built["row2_right"].mapToGlobal(QPoint(5, 5))
    assert section.focus_nearest(right_pos, reason=Qt.FocusReason.OtherFocusReason) is True
    assert QApplication.focusWidget() is built["row2_right"]
    assert QApplication.focusWidget() is not built["row2_left"]


def test_empty_and_single_row_sections_keep_their_behaviour(qapp, qtbot):
    empty = QWidget()
    empty.setGeometry(0, 0, 100, 100)
    qtbot.addWidget(empty)
    empty_section = AutoNavigationSection(empty)
    assert empty_section.focus_first(reason=Qt.FocusReason.OtherFocusReason) is False
    assert empty_section.focus_nearest(QPoint(0, 0), reason=Qt.FocusReason.OtherFocusReason) is False

    one_row = _dialog_with_rows(qtbot)
    only = one_row["row3"]
    # Hide the other two rows so a single row remains.
    for name in ("row1", "row2_left", "row2_right"):
        one_row[name].hide()
    QApplication.processEvents()
    only.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert _label() == "Row3-right-aligned"
    _press(Qt.Key.Key_Down)
    assert _label() == "Row3-right-aligned", "single row: Down must be consumed, not move"
