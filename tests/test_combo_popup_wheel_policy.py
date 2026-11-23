"""Opening and closing a ComboBox popup must not silence `wheel_requires_focus`.

The promise of the policy (see
:mod:`sli_ui_toolkit.ui.widgets.helpers.wheel_scroll_policy`): with
``wheel_requires_focus=True`` a wheel changes the value only when the control
was deliberately focused — a popup open/close cycle is not a deliberate focus
grant. Owner report 2026-11-24: after opening and closing the combo, a wheel
over it stepped the value although the user never clicked into the field.

The cycle is driven through ``showDropdown``/``hideDropdown`` (the widget's own
API), so nothing here depends on a real pointer. The mechanism it pins: this
toolkit's ``Button`` takes no Qt focus from a mouse press, the dropdown never
grabs focus while open, and the popup's close used to restore focus onto the
field — a grant no user gesture had made.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
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
