"""``TimeLineEdit``: the ``HH:mm`` field and the ▲/▼ step gauge it carried alone.

Why this file exists (2026-10-25): the gauge was written inside ``TimeLineEdit``
first and then shared with ``Stepper`` through ``StepButtonsMixin``, but only
the copy stayed in use — the original had no test, so folding it onto the mixin
would have been an unverified change to a shipping input. These tests pin the
behaviour first; they must stay green, unchanged, when the duplicate classes and
privates are deleted.

Falsification story (what fails if the gauge is deleted):
deleting the ▲/▼ gutter (its buttons, layout, paint, hold-to-repeat) makes
``test_up_arrow_*``, ``test_arrow_press_focuses_the_field``,
``test_stepping_down_from_midnight_wraps_to_2359``, ``test_hold_*``,
``test_release_*``, ``test_leaving_*``, ``test_hiding_the_buttons_hides_*``,
``test_disabling_*``, ``test_the_gutter_*``, ``test_hiding_the_buttons_releases_*``,
``test_snake_case_aliases_agree`` and ``test_painting_the_gutter_does_not_crash``
fail (missing ``_up_button`` / raised ``NotImplementedError``). The keyboard,
wheel and text-normalisation tests deliberately survive that deletion — they
prove the host behaviour the fold must not disturb.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QTime, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QWheelEvent

from sli_ui_toolkit.widgets import TimeLineEdit


@pytest.fixture
def field(qapp):
    edit = TimeLineEdit()
    edit.resize(160, 32)
    edit.show()
    yield edit
    edit.close()


def _press(edit, direction: str, release: bool = True) -> None:
    """Press a step arrow the way the mouse does (optionally hold it)."""
    button = edit._up_button if direction == "up" else edit._down_button
    button.pressed.emit()
    if release:
        button.released.emit()


def _key_event(key, text: str = ""):
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)


def _wheel_event(y_angle_delta: int):
    """A vertical-wheel event over the field (positive = wheel up)."""
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, y_angle_delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def _gutter(edit) -> int:
    return edit.STEP_BUTTON_WIDTH * 2 + edit.STEP_BUTTON_GAP


# -- arrows ------------------------------------------------------------------


def test_the_gutter_is_visible_and_reserves_the_text_room(field):
    assert field.stepButtonsVisible() is True
    assert field._up_button.isVisible() is True
    assert field._down_button.isVisible() is True
    up = field._up_button_rect()
    down = field._down_button_rect()
    assert up.left() < down.left(), "up arrow sits left of the down arrow"
    assert up.right() >= field.width() - _gutter(field) - 1
    assert down.right() <= field.width()


def test_the_gutter_geometry_is_unchanged(field):
    """The numbers the fold must preserve (22 / 0 / 1 / 22 / 350 / 70)."""
    assert TimeLineEdit.STEP_BUTTON_WIDTH == 22
    assert TimeLineEdit.STEP_BUTTON_GAP == 0
    assert TimeLineEdit.STEP_BUTTON_OVERLAP == 1
    assert TimeLineEdit.STEP_ARROW_SIZE == 22
    assert TimeLineEdit.REPEAT_START_DELAY_MS == 350
    assert TimeLineEdit.REPEAT_INTERVAL_MS == 70
    assert field._up_button.width() == TimeLineEdit.STEP_BUTTON_WIDTH + TimeLineEdit.STEP_BUTTON_OVERLAP
    assert field._down_button.width() == TimeLineEdit.STEP_BUTTON_WIDTH


def test_up_arrow_adds_one_minute_and_down_arrow_subtracts_one(field):
    field.setText("10:20")
    _press(field, "up")
    assert field.text() == "10:21"
    _press(field, "down")
    _press(field, "down")
    assert field.text() == "10:19"


def test_arrow_press_focuses_the_field(field, qapp):
    field.clearFocus()
    qapp.processEvents()
    assert field.hasFocus() is False, "precondition: the field is unfocused"

    _press(field, "up")
    qapp.processEvents()
    assert field.hasFocus() is True
    assert field.text() == "00:06"


def test_stepping_down_from_midnight_wraps_to_2359(field):
    field.setText("00:00")
    _press(field, "down")
    assert field.text() == "23:59"

    _press(field, "up")
    assert field.text() == "00:00"


# -- hold-to-repeat ----------------------------------------------------------


def test_hold_starts_the_single_shot_then_repeats_the_same_delta(field):
    field.setText("00:05")
    _press(field, "up", release=False)

    assert field.text() == "00:06"
    assert field._repeat_start_timer.isActive() is True
    assert field._repeat_timer.isActive() is False

    field._repeat_start_timer.timeout.emit()
    assert field._repeat_timer.isActive() is True

    field._repeat_timer.timeout.emit()
    field._repeat_timer.timeout.emit()
    assert field.text() == "00:08", "every repeat tick applies the same +1 minute"


def test_release_stops_both_timers_and_the_repeat(field):
    field.setText("00:05")
    _press(field, "up", release=False)
    field._repeat_start_timer.timeout.emit()
    assert field._repeat_timer.isActive() is True

    field._up_button.released.emit()

    assert field._repeat_start_timer.isActive() is False
    assert field._repeat_timer.isActive() is False
    field._repeat_timer.timeout.emit()
    assert field.text() == "00:06", "the active delta is cleared on stop"


def test_leaving_the_button_stops_the_repeat(field, qapp):
    _press(field, "down", release=False)
    field._repeat_start_timer.timeout.emit()
    assert field._repeat_timer.isActive() is True

    qapp.sendEvent(field._down_button, QEvent(QEvent.Type.Leave))

    assert field._repeat_start_timer.isActive() is False
    assert field._repeat_timer.isActive() is False
    stepped = field.text()
    field._repeat_timer.timeout.emit()
    assert field.text() == stepped


def test_hiding_the_buttons_hides_the_arrows_and_the_release_stops_the_repeat(field):
    """Hiding takes the arrows away; ending the hold stops the repeat.

    Known divergence, deliberately not pinned here: today the duplicate in
    ``TimeLineEdit`` leaves both timers running when the gutter is hidden
    mid-hold, while ``StepButtonsMixin`` stops them on hide. This file has to
    stay green across the fold, so it pins the shared part — hidden arrows and
    a release (or a leave / focus-out, above) stopping the repeat.
    """
    _press(field, "up", release=False)
    field._repeat_start_timer.timeout.emit()
    assert field._repeat_timer.isActive() is True

    field.setStepButtonsVisible(False)
    assert field._up_button.isVisible() is False
    assert field._down_button.isVisible() is False

    field._down_button.released.emit()
    assert field._repeat_start_timer.isActive() is False
    assert field._repeat_timer.isActive() is False
    stepped = field.text()
    field._repeat_timer.timeout.emit()
    assert field.text() == stepped


def test_focus_out_stops_the_repeat(field):
    _press(field, "up", release=False)
    field._repeat_start_timer.timeout.emit()
    assert field._repeat_timer.isActive() is True

    field.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))

    assert field._repeat_start_timer.isActive() is False
    assert field._repeat_timer.isActive() is False


# -- keyboard / wheel --------------------------------------------------------


def test_keyboard_up_and_down_step_one_minute(field):
    field.setText("10:20")
    field.keyPressEvent(_key_event(Qt.Key.Key_Up))
    assert field.text() == "10:21"
    field.keyPressEvent(_key_event(Qt.Key.Key_Down))
    assert field.text() == "10:20"


def test_wheel_steps_and_takes_focus_by_default(field, qapp):
    assert field.wheelRequiresFocus() is False
    field.clearFocus()
    qapp.processEvents()
    field.setText("10:20")

    event = _wheel_event(120)
    field.wheelEvent(event)

    assert field.text() == "10:21", "one notch up adds one minute"
    assert event.isAccepted() is True
    assert field.hasFocus() is True, "the default policy focuses on wheel"

    field.wheelEvent(_wheel_event(-120))
    assert field.text() == "10:20"


def test_wheel_is_ignored_while_unfocused_when_it_requires_focus(qapp):
    edit = TimeLineEdit(wheel_requires_focus=True)
    edit.resize(160, 32)
    edit.show()
    try:
        assert edit.wheelRequiresFocus() is True
        edit.clearFocus()
        qapp.processEvents()
        edit.setText("10:20")

        event = _wheel_event(120)
        edit.wheelEvent(event)

        assert edit.text() == "10:20"
        assert event.isAccepted() is False
        assert edit.hasFocus() is False
    finally:
        edit.close()


# -- text normalisation ------------------------------------------------------


def test_set_text_normalises_hh_mm(field):
    field.setText("9:5")
    assert field.text() == "09:05"
    field.setText("23:59")
    assert field.text() == "23:59"
    field.setText("0:00")
    assert field.text() == "00:00"


def test_a_single_digit_is_zero_filled(field):
    """Current behaviour: a bare digit lands in the MINUTE slot (``8`` → ``00:08``).

    Pinned as-is: this task is a de-duplication, so the normalisation rules may
    not move. (The mission brief guessed ``08:00``; the tree says otherwise.)
    """
    field.setText("8")
    assert field.text() == "00:08"


def test_unparseable_text_falls_back_to_the_last_valid_value(field):
    field.setText("07:30")
    field.setText("banana")
    assert field.text() == "07:30"
    field.setText("99:99")
    assert field.text() == "07:30", "out-of-range values are rejected too"


def test_a_half_typed_value_stays_until_editing_finishes(field):
    field.setText("00:00")
    field.selectAll()

    field.keyPressEvent(_key_event(Qt.Key.Key_9, "9"))
    assert field.text() == "9", "the half-typed value is not normalised mid-edit"

    field.editingFinished.emit()
    assert field.text() == "00:09"


def test_focus_out_normalises_a_half_typed_value(field):
    field.setText("00:00")
    field.selectAll()
    field.keyPressEvent(_key_event(Qt.Key.Key_7, "7"))

    field.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))

    assert field.text() == "00:07"


def test_time_round_trips(field):
    field.setTime(QTime(9, 7))
    assert field.text() == "09:07"
    assert field.time() == QTime(9, 7)

    field.setTime(QTime(23, 59))
    assert field.time() == QTime(23, 59)


# -- enabled / visibility / aliases -----------------------------------------


def test_disabling_the_field_disables_the_arrows_and_keeps_the_gutter(field):
    up_rect = field._up_button_rect()
    down_rect = field._down_button_rect()
    right_margin = field.textMargins().right()

    field.setEnabled(False)

    assert field._up_button.isEnabled() is False
    assert field._down_button.isEnabled() is False
    assert field._up_button_rect() == up_rect
    assert field._down_button_rect() == down_rect
    assert field.textMargins().right() == right_margin

    field.setEnabled(True)
    assert field._up_button.isEnabled() is True


def test_hiding_the_buttons_releases_the_text_room(field):
    gutter = _gutter(field)
    shown_right = field.textMargins().right()
    shown_hint = field.sizeHint().width()
    shown_min = field.minimumSizeHint().width()

    field.setStepButtonsVisible(False)

    assert field.stepButtonsVisible() is False
    assert field._up_button.isVisible() is False
    assert field._down_button.isVisible() is False
    assert field.textMargins().right() == shown_right - gutter
    assert field.sizeHint().width() == field.minimumSizeHint().width()
    assert field.sizeHint().width() < shown_hint
    assert field.minimumSizeHint().width() < shown_min

    field.setStepButtonsVisible(True)
    assert field.textMargins().right() == shown_right
    assert field.sizeHint().width() == shown_hint


def test_snake_case_aliases_agree(field):
    assert field.step_buttons_visible() is True
    field.set_step_buttons_visible(False)
    assert field.step_buttons_visible() is False
    assert field.stepButtonsVisible() is False
    field.set_step_buttons_visible(True)
    assert field.step_buttons_visible() is True
    assert field.stepButtonsVisible() is True


def test_painting_the_gutter_does_not_crash(field):
    assert field.grab().isNull() is False

    field.setEnabled(False)
    assert field.grab().isNull() is False

    field.setEnabled(True)
    field.setStepButtonsVisible(False)
    assert field.grab().isNull() is False
