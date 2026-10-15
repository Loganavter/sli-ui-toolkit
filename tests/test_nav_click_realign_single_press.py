"""One arrow press after a mouse click must re-anchor AND navigate.

A click kills the visible focus ring (``NavigationManager``'s
``MouseButtonPress`` handling), so the next arrow press re-anchors the ring
onto the widget nearest the click point before stepping. That press used to be
consumed as "reveal-only": it revealed the ring and did nothing else, so moving
one step after any click took two presses — and when the realign target was a
section's own container (the gallery's empty-zone click anchors on the scroll
area) the revealed ring was not even on a navigable item, so the first press
looked completely dead.

``ClickRealignCoordinator``'s docstring has always described the intended
behaviour: the press "re-anchors the ring ... then lets that same key press
navigate from there". These cases pin that.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.widgets import Button


class _ButtonRowSection:
    """Minimal section: owns a row of buttons, steps focus by index."""

    def __init__(self, buttons: list[Button]) -> None:
        self._buttons = buttons

    def owns(self, widget) -> bool:
        return widget in self._buttons

    def navigate(self, key, widget) -> bool:
        if widget not in self._buttons:
            return False
        i = self._buttons.index(widget)
        if key == Qt.Key.Key_Down:
            target = i + 1
        elif key == Qt.Key.Key_Up:
            target = i - 1
        else:
            return False
        if not 0 <= target < len(self._buttons):
            return False
        self._buttons[target].setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def focus_first(self, ref_x=None, *, reason) -> bool:
        self._buttons[0].setFocus(reason)
        return True

    def focus_last(self, ref_x=None, *, reason) -> bool:
        self._buttons[-1].setFocus(reason)
        return True

    @property
    def extra_keys(self):
        return frozenset()


def _build(qapp):
    """A shown window with a vertical row of three buttons; returns host, row."""
    host = QWidget()
    host.resize(240, 300)
    layout = QVBoxLayout(host)
    buttons = [Button(text=f"b{i}", size=(80, 30)) for i in range(3)]
    for b in buttons:
        layout.addWidget(b)
    host.show()
    QApplication.setActiveWindow(host)
    qapp.processEvents()
    return host, buttons


def _click(manager, host, widget) -> None:
    """Drive a MouseButtonPress through the manager, as a real click would."""
    centre = widget.mapToGlobal(widget.rect().center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPoint(centre.x(), centre.y()),
        QPoint(centre.x(), centre.y()),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    manager.eventFilter(host, event)
    assert manager._realign.realign_pending is True, "click did not arm a realign"


def _arrow(manager, widget, key) -> bool:
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    return manager.eventFilter(widget, event)


def test_one_press_after_click_navigates(qapp):
    """The classic case: click a button, press Down once -> next button."""
    host, buttons = _build(qapp)
    nav_manager = NavigationManager.get_instance()
    nav_manager.register(host, _ButtonRowSection(buttons))
    try:
        assert buttons[0].setFocus(Qt.FocusReason.OtherFocusReason) is None
        qapp.processEvents()
        assert QApplication.focusWidget() is buttons[0]

        _click(nav_manager, host, buttons[0])

        assert _arrow(nav_manager, buttons[0], Qt.Key.Key_Down) is True
        assert QApplication.focusWidget() is buttons[1], (
            "one arrow press after a click did not move focus (reveal-only regression)"
        )

        # The ring is revealed by that same press, not a wasted second one.
        assert nav_manager.last_input_was_keyboard() is True
        assert getattr(buttons[1], "_keyboard_focus", False) is True
    finally:
        nav_manager.unregister(host)
        host.deleteLater()


def test_one_press_after_click_into_non_item_area(qapp):
    """Click in dead space, one press -> focus lands on a real item.

    Mirrors the gallery empty-zone click, where the realign target is the
    section's own container rather than a button.
    """
    host, buttons = _build(qapp)
    # A section-unowned child, so the click does not land on a button and the
    # realign has to pick the nearest one instead.
    gap = QWidget(host)
    gap.setFixedHeight(20)
    host.layout().insertWidget(1, gap)
    qapp.processEvents()

    nav_manager = NavigationManager.get_instance()
    nav_manager.register(host, _ButtonRowSection(buttons))
    try:
        assert buttons[0].setFocus(Qt.FocusReason.OtherFocusReason) is None
        qapp.processEvents()

        _click(nav_manager, host, gap)
        before = QApplication.focusWidget()

        assert _arrow(nav_manager, before or buttons[0], Qt.Key.Key_Down) is True
        assert QApplication.focusWidget() in buttons, (
            "one press after a click in dead space left focus off the items"
        )
    finally:
        nav_manager.unregister(host)
        host.deleteLater()
