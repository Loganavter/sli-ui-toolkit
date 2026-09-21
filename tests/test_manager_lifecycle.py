"""Task 2 (manager lifecycle) regression tests.

Covers: FlyoutManager destroyed-cleanup (active + link maps), recursive
request_hide depth, isVisible guards on stale flyouts, GroupShowPolicy
destroyed-hook for id-keyed rules, UiFont apply() dedupe + teardown
release, and NavigationManager host owns()/navigate() exception guards.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from sli_ui_toolkit.managers import FlyoutManager, GroupShowPolicy
from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.managers.ui_font import UiFont


@pytest.fixture()
def flyout_manager():
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    manager.set_show_policy(None)
    yield manager
    manager.set_show_policy(previous)
    manager.close_all()
    for flyout in list(manager._registered_flyouts):
        try:
            manager.unregister_flyout(flyout)
        except Exception:
            pass
    manager._active_flyout = None


@pytest.fixture()
def nav_manager(qapp):
    manager = NavigationManager.get_instance()
    yield manager
    for owner, _ in list(manager._sections):
        try:
            manager.unregister(owner)
        except Exception:
            pass
    qapp.processEvents()


# -- FlyoutManager destroyed-cleanup ---------------------------------------


def test_destroyed_flyout_clears_active_and_links(qapp, flyout_manager):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    parent = QWidget(host)
    parent.show()
    child = QWidget(host)
    child.show()

    flyout_manager.register_flyout(parent)
    flyout_manager.register_flyout(child)
    flyout_manager.link(parent, child)
    flyout_manager._active_flyout = parent
    assert flyout_manager.linked_children(parent) == (child,)

    # Deterministic C++ destruction (deleteLater needs a running loop).
    shiboken6.delete(parent)

    assert flyout_manager._active_flyout is None
    assert parent not in flyout_manager._registered_flyouts
    assert flyout_manager.linked_children(parent) == ()
    assert child not in flyout_manager._link_parent_of
    child.deleteLater()
    host.deleteLater()


def test_request_hide_recurses_to_grandchildren(qapp, flyout_manager):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    grandparent = QWidget(host)
    parent = QWidget(host)
    child = QWidget(host)
    for w in (grandparent, parent, child):
        w.show()
    qapp.processEvents()

    flyout_manager.link(grandparent, parent)
    flyout_manager.link(parent, child)
    flyout_manager.request_hide(grandparent)

    assert not parent.isVisible()
    assert not child.isVisible()
    for w in (grandparent, parent, child, host):
        w.deleteLater()


def test_stale_active_flyout_guards_isvisible(flyout_manager):
    class DeadFlyout:
        def isVisible(self):
            raise RuntimeError("wrapped C++ object has been deleted")

        def hide(self):
            raise RuntimeError("wrapped C++ object has been deleted")

    dead = DeadFlyout()
    flyout_manager._active_flyout = dead
    assert flyout_manager.is_flyout_active(dead) is False
    assert flyout_manager.get_active_flyout() is None
    # Guard unregisters the corpse instead of keeping a stale pointer.
    assert flyout_manager._active_flyout is None


# -- GroupShowPolicy destroyed-hook ----------------------------------------


def test_policy_rules_die_with_flyout(qapp):
    policy = GroupShowPolicy()
    widget = QWidget()
    widget.show()
    policy.configure_flyout(widget, dismisses=(), claim_active=False)
    assert policy.should_claim_active(widget, None) is False

    key = id(widget)
    assert key in policy._flyout_claim_active
    shiboken6.delete(widget)

    assert key not in policy._flyout_claim_active
    assert key not in policy._flyout_dismisses


# -- UiFont apply() dedupe + release ---------------------------------------


def test_uifont_apply_does_not_stack_resyncs(qapp, qtbot):
    fonts = UiFont.get_instance()
    label = QLabel("hello")
    qtbot.addWidget(label)
    fonts.apply(label)
    fonts.apply(label)
    fonts.apply(label)
    try:
        connections = fonts._apply_connections.get(label)
        assert connections is not None
        # One wiring only: font_changed + scale_changed, not 3 x 2.
        assert len(connections) == 2
        fonts._emit_changed()
        qapp.processEvents()
    finally:
        fonts._disconnect_apply(label)


def test_uifont_apply_releases_widget_on_teardown(qapp):
    fonts = UiFont.get_instance()
    label = QLabel("bye")
    label.show()
    fonts.apply(label)
    assert label in fonts._apply_connections
    shiboken6.delete(label)
    assert label not in fonts._apply_connections


# -- NavigationManager host guards -----------------------------------------


class _BombSection:
    """owns()/navigate() raise — the guard must contain the blast."""

    def __init__(self, bomb):
        self._bomb = bomb

    def owns(self, widget):
        if widget is self._bomb:
            raise RuntimeError("host owns() bug")
        return False

    def navigate(self, key, widget):
        raise RuntimeError("host navigate() bug")

    def focus_first(self, ref_x=None, *, reason):
        return False

    def focus_last(self, ref_x=None, *, reason):
        return False

    @property
    def extra_keys(self):
        return frozenset()


class _ClaimingBombSection(_BombSection):
    def owns(self, widget):
        if widget is self._bomb:
            return True
        return False


def _focused_bomb(qapp, owner):
    """Show owner + focused child, repo idiom (setActiveWindow for offscreen)."""
    bomb = QWidget(owner)
    bomb.resize(100, 50)
    bomb.show()
    QApplication.setActiveWindow(owner)
    bomb.setFocus()
    qapp.processEvents()
    assert QApplication.focusWidget() is bomb
    return bomb


def test_nav_filter_survives_raising_owns(qapp, nav_manager):
    owner = QWidget()
    owner.resize(200, 200)
    owner.show()
    bomb = _focused_bomb(qapp, owner)

    nav_manager.register(owner, _BombSection(bomb))
    try:
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
        )
        # Must not raise; no section owns the widget → yielded to native.
        assert nav_manager.eventFilter(owner, event) is False
    finally:
        nav_manager.unregister(owner)
    owner.deleteLater()


def test_nav_filter_survives_raising_navigate(qapp, nav_manager):
    owner = QWidget()
    owner.resize(200, 200)
    owner.show()
    bomb = _focused_bomb(qapp, owner)

    nav_manager.register(owner, _ClaimingBombSection(bomb))
    try:
        event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
        )
        # navigate() raises → treated as declined → consumed, no neighbor.
        assert nav_manager.eventFilter(owner, event) is True
    finally:
        nav_manager.unregister(owner)
    owner.deleteLater()
