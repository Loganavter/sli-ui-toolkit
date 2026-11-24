"""The ComboBox list selects on MOUSE RELEASE, with the pointer's own motion.

Standard list behaviour, and the only shape Wayland allows: ``QCursor.setPos``
is a no-op there, so a gesture that needs the pointer to be moved by code (or
the popup translated under a stationary pointer) cannot exist. A press on the
field opens the list, the pointer's own travel over the rows highlights the row
under it, and the RELEASE commits exactly that row and closes.

Driven through the widget's real handlers, because the field holds the implicit
mouse grab for the whole gesture: after a press on the field, Qt delivers every
move and the release to the FIELD, not to the rows underneath it. The row under
the pointer is derived from real row geometry, so a highlight/commit never
depends on a synthetic ``QApplication.widgetAt`` reconciliation.

Owner request 2026-11-24.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.widgets import ComboBox

BUTTON = Qt.MouseButton.LeftButton
NO_BUTTON = Qt.MouseButton.NoButton


def _settle(app: QApplication, rounds: int = 8) -> None:
    for _ in range(rounds):
        app.processEvents()


def _mouse(
    kind: QMouseEvent.Type,
    target: QWidget,
    global_pos: QPoint,
    buttons: Qt.MouseButton,
) -> QMouseEvent:
    return QMouseEvent(
        kind,
        QPointF(target.mapFromGlobal(global_pos)),
        QPointF(global_pos),
        BUTTON,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _press(target: QWidget, global_pos: QPoint) -> None:
    QApplication.sendEvent(target, _mouse(QMouseEvent.Type.MouseButtonPress, target, global_pos, BUTTON))


def _move(target: QWidget, global_pos: QPoint) -> None:
    QApplication.sendEvent(target, _mouse(QMouseEvent.Type.MouseMove, target, global_pos, BUTTON))


def _release(target: QWidget, global_pos: QPoint) -> None:
    QApplication.sendEvent(
        target, _mouse(QMouseEvent.Type.MouseButtonRelease, target, global_pos, NO_BUTTON)
    )


def _wheel(widget: QWidget, delta: int = -120) -> QWheelEvent:
    app = QApplication.instance()
    local = widget.rect().center()
    event = QWheelEvent(
        QPointF(local),
        QPointF(widget.mapToGlobal(local)),
        QPoint(0, 0),
        QPoint(0, delta),
        NO_BUTTON,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    app.sendEvent(widget, event)
    _settle(app)
    return event


def _fixture(qtbot, items=("A", "B", "C", "D", "E"), max_visible: int = 5):
    app = QApplication.instance()
    UiScale.get_instance().set_factor(1.0)
    _settle(app)
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(420, 420)
    combo = ComboBox(parent=host)
    combo.setGeometry(40, 160, 200, combo.BASE_HEIGHT)
    combo.addItems(list(items))
    combo.setMaxVisibleItems(max_visible)
    combo.setCurrentIndex(0)
    host.show()
    qtbot.waitExposed(host)
    _settle(app)
    return app, host, combo


def _field_center(combo: ComboBox) -> QPoint:
    return combo.mapToGlobal(combo.rect().center())


def _row_center(combo: ComboBox, index: int) -> QPoint:
    row = combo.dropdown_row_widget(index)
    assert row is not None, f"row {index} is not in the visible window"
    return row.mapToGlobal(row.rect().center())


# -- (a) the press opens, the click on the field keeps it open -------------


def test_a_press_on_the_field_opens_and_the_click_does_not_close_it(qtbot):
    """Press opens (that is what lets the held button travel over the rows)."""
    app, host, combo = _fixture(qtbot)
    assert not combo._expanded
    clicks: list[bool] = []
    combo.clicked.connect(lambda: clicks.append(True))

    _press(combo, _field_center(combo))
    _settle(app)
    assert combo._expanded, "the press on the field must open the list"
    assert combo._overlay is not None and combo._overlay.isVisible()
    assert combo.currentIndex() == 0, "opening the list is not a commit"

    _release(combo, _field_center(combo))
    _settle(app)
    assert combo._expanded, (
        "releasing back on the field is the opening click, not a row pick: the "
        "popup parks the anchored row over the field, and committing it would "
        "close the list the press just opened"
    )
    assert combo.currentIndex() == 0
    assert clicks == [True], (
        "the click on the field must still reach the host as a click; it is the "
        f"list toggle that must not run twice, got {clicks}"
    )

    # A second click on the field is the toggle: press closes, release keeps it
    # closed (the click Button would emit for that press/release pair is the
    # toggle the press already performed).
    _press(combo, _field_center(combo))
    _release(combo, _field_center(combo))
    _settle(app)
    assert not combo._expanded, "a press on an open list closes it"


# -- (b)(c)(d) press on a row does not commit; move highlights; release picks --


def test_press_over_a_row_does_not_commit_and_a_release_does(qtbot):
    app, host, combo = _fixture(qtbot)
    _press(combo, _field_center(combo))
    _release(combo, _field_center(combo))
    _settle(app)
    assert combo._expanded

    # (b) press over a row: nothing is committed on the press.
    row2 = combo.dropdown_row_widget(2)
    assert row2 is not None
    _press(row2, _row_center(combo, 2))
    _settle(app)
    assert combo.currentIndex() == 0, "a press over a row must not commit it"
    assert combo._expanded, "a press over a row must not close the list either"

    # (c) the pointer's own move highlights the row it lands on.
    target = _row_center(combo, 3)
    _move(row2, target)
    _settle(app)
    assert combo._focus_row_index == 3, (
        "the row under the held pointer must be the highlighted commit target"
    )
    row3 = combo.dropdown_row_widget(3)
    assert row3 is not None and row3._is_focus_row, "the targeted row must paint as a focus row"
    assert not row2._is_focus_row, "the row the press started on must not stay highlighted"
    assert combo.currentIndex() == 0, "moving is highlight only — nothing is committed"

    # (d) release over it commits exactly that row and closes.
    committed: list[int] = []
    combo.currentIndexChanged.connect(committed.append)
    _release(row2, target)
    _settle(app)

    assert committed == [3], f"the release must commit exactly once, got {committed}"
    assert combo.currentIndex() == 3
    assert not combo._expanded, "a committed release closes the list"


# -- (e) a release that lands on no row commits nothing --------------------


def test_a_release_outside_every_row_commits_nothing(qtbot):
    app, host, combo = _fixture(qtbot)

    _press(combo, _field_center(combo))
    _settle(app)
    assert combo._expanded
    _move(combo, _row_center(combo, 2))
    _settle(app)
    assert combo._focus_row_index == 2

    outside = host.mapToGlobal(QPoint(4, 4))
    _release(combo, outside)
    _settle(app)

    assert combo.currentIndex() == 0, "a release that lands on no row must commit nothing"
    assert combo._expanded, "nothing was picked, so the list stays open for a second try"
    assert combo._pointer_select_armed is False, "the gesture must be disarmed by its release"


# -- the popup stays parked: only the pointer moves ------------------------


def test_the_card_stays_parked_while_the_pointer_travels(qtbot):
    """The old gesture shoved the popup around under a stationary pointer."""
    app, host, combo = _fixture(qtbot)
    _press(combo, _field_center(combo))
    _settle(app)
    assert combo._overlay is not None
    parked = combo._overlay.pos()

    for index in (1, 2, 3):
        _move(combo, _row_center(combo, index))
        _settle(app)
        assert combo._overlay.pos() == parked, (
            "the card must not move during a selection: Wayland gives no way to "
            "hold the pointer still, so the pointer is what moves"
        )

    _release(combo, _row_center(combo, 3))
    _settle(app)
    assert combo.currentIndex() == 3


# -- (f) keyboard and wheel policy keep their own contracts ----------------


def test_the_keyboard_path_still_walks_and_commits(qtbot):
    app, host, combo = _fixture(qtbot)
    _press(combo, _field_center(combo))
    _release(combo, _field_center(combo))
    _settle(app)
    assert combo._expanded

    QTest.keyClick(combo, Qt.Key.Key_Down)
    _settle(app)
    assert combo.currentIndex() == 1, "Down must still walk the selection"
    QTest.keyClick(combo, Qt.Key.Key_Return)
    _settle(app)
    assert not combo._expanded
    assert combo.currentIndex() == 1, "Enter must still commit the walked row"


def test_the_wheel_policy_survives_an_pointer_open_close_cycle(qtbot):
    app = QApplication.instance()
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(320, 240)
    other = QLineEdit(parent=host)
    other.setGeometry(0, 0, 120, 24)
    combo = ComboBox(parent=host, wheel_requires_focus=True)
    combo.setGeometry(0, 40, 200, 33)
    combo.addItems([str(i) for i in range(20)])
    combo.setMaxVisibleItems(5)
    combo.setCurrentIndex(0)
    host.show()
    qtbot.waitExposed(host)
    other.setFocus(Qt.FocusReason.OtherFocusReason)
    _settle(app)
    assert not combo.hasFocus()

    _press(combo, _field_center(combo))
    _release(combo, _field_center(combo))
    _settle(app)
    assert combo._expanded
    _press(combo, _field_center(combo))
    _release(combo, _field_center(combo))
    _settle(app)
    assert not combo._expanded

    _wheel(combo)
    assert combo.currentIndex() == 0, (
        "an open/close cycle is not a deliberate focus grant: the wheel must not step a "
        "policy-protected combo"
    )


def test_the_wheel_over_an_open_list_scrolls_it(qtbot):
    app = QApplication.instance()
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(420, 420)
    combo = ComboBox(parent=host, wheel_requires_focus=True)
    combo.setGeometry(40, 160, 200, 33)
    combo.addItems([str(i) for i in range(20)])
    combo.setMaxVisibleItems(5)
    combo.setCurrentIndex(0)
    host.show()
    qtbot.waitExposed(host)
    _settle(app)

    _press(combo, _field_center(combo))
    _release(combo, _field_center(combo))
    _settle(app)
    assert combo._expanded

    before = combo._scroll_offset
    event = _wheel(combo._overlay)
    assert event.isAccepted(), "the open list must accept the wheel it scrolled"
    assert combo._scroll_offset == before + 1
    assert combo.currentIndex() == 0, "scrolling the rows must not change the value"
