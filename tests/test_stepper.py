"""The numeric stepper: a SpinBox that shows how to step it.

Why (2026-10-25): a settings row with a bare ``SpinBox`` reads as a text field —
nothing says "number", and the only way to change the value is typing. The
AI settings page shipped exactly that for "Judge run call ceiling" and
"Parallel judge requests"; the owner's words for it were "a plain lineedit".

The gauge is the one ``TimeLineEdit`` already had, now shared through
``StepButtonsMixin`` so the value can be stepped by mouse (with hold-to-repeat),
Up/Down keys and the wheel, and stays clamped by ``setRange``.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from sli_ui_toolkit.widgets import Stepper


@pytest.fixture
def stepper(qapp):
    box = Stepper(default_value=3)
    box.setRange(1, 8)
    box.resize(160, 32)
    box.show()
    yield box
    box.close()


def _press(box, direction: str) -> None:
    """Press a step arrow the way the mouse does, then release it."""
    button = box._up_button if direction == "up" else box._down_button
    button.pressed.emit()
    button.released.emit()


def _key_event(key):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


def test_the_gutter_is_visible_and_reserves_the_text_room(stepper):
    assert stepper.stepButtonsVisible() is True
    gutter = stepper.STEP_BUTTON_WIDTH * 2 + stepper.STEP_BUTTON_GAP
    up = stepper._up_button_rect()
    down = stepper._down_button_rect()
    assert up.right() >= stepper.width() - gutter - 1
    assert down.right() <= stepper.width()
    assert up.left() >= 0 and down.left() > up.left()


def test_clicking_the_arrows_steps_the_value(stepper):
    assert stepper.value() == 3

    _press(stepper, "up")
    assert stepper.value() == 4

    _press(stepper, "down")
    _press(stepper, "down")
    assert stepper.value() == 2


def test_the_step_size_is_honoured_and_clamped(stepper):
    stepper.setRange(0, 10)
    stepper.setValue(9)
    stepper.setStep(5)

    _press(stepper, "up")
    assert stepper.value() == 10, "must clamp at the range maximum"

    stepper.setValue(2)
    _press(stepper, "down")
    assert stepper.value() == 0, "must clamp at the range minimum"


def test_keyboard_up_and_down_step_the_value(stepper):
    stepper.setFocus()
    stepper.keyPressEvent(_key_event(Qt.Key.Key_Up))
    assert stepper.value() == 4
    stepper.keyPressEvent(_key_event(Qt.Key.Key_Down))
    assert stepper.value() == 3


def test_hiding_the_gutter_leaves_a_plain_field(stepper):
    stepper.setStepButtonsVisible(False)

    assert stepper.stepButtonsVisible() is False
    assert stepper._up_button.isVisible() is False
    assert stepper._down_button.isVisible() is False


def test_value_changed_is_emitted_for_a_step(stepper):
    seen: list[int] = []
    stepper.valueChanged.connect(seen.append)

    _press(stepper, "up")

    assert seen == [4]

