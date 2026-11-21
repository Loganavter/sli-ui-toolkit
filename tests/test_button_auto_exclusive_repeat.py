"""Button ``autoExclusive`` / ``autoRepeat`` — Qt ``QAbstractButton`` semantics.

A host's Qt compatibility layer mocked ``QPushButton``/``QCheckBox`` for these
two behaviours; they belong here instead. The oracle is stock ``QPushButton``
on this Qt (6.11.2), measured before implementing:

* ``autoExclusive`` — a checked exclusive button unchecks the siblings in the
  same parent that are *also* exclusive and checkable; a non-exclusive sibling
  is left checked beside it (measured ``[True, True, False]``: clicking the
  third exclusive one unchecks the other exclusive one only). Clicking an
  already-checked exclusive button keeps it checked.
* ``autoRepeat`` — Qt re-emits the click flow on a delay, then at an interval.
  Qt's own defaults measured: delay **300 ms**, interval **100 ms**, repeat off.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import Button, ButtonRegion


def _host(qtbot, height: int = 60) -> QWidget:
    host = QWidget()
    host.resize(400, height)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    return host


def _exclusive_row(qtbot, count: int = 3) -> tuple[QWidget, list[Button]]:
    host = _host(qtbot)
    buttons = [
        Button(f"b{index}", toggle=True, auto_exclusive=True, parent=host)
        for index in range(count)
    ]
    for index, button in enumerate(buttons):
        button.setGeometry(index * 60, 0, 56, 32)
    return host, buttons


def _click(qtbot, button: Button) -> None:
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=button.rect().center())


def _checked(buttons: list[Button]) -> list[bool]:
    return [button.isChecked() for button in buttons]


# ------------------------------------------------------------------ defaults


def test_auto_exclusive_and_auto_repeat_are_off_by_default(qtbot) -> None:
    button = Button("plain")
    qtbot.addWidget(button)

    assert button.autoExclusive() is False
    assert button.autoRepeat() is False
    # Qt's measured defaults, so a host that never calls the setters matches.
    assert button.autoRepeatDelay() == 300
    assert button.autoRepeatInterval() == 100


def test_without_the_flag_siblings_stay_independent(qtbot) -> None:
    host = _host(qtbot)
    buttons = [Button(f"b{index}", toggle=True, parent=host) for index in range(3)]
    for index, button in enumerate(buttons):
        button.setGeometry(index * 60, 0, 56, 32)

    for button in buttons:
        _click(qtbot, button)

    assert _checked(buttons) == [True, True, True], "today's behaviour is preserved"


# ------------------------------------------------------------------ exclusive


def test_checking_one_exclusive_sibling_unchecks_the_others(qtbot) -> None:
    _, buttons = _exclusive_row(qtbot)

    _click(qtbot, buttons[0])
    assert _checked(buttons) == [True, False, False]

    _click(qtbot, buttons[1])
    assert _checked(buttons) == [False, True, False]

    # The negative that names the requirement: checking the third unchecks the
    # other two, whichever was checked before.
    _click(qtbot, buttons[2])
    assert _checked(buttons) == [False, False, True]


def test_clicking_a_checked_exclusive_button_keeps_it_checked(qtbot) -> None:
    _, buttons = _exclusive_row(qtbot)
    _click(qtbot, buttons[1])
    toggles: list[bool] = []
    buttons[1].toggled.connect(toggles.append)

    _click(qtbot, buttons[1])

    assert buttons[1].isChecked(), "Qt: an exclusive button cannot be unchecked by a click"
    assert toggles == [], "no toggled signal when nothing changed"


def test_a_non_exclusive_sibling_is_left_alone(qtbot) -> None:
    host = _host(qtbot)
    a = Button("a", toggle=True, auto_exclusive=True, parent=host)
    b = Button("b", toggle=True, auto_exclusive=True, parent=host)
    c = Button("c", toggle=True, parent=host)
    for index, button in enumerate((a, b, c)):
        button.setGeometry(index * 60, 0, 56, 32)

    _click(qtbot, a)
    _click(qtbot, c)
    _click(qtbot, b)

    # Qt measurement for [exclusive, exclusive, plain]: b unchecks a only;
    # c stays checked beside the exclusive pair.
    assert (a.isChecked(), b.isChecked(), c.isChecked()) == (False, True, True)


def test_a_plain_button_does_not_join_an_exclusive_group(qtbot) -> None:
    host = _host(qtbot)
    a = Button("a", toggle=True, auto_exclusive=True, parent=host)
    plain = Button("plain", parent=host)
    for index, button in enumerate((a, plain)):
        button.setGeometry(index * 60, 0, 56, 32)
    _click(qtbot, a)
    assert a.isChecked()

    _click(qtbot, plain)

    assert a.isChecked(), "a non-checkable sibling must not clear the group"
    assert plain.isCheckable() is False


def test_programmatic_set_checked_respects_exclusivity(qtbot) -> None:
    _, buttons = _exclusive_row(qtbot)

    buttons[0].setChecked(True)
    buttons[1].setChecked(True)

    assert _checked(buttons) == [False, True, False]


def test_is_checkable_follows_the_toggle_flag_and_regions(qtbot) -> None:
    host = _host(qtbot)
    plain = Button("plain", parent=host)
    toggle = Button("toggle", toggle=True, parent=host)
    region = Button(regions=[ButtonRegion(id="_main", toggle=True)], parent=host)

    assert plain.isCheckable() is False
    assert toggle.isCheckable() is True
    assert region.isCheckable() is True


# --------------------------------------------------------------------- repeat


def _press(qtbot, button: Button):
    """Press and park the real cursor on the button.

    The HoverCoordinator reconciles every registered button against the real
    cursor on any hover event; with the cursor elsewhere it reports the button
    un-hovered and clears its pressed state, which is exactly what a *real*
    hold never does (the pointer is on the control). Offscreen has no pointer
    unless a test places one.
    """
    from PySide6.QtGui import QCursor

    original = QCursor.pos()
    QCursor.setPos(button.mapToGlobal(button.rect().center()))
    qtbot.mousePress(button, Qt.MouseButton.LeftButton, pos=button.rect().center())
    return original


def _release(qtbot, button: Button, original) -> None:
    from PySide6.QtGui import QCursor

    qtbot.mouseRelease(button, Qt.MouseButton.LeftButton, pos=button.rect().center())
    qtbot.wait(10)
    QCursor.setPos(original)


def _hold(qtbot, button: Button, ms: int) -> dict[str, int]:
    counts = {"clicked": 0, "pressed": 0, "released": 0}
    button.clicked.connect(lambda: counts.__setitem__("clicked", counts["clicked"] + 1))
    button.pressed.connect(lambda: counts.__setitem__("pressed", counts["pressed"] + 1))
    button.released.connect(lambda: counts.__setitem__("released", counts["released"] + 1))
    original = _press(qtbot, button)
    try:
        qtbot.wait(ms)
        qtbot.mouseRelease(
            button, Qt.MouseButton.LeftButton, pos=button.rect().center()
        )
        qtbot.wait(10)
    finally:
        from PySide6.QtGui import QCursor

        QCursor.setPos(original)
    return counts


def _repeat_button(
    qtbot,
    host: QWidget,
    *,
    delay: int = 20,
    interval: int = 20,
    y: int = 0,
    toggle: bool = False,
) -> Button:
    # Parented to a host the caller keeps alive: a QWidget with no Python
    # reference is garbage-collected with its children, and two top-level
    # Buttons also share the (0, 0) position a synthetic press is mapped to.
    button = Button(
        "repeat",
        toggle=toggle,
        auto_repeat=True,
        auto_repeat_delay=delay,
        auto_repeat_interval=interval,
        parent=host,
    )
    button.setGeometry(120, y, 100, 32)
    button.show()
    return button


def test_holding_a_repeating_button_emits_its_click_flow(qtbot) -> None:
    host = _host(qtbot)
    button = _repeat_button(qtbot, host)
    counts = _hold(qtbot, button, 200)

    assert counts["clicked"] >= 4, counts
    # One initial press + one per repeat; the real release closes the gap so a
    # press is never left unanswered by a click.
    assert counts["pressed"] == counts["clicked"], counts
    assert counts["released"] == 1, "the gesture itself ends exactly once"


def test_repeat_is_silent_by_default(qtbot) -> None:
    host = _host(qtbot)
    button = Button("plain", parent=host)
    button.setGeometry(120, 0, 100, 32)
    button.show()

    counts = _hold(qtbot, button, 200)

    assert counts == {"clicked": 1, "pressed": 1, "released": 1}, counts


def test_the_interval_sets_the_rate(qtbot) -> None:
    host = _host(qtbot, height=120)
    fast = _repeat_button(qtbot, host, delay=10, interval=15, y=0)
    slow = _repeat_button(qtbot, host, delay=10, interval=90, y=40)

    fast_counts = _hold(qtbot, fast, 260)
    slow_counts = _hold(qtbot, slow, 260)

    assert fast_counts["clicked"] > slow_counts["clicked"], (fast_counts, slow_counts)
    assert slow_counts["clicked"] >= 2, slow_counts


def test_the_delay_holds_the_first_repeat_back(qtbot) -> None:
    host = _host(qtbot)
    button = _repeat_button(qtbot, host, delay=400, interval=20)
    counts = {"clicked": 0}
    button.clicked.connect(lambda: counts.__setitem__("clicked", counts["clicked"] + 1))

    original = _press(qtbot, button)
    try:
        qtbot.wait(150)
        assert counts["clicked"] == 0, "nothing may fire inside the delay window"
    finally:
        _release(qtbot, button, original)
    assert counts["clicked"] == 1, "the release still delivers its own click"


def test_release_stops_the_repeat(qtbot) -> None:
    host = _host(qtbot)
    button = _repeat_button(qtbot, host)
    counts = {"clicked": 0}
    button.clicked.connect(lambda: counts.__setitem__("clicked", counts["clicked"] + 1))

    original = _press(qtbot, button)
    try:
        qtbot.wait(120)
    finally:
        _release(qtbot, button, original)
    at_release = counts["clicked"]
    qtbot.wait(150)

    assert at_release >= 2, "the hold must have repeated before the release"
    assert counts["clicked"] == at_release, "no click may arrive after the release"


def test_turning_repeat_off_mid_hold_stops_it(qtbot) -> None:
    host = _host(qtbot)
    button = _repeat_button(qtbot, host)
    counts = {"clicked": 0}
    button.clicked.connect(lambda: counts.__setitem__("clicked", counts["clicked"] + 1))

    original = _press(qtbot, button)
    try:
        qtbot.wait(120)
        button.setAutoRepeat(False)
        qtbot.wait(10)
        at_disable = counts["clicked"]
        qtbot.wait(150)
    finally:
        _release(qtbot, button, original)

    assert at_disable >= 2, "the hold repeated before the flag was cleared"
    assert counts["clicked"] == at_disable + 1, "only the real release clicks afterwards"


def test_a_repeat_tick_reaches_region_handlers(qtbot) -> None:
    host = _host(qtbot)
    button = _repeat_button(qtbot, host)
    regions: list[str] = []
    button.regionClicked.connect(regions.append)

    original = _press(qtbot, button)
    try:
        qtbot.wait(120)
    finally:
        _release(qtbot, button, original)

    assert regions and set(regions) == {"_main"}
    assert len(regions) >= 2


def test_repeat_does_not_flip_a_toggle(qtbot) -> None:
    """The named contract is clicked/pressed; Qt's per-tick state flip is not.

    A toolkit toggle that toggled on every repeat tick would thrash the value
    the user is holding the pointer on.
    """
    host = _host(qtbot)
    button = _repeat_button(qtbot, host, toggle=True)

    counts = _hold(qtbot, button, 150)

    assert counts["clicked"] >= 3, counts
    assert button.isChecked() is True, "the release click flips the toggle once"
