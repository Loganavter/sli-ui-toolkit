"""A toggle created already-on must be on in its FIRST frame.

Owner report 2026-10-22: "при их создании мы не можем создать их сразу
активированными и в первые кадры они переключаются, если им нужно было
изначально быть активными".

Cause: ``Switch.setChecked`` and ``CheckBox``'s ``toggled`` handler always ran the
knob animation from the CURRENT progress, which is 0.0 on a fresh widget. So a
toggle configured before it is shown (``sw = Switch(); sw.setChecked(True)`` —
the normal build-time pattern) painted "off" on the first frame and slid on
afterwards.

The rule pinned here: a state change while the widget is not visible SNAPS to the
target (nothing to animate, nobody watching); a state change while it IS visible
still animates, because that motion is the affordance.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import CheckBox, Switch


def _animation_running(anim: QAbstractAnimation) -> bool:
    return anim.state() == QAbstractAnimation.State.Running


def test_a_switch_created_on_is_on_before_it_is_shown(qtbot):
    switch = Switch()
    qtbot.addWidget(switch)

    switch.setChecked(True)

    assert switch.isChecked()
    assert switch._progress == 1.0, "a fresh switch must snap to 'on', not start from 0.0"
    assert not _animation_running(switch._anim), "no animation may run before the first show"


def test_a_switch_created_on_is_still_on_in_its_first_frame(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    layout.addWidget(switch)
    qtbot.addWidget(host)
    switch.setChecked(True)

    host.show()
    qtbot.waitExposed(host)

    assert switch._progress == 1.0, "the first painted frame must already be 'on'"


def test_a_visible_switch_still_animates(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    layout.addWidget(switch)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    switch.setChecked(True)

    assert _animation_running(switch._anim), "a visible toggle must keep its motion"
    qtbot.waitUntil(lambda: switch._progress == 1.0, timeout=1000)


def test_a_hidden_switch_snaps_instead_of_animating(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    layout.addWidget(switch)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    switch.setChecked(True)
    qtbot.waitUntil(lambda: switch._progress == 1.0, timeout=1000)
    host.hide()

    switch.setChecked(False)

    assert switch._progress == 0.0, "a hidden toggle has nothing to animate"
    assert not _animation_running(switch._anim)


def test_a_checkbox_created_on_is_on_before_it_is_shown(qtbot):
    checkbox = CheckBox("text")
    qtbot.addWidget(checkbox)

    checkbox.setChecked(True)

    assert checkbox.isChecked()
    assert checkbox._checked_progress == 1.0, (
        "a fresh checkbox must snap its indicator to 'on', not start from 0.0"
    )
    assert not _animation_running(checkbox._checked_anim)


def test_a_visible_checkbox_still_animates(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    checkbox = CheckBox("text")
    layout.addWidget(checkbox)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    checkbox.setChecked(True)

    assert _animation_running(checkbox._checked_anim), "a visible checkbox must keep its motion"
    qtbot.waitUntil(lambda: checkbox._checked_progress == 1.0, timeout=1000)


def test_a_toggle_can_be_created_on_and_still_toggles_by_click(qtbot):
    """The on-at-build state must not leave the widget wedged."""
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    layout.addWidget(switch)
    qtbot.addWidget(host)
    switch.setChecked(True)
    host.show()
    qtbot.waitExposed(host)

    qtbot.mouseClick(switch, Qt.MouseButton.LeftButton, pos=switch.rect().center())

    assert not switch.isChecked()
    qtbot.waitUntil(lambda: switch._progress == 0.0, timeout=1000)
