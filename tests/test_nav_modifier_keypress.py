"""A bare modifier KeyPress must not flip the keyboard-focus modality.

Falsification (pre-fix): the app-wide ``NavigationManager`` event filter set
``_last_input_keyboard = True`` on ANY ``KeyPress``, including a bare
Ctrl/Shift/Alt. Holding Ctrl to move the window or take a screenshot therefore
flipped the modality, so the next programmatic focus grant (window activation /
post-move restore) picked ``OtherFocusReason`` and flashed the focus ring on the
first/last widget. Only real keys should flip it.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager


def _press(key, mods=Qt.KeyboardModifier.NoModifier) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, mods)


def test_bare_modifier_does_not_enable_keyboard_ring(qtbot) -> None:
    m = NavigationManager.get_instance()
    m._last_input_keyboard = False
    m.eventFilter(QObject(), _press(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier))
    assert m.last_input_was_keyboard() is False
    m.eventFilter(QObject(), _press(Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier))
    assert m.last_input_was_keyboard() is False
    m.eventFilter(QObject(), _press(Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier))
    assert m.last_input_was_keyboard() is False


def test_real_key_enables_keyboard_ring(qtbot) -> None:
    m = NavigationManager.get_instance()
    m._last_input_keyboard = False
    m.eventFilter(QObject(), _press(Qt.Key.Key_Down))
    assert m.last_input_was_keyboard() is True
