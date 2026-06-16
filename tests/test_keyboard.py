from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    Button,
    InstancesCounterButton,
    ScrollableComboBox,
    SimpleUnifiedFlyoutController,
    SimpleUnifiedFlyoutStore,
    Switch,
    TimelineWidget,
    UnifiedFlyout,
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


def test_flyout_closes_on_escape(qtbot):
    host = QWidget()
    host.resize(400, 300)
    _show(host, qtbot)

    store = SimpleUnifiedFlyoutStore()
    controller = SimpleUnifiedFlyoutController(store)
    flyout = UnifiedFlyout(store=store, main_controller=controller, main_window=host)
    flyout.show()
    qtbot.waitExposed(flyout)
    flyout.setFocus()
    assert flyout.isVisible()

    qtbot.keyClick(flyout, Qt.Key.Key_Escape)
    assert not flyout.isVisible()
