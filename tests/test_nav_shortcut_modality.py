"""A QShortcut activation is keyboard input — it must flip the ring modality.

Falsification (pre-fix, measured live 2026-10-22): ``QShortcutMap`` resolves a
chord inside ``QApplication::notify``'s prologue, so the ``KeyPress`` never
reaches ``NavigationManager.eventFilter``; only the resulting
``QShortcutEvent`` is delivered. After a mouse click the modality stayed
``False``, and a surface opened by ``ctrl+F1`` came up with no focus ring — the
same window opened from the menu carried a ring it should not have had.

The app-wide filter therefore has to treat ``QEvent.Type.Shortcut`` as the
keyboard signal, in the same way ``KeyPress`` is treated.

Scope note: the *chord resolution* half cannot be exercised offscreen — the
offscreen platform never runs ``QShortcutMap`` (probed 2026-10-22: neither
``QTest.keyClick`` nor a hand-built ``QShortcutEvent`` activates a
``QShortcut`` there). These tests pin the filter contract; the real chord path
is proven live through the MCP runbook (mouse click → ``ctrl+F1`` →
``ui_nav_state.modality``), recorded in
``inv-help-focus-ring-mouse-open-2026-10-22``.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager


def _shortcut_event(portable: str = "Ctrl+F1"):
    from PySide6.QtGui import QShortcutEvent

    return QShortcutEvent(QKeySequence(portable), 0)


def test_shortcut_event_enables_keyboard_ring(qtbot) -> None:
    m = NavigationManager.get_instance()
    m._last_input_keyboard = False
    m.eventFilter(QObject(), _shortcut_event())
    assert m.last_input_was_keyboard() is True


def test_shortcut_event_is_not_consumed(qtbot) -> None:
    """The filter only records the modality — the shortcut still fires."""
    m = NavigationManager.get_instance()
    m._last_input_keyboard = False
    assert m.eventFilter(QObject(), _shortcut_event()) is False


def test_shortcut_is_recorded_before_the_window_shortcut_chain(qtbot) -> None:
    """Ordering: the modality is already keyboard when the widget sees the event."""
    seen: list[bool] = []
    m = NavigationManager.get_instance()
    m._last_input_keyboard = False
    widget = QWidget()
    qtbot.addWidget(widget)

    class Watcher(QObject):
        def eventFilter(self, obj, event):  # noqa: N802
            if event.type() == QEvent.Type.Shortcut:
                seen.append(m.last_input_was_keyboard())
            return False

    watcher = Watcher()
    widget.installEventFilter(watcher)
    from PySide6.QtWidgets import QApplication

    m._install_event_filter()
    try:
        QApplication.sendEvent(widget, _shortcut_event())
    finally:
        m._uninstall_event_filter()
    assert seen == [True]
