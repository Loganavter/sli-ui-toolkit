"""Opening and closing a ComboBox popup must not silence `wheel_requires_focus`.

The promise of the policy (see
:mod:`sli_ui_toolkit.ui.widgets.helpers.wheel_scroll_policy`): with
``wheel_requires_focus=True`` a wheel changes the value only when the control
was deliberately focused — a popup open/close cycle is not a deliberate focus
grant. Owner report 2026-11-24: after opening and closing the combo, a wheel
over it stepped the value although the user never clicked into the field.

The cycle is driven through ``showDropdown``/``hideDropdown`` (the widget's own
API), and the reported pointer path through a window-level ``QTest`` click. The
mechanism it pins: the dropdown never grabs focus while open, and the popup's
close must not hand the field a focus the user's gesture did not ask for. Two
gestures differ and both are pinned here: a mouse click on a row commits the
value, while Tab/arrow/Enter keeps the field focused for the next keystroke.

A window-level click matters: Qt's own click-focus policy runs in
``QWidgetWindow`` *before* the press reaches the widget, so a real press on the
field focuses it even though ``_ButtonEvents.mousePressEvent`` never asks for
focus. Round one's fix recorded "did the field have focus" at open, which read
that press-granted focus as a deliberate one (owner report 2026-11-24, second
round: open, pick a row, wheel steps the value).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from sli_ui_toolkit.widgets import ComboBox


def _wheel(widget, delta: int = -120, app: QApplication | None = None) -> QWheelEvent:
    app = app or QApplication.instance()
    local = widget.rect().center()
    event = QWheelEvent(QPointF(local), QPointF(widget.mapToGlobal(local)), QPoint(0, 0), QPoint(0, delta),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(widget, event)
    for _ in range(4):
        app.processEvents()
    return event


def _settle(app: QApplication, rounds: int = 8) -> None:
    for _ in range(rounds):
        app.processEvents()


def _widget_name(widget) -> str | None:
    return type(widget).__name__ if widget is not None else None


def _window_click(host: QWidget, target: QWidget, point=None) -> None:
    """Click ``target`` the way the platform delivers it.

    ``QTest.mouseClick(target, ...)`` bypasses ``QWidgetWindow``, so it skips
    Qt's click-focus policy — precisely the step that grants a real press on
    the field focus before the widget sees it. Delivering to the window runs
    that policy, which is what the owner's report exercises.
    """
    pos = target.mapTo(host, point if point is not None else target.rect().center())
    QTest.mouseClick(host.windowHandle(), Qt.MouseButton.LeftButton, pos=pos)


def _focused_host(qtbot, *, wheel_requires_focus: bool = True, items=("A", "B", "C")):
    """Host with a focus sink + a combo, focus parked outside the combo.

    A lone combo in a window receives focus from Qt on show, which would make
    the pin start from "deliberately focused" and prove nothing — the report
    starts with the pointer hovering a combo while focus is elsewhere.
    """
    app = QApplication.instance()
    host = QWidget()
    qtbot.addWidget(host)
    other = QLineEdit(parent=host)
    other.setGeometry(0, 0, 120, 24)
    combo = ComboBox(parent=host, wheel_requires_focus=wheel_requires_focus)
    combo.setGeometry(0, 40, 200, 33)
    combo.addItems(list(items))
    combo.setCurrentIndex(0)
    host.resize(300, 200)
    host.show()
    qtbot.waitExposed(host)
    other.setFocus(Qt.FocusReason.OtherFocusReason)
    _settle(app)
    return host, combo, other


def test_a_popup_open_close_cycle_does_not_grant_the_wheel(qtbot):
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)
    assert not combo.hasFocus(), "the fixture must start with focus outside the combo"

    focus_trace: list[tuple[str, str]] = []

    def _on_focus_changed(old, now):
        focus_trace.append((type(old).__name__ if old else None, type(now).__name__ if now else None))

    app.focusChanged.connect(_on_focus_changed)
    try:
        state_before = (combo.hasFocus(), combo.wheelRequiresFocus(), combo.currentIndex())
        combo.showDropdown()
        _settle(app)
        while_open = (combo.hasFocus(), combo.wheelRequiresFocus(), app.focusWidget())
        combo.hideDropdown()
        _settle(app)
        state_after = (combo.hasFocus(), combo.wheelRequiresFocus(), combo.currentIndex())

        event = _wheel(combo, app=app)
        index_after_wheel = combo.currentIndex()
    finally:
        app.focusChanged.disconnect(_on_focus_changed)

    print(
        "\n[popup-cycle] before(hasFocus, policy, index)=",
        state_before,
        "\n[popup-cycle] while-open(hasFocus, policy, focusWidget)=",
        while_open,
        "\n[popup-cycle] after(hasFocus, policy, index)=",
        state_after,
        "\n[popup-cycle] focusWidget after close=",
        app.focusWidget(),
        "\n[popup-cycle] wheel accepted=",
        event.isAccepted(),
        "index after wheel=",
        index_after_wheel,
        "\n[popup-cycle] focusChanged=",
        focus_trace,
    )

    assert app.focusWidget() is other, (
        "closing the list must leave focus where it was, not park it on the field "
        f"(focusChanged={focus_trace})"
    )
    assert combo.currentIndex() == 0, (
        "the popup open/close cycle granted the wheel: "
        f"hasFocus={state_after[0]}, policy={state_after[1]}, "
        f"focus={app.focusWidget()}, focusTrace={focus_trace}"
    )
    assert not event.isAccepted(), "the refused wheel must stay unaccepted so the page can scroll"


def test_a_keyboard_focused_combo_keeps_focus_across_the_cycle(qtbot):
    """The legitimate case: focus granted by the user survives the popup close.

    That focus was granted by Tab, so the wheel must still step the value
    afterwards — the fix for the test above must not turn into "a combo can
    never be wheeled once it has shown its list".
    """
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)
    combo.setFocus(Qt.FocusReason.TabFocusReason)
    _settle(app)
    assert combo.hasFocus()

    combo.showDropdown()
    _settle(app)
    combo.hideDropdown()
    _settle(app)

    assert combo.hasFocus(), "a keyboard-focused combo lost focus because its popup closed"

    _wheel(combo, app=app)
    assert combo.currentIndex() == 1, "a deliberately focused combo must still answer the wheel"


def test_a_click_opened_cycle_returns_focus_to_the_previous_widget(qtbot):
    """Button takes no focus from a press, so a click-open must not grant it.

    Pinned separately from the programmatic cycle because it is the reported
    path: the pointer clicks the field, the list opens and closes, and the
    keyboard must be left wherever it was.
    """
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)
    assert not combo.hasFocus()

    # Same state a real left press leaves behind: no focus move, expanded.
    combo._on_field_clicked()
    _settle(app)
    assert combo._expanded
    combo._on_field_clicked()
    _settle(app)

    assert not combo._expanded
    assert app.focusWidget() is other, "the click-opened list handed the field focus it never took"
    _wheel(combo, app=app)
    assert combo.currentIndex() == 0


def test_the_wheel_over_an_open_list_still_scrolls_it(qtbot):
    """The policy must not freeze the list under the pointer: an open popup
    scrolls its rows and leaves the value alone."""
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot, items=[str(i) for i in range(20)])
    combo.setMaxVisibleItems(5)
    combo.showDropdown()
    _settle(app)
    assert combo._overlay is not None and combo._overlay.isVisible()

    before_offset = combo._scroll_offset
    event = _wheel(combo._overlay, app=app)

    assert event.isAccepted(), "the open list must accept the wheel it scrolled"
    assert combo._scroll_offset == before_offset + 1, "the wheel over the open list must scroll it"
    assert combo.currentIndex() == 0, "scrolling the list must not change the value"
    combo.hideDropdown()
    _settle(app)


def test_without_the_policy_the_cycle_is_unchanged(qtbot):
    """`wheel_requires_focus=False` keeps its old behaviour: the wheel steps."""
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot, wheel_requires_focus=False)
    combo.showDropdown()
    _settle(app)
    combo.hideDropdown()
    _settle(app)

    event = _wheel(combo, app=app)
    assert event.isAccepted()
    assert combo.currentIndex() == 1, "policy off: an open/close cycle must not stop the wheel from stepping"


def test_a_mouse_selection_leaves_focus_where_the_list_found_it(qtbot):
    """The owner's second report: open, pick a row, wheel over the field.

    A real press on the field is click-focused by Qt before the widget sees it,
    so "the field had focus at open" is true even though the user only opened
    the list. A second press focuses the row; the close then used to restore
    the anchor (the field) and the wheel stepped the committed value. The
    focus must end where it was before the opening gesture.
    """
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)
    assert not combo.hasFocus(), "the fixture must start with focus outside the combo"

    focus_trace: list[tuple[str | None, str | None]] = []

    def _on_focus_changed(old, now):
        focus_trace.append((_widget_name(old), _widget_name(now)))

    app.focusChanged.connect(_on_focus_changed)
    try:
        # (a) before open
        focus_before = app.focusWidget()
        # The composed gesture the report describes: press the field (Qt
        # click-focuses it, the list opens on release), press a row (Qt
        # click-focuses it, the value commits and the list closes).
        _window_click(host, combo)
        _settle(app)
        # (b) after open
        focus_open = app.focusWidget()
        row = combo.dropdown_row_widget(1)
        assert combo._expanded and row is not None, "the click on the field must open the list"
        # (c) at the moment the row is pressed (before the commit closes it)
        at_click: dict[str, object] = {}
        row.pressed.connect(lambda: at_click.setdefault("focus", app.focusWidget()))
        _window_click(host, row)
        _settle(app)
        # (d) after close
        focus_after = app.focusWidget()
        index_after_click = combo.currentIndex()

        event = _wheel(combo, app=app)
        index_after_wheel = combo.currentIndex()
    finally:
        app.focusChanged.disconnect(_on_focus_changed)

    print(
        "\n[popup-select] (a) focus before open=",
        _widget_name(focus_before),
        "\n[popup-select] (b) focus after open=",
        _widget_name(focus_open),
        "combo.hasFocus=",
        focus_open is combo,
        "\n[popup-select] (c) focus when the row is pressed=",
        _widget_name(at_click.get("focus")),
        "\n[popup-select] (d) focus after close=",
        _widget_name(focus_after),
        "combo.hasFocus=",
        combo.hasFocus(),
        "\n[popup-select] index=",
        combo.currentIndex(),
        "wheel accepted=",
        event.isAccepted(),
        "index after wheel=",
        index_after_wheel,
        "\n[popup-select] focusChanged=",
        focus_trace,
    )

    assert index_after_click == 1, "the row click must commit the value before the focus check"
    assert not combo._expanded, "the row click must close the list"
    assert focus_after is focus_before, (
        "a mouse selection must leave focus exactly where the list found it, "
        f"got {_widget_name(focus_after)} (focusChanged={focus_trace})"
    )
    assert index_after_wheel == 1, (
        "the mouse selection granted the wheel: "
        f"hasFocus={combo.hasFocus()}, focus={_widget_name(app.focusWidget())}, "
        f"focusTrace={focus_trace}"
    )
    assert not event.isAccepted(), "the refused wheel must stay unaccepted so the page can scroll"


def test_a_mouse_selection_with_no_prior_focus_leaves_nothing_focused(qtbot):
    """The common live case: nothing was focused, the pointer picks a row.

    Closing must not leave the field as the window's focus widget — that is
    the grant which made the wheel step, and Qt would otherwise hand the
    field focus through the focus chain when the focused row is hidden.
    """
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)
    other.clearFocus()
    _settle(app)
    assert app.focusWidget() is None, "the fixture must start with nothing focused"

    _window_click(host, combo)
    _settle(app)
    assert combo._expanded
    row = combo.dropdown_row_widget(2)
    assert row is not None
    _window_click(host, row)
    _settle(app)

    assert combo.currentIndex() == 2
    assert not combo._expanded
    assert app.focusWidget() is not combo, (
        "a mouse selection left the field focused with no gesture that asked for it"
    )
    assert not combo.hasFocus()
    event = _wheel(combo, app=app)
    assert combo.currentIndex() == 2, "the mouse selection granted the wheel"
    assert not event.isAccepted()


def test_a_keyboard_selection_keeps_the_field_focused(qtbot):
    """The legitimate case: Enter opens, arrows walk, Enter commits.

    That focus was granted by Tab, so it must survive the commit and the wheel
    must still step afterwards — the fix for the mouse cases must not turn
    into "a combo can never be wheeled once it has shown its list".
    """
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)
    combo.setFocus(Qt.FocusReason.TabFocusReason)
    _settle(app)
    assert combo.hasFocus()

    QTest.keyClick(combo, Qt.Key.Key_Return)
    _settle(app)
    assert combo._expanded, "Enter on a keyboard-focused combo must open the list"
    QTest.keyClick(combo, Qt.Key.Key_Down)
    _settle(app)
    assert combo.currentIndex() == 1
    QTest.keyClick(combo, Qt.Key.Key_Return)
    _settle(app)

    assert not combo._expanded
    assert app.focusWidget() is combo, "a keyboard commit must leave the field focused"

    QTest.keyClick(combo, Qt.Key.Key_Return)
    _settle(app)
    assert combo._expanded, "the field must still receive keys after a keyboard commit"
    combo.hideDropdown()
    _settle(app)

    _wheel(combo, app=app)
    assert combo.currentIndex() == 2, "a deliberately focused combo must still answer the wheel"


def test_a_keyboard_commit_after_a_mouse_open_keeps_the_field(qtbot):
    """Mixed gesture: the pointer opens the list, the keyboard commits it.

    Once the user is driving with the keyboard, the field must stay focused —
    the mouse *selection* rule must not steal it back to the pre-open widget.
    """
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)

    _window_click(host, combo)
    _settle(app)
    assert combo._expanded
    QTest.keyClick(combo, Qt.Key.Key_Down)
    _settle(app)
    QTest.keyClick(combo, Qt.Key.Key_Return)
    _settle(app)

    assert not combo._expanded
    assert combo.currentIndex() == 1
    assert app.focusWidget() is combo, "a keyboard commit must keep the field focused, mouse-opened or not"

    _wheel(combo, app=app)
    assert combo.currentIndex() == 2


def test_a_window_click_open_and_close_restores_the_pre_click_focus(qtbot):
    """Round one's cycle under a real pointer: open, close, no selection.

    ``test_a_click_opened_cycle_returns_focus_to_the_previous_widget`` drives
    the field's handler directly, which never focuses the field. A real
    window-level press is click-focused by Qt first, so this is the same
    promise under the gesture that actually happens.
    """
    app = QApplication.instance()
    host, combo, other = _focused_host(qtbot)
    assert not combo.hasFocus()

    _window_click(host, combo)
    _settle(app)
    assert combo._expanded
    _window_click(host, combo)
    _settle(app)

    assert not combo._expanded
    assert app.focusWidget() is other, "the pointer-opened list handed the field focus it never kept"
    _wheel(combo, app=app)
    assert combo.currentIndex() == 0
