"""Modal navigation sections: while an overlay is up, keys and focus stay inside.

A section may declare ``modal = True`` via the optional protocol member.
While such a section is registered and its (QWidget) owner is visible, the
manager must guarantee that keyboard input and focus never leave it:

* a declined arrow at the section's edge is consumed, not handed to the
  neighbouring section and not bubbled to the tab behind the veil;
* Tab/Backtab cycle inside the owner's focus ring (with wrap), and are always
  consumed;
* a foreign widget stealing focus is pulled back inside the ceiling;
* sections registered *after* the modal section sit above it and keep normal
  behaviour (e.g. a flyout opened from inside the overlay);
* a section without the attribute is treated as non-modal.

These cases are written against real ``Button``s driven through the manager's
``eventFilter`` (the ``test_nav_click_realign_single_press`` idiom), so they
exercise the same code path a live key press does.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.widgets import Button


class _RowsSection:
    """Minimal section over a list of real buttons.

    Up/Down step between the buttons and decline past an edge, so the
    manager's own neighbour-handoff path is the one under test.
    """

    def __init__(self, owner, buttons, *, extra_keys=(), focus_first_target=None):
        self._owner = owner
        self._buttons = list(buttons)
        self._extra = frozenset(extra_keys)
        self._focus_first_target = focus_first_target
        self.navigate_calls: list[int] = []
        self.focus_first_calls = 0
        self.focus_last_calls = 0

    def owns(self, widget) -> bool:
        return widget in self._buttons

    def navigate(self, key, widget) -> bool:
        self.navigate_calls.append(key)
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
        self.focus_first_calls += 1
        target = self._focus_first_target
        if target is None:
            target = self._buttons[0] if self._buttons else None
        if target is None:
            return False
        target.setFocus(reason)
        return True

    def focus_last(self, ref_x=None, *, reason) -> bool:
        self.focus_last_calls += 1
        if not self._buttons:
            return False
        self._buttons[-1].setFocus(reason)
        return True

    @property
    def extra_keys(self):
        return self._extra


class _ModalRowsSection(_RowsSection):
    @property
    def modal(self) -> bool:
        return True


class _PlainRowsSection(_RowsSection):
    """No ``modal`` attribute at all — the ``getattr`` default must apply."""


def _window(qapp, *columns):
    """A shown window with one vertical column per ``(tag, n_buttons)``."""
    host = QWidget()
    host.resize(600, 400)
    layout = QHBoxLayout(host)
    owners = []
    all_buttons = []
    for tag, count in columns:
        col = QWidget(host)
        col_layout = QVBoxLayout(col)
        buttons = []
        for i in range(count):
            button = Button(text=f"{tag}{i}", size=(80, 30))
            col_layout.addWidget(button)
            buttons.append(button)
        layout.addWidget(col)
        owners.append(col)
        all_buttons.append(buttons)
    host.show()
    QApplication.setActiveWindow(host)
    qapp.processEvents()
    return host, owners, all_buttons


def _key(manager, widget, key) -> bool:
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    return manager.eventFilter(widget, event)


def _focus(widget, qapp):
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is widget


def test_down_at_modal_edge_does_not_hand_off(qapp, navigation_manager_reset):
    """Down on the modal section's last row is consumed — no neighbour handoff."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("behind", 1), ("a", 2), ("above", 2))
    behind = _RowsSection(owners[0], buttons[0])
    modal = _ModalRowsSection(owners[1], buttons[1])
    above = _RowsSection(owners[2], buttons[2])
    mgr.register(owners[0], behind)
    mgr.register(owners[1], modal)
    mgr.register(owners[2], above)
    try:
        _focus(buttons[1][-1], qapp)
        assert _key(mgr, buttons[1][-1], Qt.Key.Key_Down) is True
        assert QApplication.focusWidget() is buttons[1][-1]
        assert above.navigate_calls == []
        assert above.focus_first_calls == 0
    finally:
        host.deleteLater()


def test_arrow_on_behind_widget_reclaims_into_modal(qapp, navigation_manager_reset):
    """A widget of a section *behind* the ceiling is not navigable while modal."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("behind", 2), ("a", 2))
    behind = _RowsSection(owners[0], buttons[0])
    modal = _ModalRowsSection(owners[1], buttons[1])
    mgr.register(owners[0], behind)
    mgr.register(owners[1], modal)
    try:
        _focus(buttons[0][0], qapp)
        assert _key(mgr, buttons[0][0], Qt.Key.Key_Down) is True
        assert modal.focus_first_calls == 1
        assert QApplication.focusWidget() is buttons[1][0]
        assert behind.navigate_calls == []
    finally:
        host.deleteLater()


def test_tab_and_backtab_cycle_inside_modal_owner(qapp, navigation_manager_reset):
    """Tab/Backtab stay in the owner subtree and wrap; both are consumed."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("a", 3))
    modal = _ModalRowsSection(owners[0], buttons[0])
    mgr.register(owners[0], modal)
    try:
        _focus(buttons[0][0], qapp)
        assert _key(mgr, buttons[0][0], Qt.Key.Key_Tab) is True
        assert QApplication.focusWidget() is buttons[0][1]
        assert _key(mgr, buttons[0][1], Qt.Key.Key_Tab) is True
        assert QApplication.focusWidget() is buttons[0][2]
        # Wrap forward.
        assert _key(mgr, buttons[0][2], Qt.Key.Key_Tab) is True
        assert QApplication.focusWidget() is buttons[0][0]
        # Wrap backward.
        assert _key(mgr, buttons[0][0], Qt.Key.Key_Backtab) is True
        assert QApplication.focusWidget() is buttons[0][2]
    finally:
        host.deleteLater()


def test_empty_tab_ring_falls_back_to_focus_first(qapp, navigation_manager_reset):
    """No tab-focusable descendant -> focus_first, and Tab is still consumed."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("a", 0))
    sentinel = Button(text="sentinel", size=(80, 30))
    host.layout().addWidget(sentinel)
    qapp.processEvents()
    modal = _ModalRowsSection(owners[0], buttons[0], focus_first_target=sentinel)
    mgr.register(owners[0], modal)
    try:
        assert _key(mgr, owners[0], Qt.Key.Key_Tab) is True
        assert modal.focus_first_calls == 1
        assert QApplication.focusWidget() is sentinel
    finally:
        host.deleteLater()


def test_arrow_decline_consumes_left_right_too(qapp, navigation_manager_reset):
    """All four arrows are consumed at a modal edge, not only Up/Down."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("a", 2))
    modal = _ModalRowsSection(owners[0], buttons[0])
    mgr.register(owners[0], modal)
    try:
        _focus(buttons[0][0], qapp)
        assert _key(mgr, buttons[0][0], Qt.Key.Key_Left) is True
        assert QApplication.focusWidget() is buttons[0][0]
        assert _key(mgr, buttons[0][0], Qt.Key.Key_Right) is True
        assert QApplication.focusWidget() is buttons[0][0]
    finally:
        host.deleteLater()


def test_non_arrow_extra_key_stays_native_inside_modal(qapp, navigation_manager_reset):
    """Esc-like extra keys are still offered to native handling inside the veil."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("a", 2))
    modal = _ModalRowsSection(
        owners[0], buttons[0], extra_keys={Qt.Key.Key_Escape}
    )
    mgr.register(owners[0], modal)
    try:
        _focus(buttons[0][0], qapp)
        # navigate() declines Escape, and it is not an arrow: yield to native
        # (returns False here because no realign happened — the key is not
        # forcibly consumed).
        assert _key(mgr, buttons[0][0], Qt.Key.Key_Escape) is False
        assert modal.navigate_calls == [Qt.Key.Key_Escape]
    finally:
        host.deleteLater()


def test_focus_in_reclaim_and_other_window_exempt(
    qapp, navigation_manager_reset, qtbot
):
    """A foreign FocusIn is reclaimed; a widget of another window is not."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("behind", 2), ("a", 2))
    behind = _RowsSection(owners[0], buttons[0])
    modal = _ModalRowsSection(owners[1], buttons[1])
    mgr.register(owners[0], behind)
    mgr.register(owners[1], modal)
    try:
        _focus(buttons[1][0], qapp)
        # A widget behind the ceiling grabs focus -> pulled back next tick.
        buttons[0][1].setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()
        assert QApplication.focusWidget() is buttons[1][0]

        # A widget in a different top-level window is exempt.
        other = QWidget()
        other.resize(200, 200)
        qtbot.addWidget(other)
        other_layout = QVBoxLayout(other)
        other_button = Button(text="other", size=(80, 30))
        other_layout.addWidget(other_button)
        other.show()
        QApplication.setActiveWindow(other)
        qapp.processEvents()
        other_button.setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()
        assert QApplication.focusWidget() is other_button
    finally:
        host.deleteLater()


def test_section_above_ceiling_behaves_normally(qapp, navigation_manager_reset):
    """A section registered after the modal one keeps normal navigation."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("a", 2), ("c", 2))
    modal = _ModalRowsSection(owners[0], buttons[0])
    above = _RowsSection(owners[1], buttons[1])
    mgr.register(owners[0], modal)
    mgr.register(owners[1], above)
    try:
        _focus(buttons[1][0], qapp)
        assert _key(mgr, buttons[1][0], Qt.Key.Key_Down) is True
        assert QApplication.focusWidget() is buttons[1][1]
        assert above.navigate_calls == [Qt.Key.Key_Down]
        assert modal.focus_first_calls == 0
    finally:
        host.deleteLater()


def test_hidden_modal_owner_turns_modality_off(qapp, navigation_manager_reset):
    """Hiding the owner disables the ceiling: no reclaim, handoff works again."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("behind", 2), ("a", 2), ("above", 2))
    behind = _RowsSection(owners[0], buttons[0])
    modal = _ModalRowsSection(owners[1], buttons[1])
    above = _RowsSection(owners[2], buttons[2])
    mgr.register(owners[0], behind)
    mgr.register(owners[1], modal)
    mgr.register(owners[2], above)
    try:
        _focus(buttons[1][-1], qapp)
        assert _key(mgr, buttons[1][-1], Qt.Key.Key_Down) is True
        assert mgr._modal_ceiling() is not None

        owners[1].hide()
        qapp.processEvents()
        assert mgr._modal_ceiling() is None

        # No reclaim while the ceiling is gone.
        _focus(buttons[0][0], qapp)
        assert QApplication.focusWidget() is buttons[0][0]

        # Neighbour handoff is back: Down from behind's last row skips the
        # hidden modal column and lands in the section above it.
        _focus(buttons[0][-1], qapp)
        assert _key(mgr, buttons[0][-1], Qt.Key.Key_Down) is True
        assert QApplication.focusWidget() is buttons[2][0]
        assert above.focus_first_calls == 1
    finally:
        host.deleteLater()


def test_section_without_modal_attribute_is_non_modal(
    qapp, navigation_manager_reset
):
    """Missing ``modal`` -> ``getattr`` default False, no ceiling."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("plain", 2), ("above", 2))
    plain = _PlainRowsSection(owners[0], buttons[0])
    above = _RowsSection(owners[1], buttons[1])
    mgr.register(owners[0], plain)
    mgr.register(owners[1], above)
    try:
        assert mgr._modal_ceiling() is None
        _focus(buttons[0][-1], qapp)
        assert _key(mgr, buttons[0][-1], Qt.Key.Key_Down) is True
        assert QApplication.focusWidget() is buttons[1][0]
        assert above.focus_first_calls == 1
    finally:
        host.deleteLater()


def test_modal_reclaim_flag_does_not_leak(qapp, navigation_manager_reset):
    """The deferred-reclaim guard resets when the ceiling owner unregisters."""
    mgr = navigation_manager_reset
    host, owners, buttons = _window(qapp, ("behind", 2), ("a", 2))
    modal = _ModalRowsSection(owners[1], buttons[1])
    mgr.register(owners[0], _RowsSection(owners[0], buttons[0]))
    mgr.register(owners[1], modal)
    try:
        # Arm a reclaim (focus lands behind the ceiling).
        buttons[0][0].setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()
        mgr.unregister(owners[1])
        assert mgr._modal_reclaim_pending is False
    finally:
        host.deleteLater()
