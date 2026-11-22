"""A value control answers the wheel only when it has focus.

Why this file exists: RVE's settings pages are long columns inside a scroll area, and the toolkit's controls took the
wheel on hover - the first tick over a combo focused it AND stepped its value, so scrolling a page silently rewrote
whatever the pointer crossed (owner report 2026-11-22: "tons of misclicks"). `WheelScrollPolicyMixin` carries the fix
(`wheel_requires_focus`): with the flag on, `shouldHandleWheelEvent` ignores the event instead of focusing the control,
and an ignored wheel event propagates to the enclosing scroll area. Both halves are pinned here - the refusal, and the
fact that a FOCUSED control still steps, so the policy cannot degenerate into "the wheel never works".
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.widgets import ComboBox, DoubleSpinBox


def _wheel(widget, delta: int = -120, app: QApplication | None = None) -> QWheelEvent:
    app = app or QApplication.instance()
    local = widget.rect().center()
    event = QWheelEvent(QPointF(local), QPointF(widget.mapToGlobal(local)), QPoint(0, 0), QPoint(0, delta),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(widget, event)
    for _ in range(4):
        app.processEvents()
    return event


def test_an_unfocused_combo_refuses_the_wheel(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    combo = ComboBox(parent=host, wheel_requires_focus=True)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    host.resize(300, 200)
    host.show()
    qtbot.waitExposed(host)

    _wheel(combo)
    assert combo.currentIndex() == 0, "the wheel stepped a combo the pointer only HOVERED"


def test_the_same_combo_without_the_policy_steps():
    """The identical gesture on the same widget family, policy off: the instrument can see a change at all."""
    app = QApplication.instance()
    host = QWidget()
    combo = ComboBox(parent=host, wheel_requires_focus=False)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    host.resize(300, 200)
    host.show()
    for _ in range(4):
        app.processEvents()

    _wheel(combo, app=app)
    assert combo.currentIndex() == 1, "with the policy off the wheel must step the combo - otherwise the pin proves nothing"


def test_a_focused_combo_still_steps(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    combo = ComboBox(parent=host, wheel_requires_focus=True)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    host.resize(300, 200)
    host.show()
    qtbot.waitExposed(host)
    combo.setFocus(Qt.FocusReason.OtherFocusReason)
    for _ in range(4):
        QApplication.instance().processEvents()
    assert combo.hasFocus()

    _wheel(combo)
    assert combo.currentIndex() == 1, "a focused combo must still answer the wheel"


def test_the_refused_wheel_is_left_unaccepted_so_the_page_can_scroll(qtbot):
    """Refusing is only half of it: the event must stay UNACCEPTED - that is what lets Qt hand it to the enclosing
    scroll area. A control that swallowed the tick would leave the page frozen under the cursor.

    `sendEvent` reaches one widget only (Qt's parent propagation happens in the platform delivery, so a synthetic event
    cannot demonstrate the scroll itself - the live app did: four notches over the Backend combo scrolled the General
    tab and left the combo on "tensorrt", 2026-11-22). What is asserted here is the precondition: accepted == False.
    """
    host = QWidget()
    qtbot.addWidget(host)
    combo = ComboBox(parent=host, wheel_requires_focus=True)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    host.resize(300, 200)
    host.show()
    qtbot.waitExposed(host)

    event = _wheel(combo)
    assert not event.isAccepted(), "the combo swallowed the wheel instead of leaving it to the scroll area"
    assert combo.currentIndex() == 0


def test_a_control_that_does_handle_the_wheel_accepts_it(qtbot):
    """The other half of the same contract, on the same gesture: policy off -> accepted, so no page scroll."""
    host = QWidget()
    qtbot.addWidget(host)
    combo = ComboBox(parent=host, wheel_requires_focus=False)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    host.resize(300, 200)
    host.show()
    qtbot.waitExposed(host)

    event = _wheel(combo)
    assert event.isAccepted(), "a stepping combo must accept the wheel it acted on"
    assert combo.currentIndex() == 1


def test_a_spin_box_obeys_the_same_policy(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    spin = DoubleSpinBox(parent=host, wheel_requires_focus=True)
    spin.setRange(0.0, 10.0)
    spin.setValue(5.0)
    host.resize(300, 200)
    host.show()
    qtbot.waitExposed(host)

    _wheel(spin)
    assert spin.value() == 5.0, "the wheel changed a spin box the pointer only hovered"
