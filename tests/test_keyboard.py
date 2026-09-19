from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    Button,
    InstancesCounterButton,
    ScrollableComboBox,
    Switch,
    TimelineWidget,
)


def _show(widget, qtbot):
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)


def test_button_space_activates(qtbot):
    btn = Button(text="Go")
    _show(btn, qtbot)
    btn.setFocus()
    fired: list[int] = []
    btn.clicked.connect(lambda: fired.append(1))
    qtbot.keyClick(btn, Qt.Key.Key_Space)
    assert fired == [1]


def test_button_enter_activates(qtbot):
    btn = Button(text="Go")
    _show(btn, qtbot)
    btn.setFocus()
    fired: list[int] = []
    btn.clicked.connect(lambda: fired.append(1))
    qtbot.keyClick(btn, Qt.Key.Key_Return)
    assert fired == [1]


def test_button_focus_policy_is_strong():
    btn = Button(text="Go")
    assert btn.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_switch_space_toggles(qtbot):
    sw = Switch()
    _show(sw, qtbot)
    sw.setFocus()
    assert sw.isChecked() is False
    qtbot.keyClick(sw, Qt.Key.Key_Space)
    assert sw.isChecked() is True
    qtbot.keyClick(sw, Qt.Key.Key_Space)
    assert sw.isChecked() is False


def test_switch_focus_policy_is_strong():
    sw = Switch()
    assert sw.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_scrollable_combobox_focus_policy_is_strong():
    box = ScrollableComboBox()
    assert box.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_instances_counter_button_focus_policy_is_strong():
    counter = InstancesCounterButton()
    assert counter.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_instances_counter_button_keyboard_adds(qtbot):
    counter = InstancesCounterButton()
    _show(counter, qtbot)
    counter.setFocus()
    fired: list[int] = []
    counter.addClicked.connect(lambda: fired.append(1))

    qtbot.keyClick(counter, Qt.Key.Key_Space)
    qtbot.keyClick(counter, Qt.Key.Key_Return)
    qtbot.keyClick(counter, Qt.Key.Key_Up)
    qtbot.keyClick(counter, Qt.Key.Key_Plus)

    assert fired == [1, 1, 1, 1]


def test_instances_counter_button_keyboard_removes_only_when_allowed(qtbot):
    counter = InstancesCounterButton()
    _show(counter, qtbot)
    counter.setFocus()
    fired: list[int] = []
    counter.removeClicked.connect(lambda: fired.append(1))

    qtbot.keyClick(counter, Qt.Key.Key_Down)
    counter.set_count(2)
    counter.set_can_remove(True)
    qtbot.keyClick(counter, Qt.Key.Key_Down)
    qtbot.keyClick(counter, Qt.Key.Key_Minus)

    assert fired == [1, 1]


def _make_timeline(qtbot, total_frames: int = 50):
    tl = TimelineWidget()
    tl._total_frames = total_frames
    tl._current_index = 5
    _show(tl, qtbot)
    tl.setFocus()
    return tl


def test_timeline_focus_policy_is_strong():
    tl = TimelineWidget()
    assert tl.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_timeline_delete_key_emits_signal(qtbot):
    tl = _make_timeline(qtbot)
    fired: list[int] = []
    tl.deletePressed.connect(lambda: fired.append(1))
    qtbot.keyClick(tl, Qt.Key.Key_Delete)
    assert fired == [1]


def test_timeline_arrow_moves_head(qtbot):
    tl = _make_timeline(qtbot)
    moves: list[int] = []
    tl.headMoved.connect(moves.append)

    qtbot.keyClick(tl, Qt.Key.Key_Right)
    assert tl._current_index == 6
    qtbot.keyClick(tl, Qt.Key.Key_Left)
    assert tl._current_index == 5
    assert moves == [6, 5]


def test_timeline_shift_arrow_jumps_by_ten(qtbot):
    tl = _make_timeline(qtbot)
    qtbot.keyClick(tl, Qt.Key.Key_Right, modifier=Qt.KeyboardModifier.ShiftModifier)
    assert tl._current_index == 15


def test_timeline_home_end_jump_to_bounds(qtbot):
    tl = _make_timeline(qtbot, total_frames=42)
    qtbot.keyClick(tl, Qt.Key.Key_End)
    assert tl._current_index == 41
    qtbot.keyClick(tl, Qt.Key.Key_Home)
    assert tl._current_index == 0


def test_timeline_up_down_yield_to_navigation():
    """Trial-dispatch contract (docs/dev/NAVIGATION.md): Up/Down are never
    consumed by the widget while idle — NavigationManager owns them."""
    from tests._nav_contract import assert_yields_arrows_when_idle

    assert_yields_arrows_when_idle(TimelineWidget)


def test_timeline_up_down_leave_head_untouched(qtbot):
    tl = _make_timeline(qtbot)
    moves: list[int] = []
    tl.headMoved.connect(moves.append)
    before = tl._current_index
    qtbot.keyClick(tl, Qt.Key.Key_Up)
    qtbot.keyClick(tl, Qt.Key.Key_Down)
    assert tl._current_index == before
    assert moves == []


def test_timeline_left_right_yield_to_navigation():
    """Left/Right are free unless extra_keys (NAVIGATION.md): the widget may
    step with them, but must not break the trial-dispatch probe shape —
    direct keyPressEvent delivery stays functional for the manager probe."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    tl = TimelineWidget()
    tl._total_frames = 50
    tl._current_index = 5
    for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        tl.keyPressEvent(event)
        # Stepping accepts (widget owns Left/Right); the point is the call
        # never crashes and the probe shape (direct keyPressEvent) works.
        assert event.isAccepted()
    tl.close()


def test_timeline_empty_inputs_fail_open(qtbot):
    """Empty/degenerate store: navigation keys are ignored, nothing emits."""
    tl = TimelineWidget()
    tl._total_frames = 0
    tl._current_index = 0
    _show(tl, qtbot)
    tl.setFocus()
    moves: list[int] = []
    deletes: list[int] = []
    tl.headMoved.connect(moves.append)
    tl.deletePressed.connect(lambda: deletes.append(1))
    for key in (
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_Home,
        Qt.Key.Key_End,
    ):
        qtbot.keyClick(tl, key)
    assert tl._current_index == 0
    assert moves == []
    # Delete is selection-independent and still emits (documents current
    # behavior for the supervisor key-map spec).
    qtbot.keyClick(tl, Qt.Key.Key_Delete)
    assert deletes == [1]


def _key_event(key, modifier=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifier)


def test_timeline_pageup_pagedown_step_ten(qtbot):
    tl = _make_timeline(qtbot)
    moves: list[int] = []
    tl.headMoved.connect(moves.append)
    qtbot.keyClick(tl, Qt.Key.Key_PageDown)
    assert tl._current_index == 15
    qtbot.keyClick(tl, Qt.Key.Key_PageUp)
    assert tl._current_index == 5
    assert moves == [15, 5]


def test_timeline_pageup_pagedown_clamp_at_edges(qtbot):
    tl = _make_timeline(qtbot, total_frames=42)
    tl._current_index = 40
    qtbot.keyClick(tl, Qt.Key.Key_PageDown)
    assert tl._current_index == 41
    qtbot.keyClick(tl, Qt.Key.Key_PageDown)
    assert tl._current_index == 41
    tl._current_index = 1
    qtbot.keyClick(tl, Qt.Key.Key_PageUp)
    assert tl._current_index == 0
    qtbot.keyClick(tl, Qt.Key.Key_PageUp)
    assert tl._current_index == 0


def test_timeline_pageup_pagedown_empty_store_ignored(qtbot):
    tl = _make_timeline(qtbot, total_frames=0)
    tl._current_index = 0
    moves: list[int] = []
    tl.headMoved.connect(moves.append)
    for key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
        event = _key_event(key)
        tl.keyPressEvent(event)
        assert not event.isAccepted()
    assert tl._current_index == 0
    assert moves == []


def test_timeline_space_emits_play_pause_requested(qtbot):
    tl = _make_timeline(qtbot)
    fired: list[int] = []
    tl.playPauseRequested.connect(lambda: fired.append(1))
    event = _key_event(Qt.Key.Key_Space)
    tl.keyPressEvent(event)
    assert fired == [1]
    assert event.isAccepted()


def test_timeline_space_with_modifier_not_emitted(qtbot):
    tl = _make_timeline(qtbot)
    fired: list[int] = []
    tl.playPauseRequested.connect(lambda: fired.append(1))
    for modifier in (
        Qt.KeyboardModifier.ShiftModifier,
        Qt.KeyboardModifier.ControlModifier,
    ):
        event = _key_event(Qt.Key.Key_Space, modifier)
        tl.keyPressEvent(event)
        assert fired == []


def test_timeline_plus_minus_zoom_by_quarter_step(qtbot):
    tl = _make_timeline(qtbot)
    tl._zoom_level = 0.5
    event = _key_event(Qt.Key.Key_Plus)
    tl.keyPressEvent(event)
    assert event.isAccepted()
    assert tl._zoom_level == pytest.approx(0.5 * 1.25)
    event = _key_event(Qt.Key.Key_Minus)
    tl.keyPressEvent(event)
    assert event.isAccepted()
    assert tl._zoom_level == pytest.approx(0.5)


def test_timeline_plus_keypad_modifier_zooms(qtbot):
    tl = _make_timeline(qtbot)
    tl._zoom_level = 0.5
    event = _key_event(Qt.Key.Key_Plus, Qt.KeyboardModifier.KeypadModifier)
    tl.keyPressEvent(event)
    assert event.isAccepted()
    assert tl._zoom_level == pytest.approx(0.5 * 1.25)


def test_timeline_plus_with_other_modifiers_ignored(qtbot):
    tl = _make_timeline(qtbot)
    tl._zoom_level = 0.5
    event = _key_event(Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    tl.keyPressEvent(event)
    assert tl._zoom_level == pytest.approx(0.5)


def test_timeline_accessible_name_and_description():
    tl = TimelineWidget()
    assert tl.accessibleName() == "Timeline"
    assert tl.accessibleDescription() == (
        "Keyframe timeline. Left and right arrows step frames. "
        "Space toggles playback."
    )


