"""FlyoutManager.link/unlink -- flyout family cascades."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import FlyoutManager, GroupShowPolicy
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout


def test_hiding_parent_cascades_to_linked_child(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        parent = BaseFlyout(host)
        parent.flyout_group = "options"
        parent.setGeometry(10, 10, 100, 60)
        parent.show()

        child = BaseFlyout(host)
        child.flyout_group = "pickers"
        child.setGeometry(10, 80, 100, 60)
        child.show()

        manager.link(parent, child)
        assert manager.linked_children(parent) == (child,)

        parent.hide()
        assert not parent.isVisible()
        assert not child.isVisible()

        parent.deleteLater()
        child.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_group_dismiss_of_parent_cascades_to_child(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        policy = GroupShowPolicy()
        manager.set_show_policy(policy)

        host = QWidget()
        host.resize(400, 300)
        host.show()

        parent = BaseFlyout(host)
        parent.flyout_group = "options"
        parent.setGeometry(10, 10, 100, 60)
        parent.show()

        child = BaseFlyout(host)
        child.flyout_group = "pickers"
        child.setGeometry(10, 80, 100, 60)
        child.show()
        manager.link(parent, child)

        other = BaseFlyout(host)
        other.flyout_group = "unified_list"
        other.setGeometry(200, 10, 100, 60)
        other.show()

        assert not parent.isVisible()
        assert not child.isVisible()
        assert other.isVisible()

        other.deleteLater()
        parent.deleteLater()
        child.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


class _FakeFlyout:
    """Minimal ManagedFlyout stand-in -- hashable by identity, unlike SimpleNamespace."""

    def isVisible(self) -> bool:
        return True

    def hide(self) -> None:
        pass


def test_unlink_stops_cascade():
    manager = FlyoutManager.get_instance()

    parent = _FakeFlyout()
    child = _FakeFlyout()

    manager.link(parent, child)
    assert manager.linked_children(parent) == (child,)
    manager.unlink(parent, child)
    assert manager.linked_children(parent) == ()


def test_unregister_flyout_cleans_up_links():
    manager = FlyoutManager.get_instance()

    parent = _FakeFlyout()
    child = _FakeFlyout()

    manager.link(parent, child)
    manager.unregister_flyout(parent)
    assert manager.linked_children(parent) == ()


def test_click_inside_linked_child_does_not_trigger_outside_dismiss(qapp):
    """A click inside a linked child must not read as "outside the family".

    ``FlyoutManager`` doesn't union parent+child geometry explicitly -- it
    relies on every registered *visible* flyout (not just the active one)
    being checked in ``_contains_global``. Since ``BaseFlyout`` always
    self-registers (see its ``__init__``), a linked ``BaseFlyout`` child
    gets this protection automatically. This test locks that guarantee in
    as a regression test rather than leaving it an unverified assumption.
    """
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        # A submenu/color-picker-style child must not dismiss its own
        # parent when it opens -- use coexists_with rather than the
        # default ExclusiveShowPolicy (which would hide parent the moment
        # child.show() runs, before we even get to the click test).
        policy = GroupShowPolicy()
        policy.coexists_with("options", "pickers")
        manager.set_show_policy(policy)

        host = QWidget()
        host.resize(400, 300)
        host.show()

        parent = BaseFlyout(host)
        parent.flyout_group = "options"
        parent.setGeometry(10, 10, 100, 60)
        parent.show()

        child = BaseFlyout(host)
        child.flyout_group = "pickers"
        child.setGeometry(200, 200, 100, 60)  # far from parent's own bounds
        child.show()
        manager.link(parent, child)

        assert parent.isVisible()
        assert child.isVisible()

        child_center = child.mapToGlobal(child.rect().center())
        assert not parent.contains_global(child_center)

        dismissed = manager.close_if_outside(child_center)

        assert dismissed is False
        assert parent.isVisible()
        assert child.isVisible()

        parent.deleteLater()
        child.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_reposition_children_calls_child_reposition_when_parent_reshown(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        anchor = QWidget(host)
        anchor.setGeometry(10, 10, 80, 32)
        anchor.show()

        parent = BaseFlyout(host, pinned=True)
        parent.show_aligned(anchor, "bottom-left", "top-left")

        calls: list[int] = []

        class _Child:
            def isVisible(self):
                return True

            def hide(self):
                pass

            def reposition(self):
                calls.append(1)

        child = _Child()
        manager.link(parent, child)

        # Simulate the host's resize hook calling reposition() on the pinned HUD.
        # show_aligned() re-enters request_show via both its own explicit call
        # and BaseFlyout.show()'s override, so the child may reposition more
        # than once per call -- what matters is that it happens at all.
        parent.reposition()
        assert calls

        parent.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)
