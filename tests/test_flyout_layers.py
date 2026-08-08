"""FlyoutManager layer stack (z-order) behavior."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import FlyoutManager, LayerStack
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout


def test_default_layer_stack_puts_context_menu_on_top():
    stack = LayerStack()
    assert stack.index_of("context_menu") > stack.index_of("base")
    assert stack.index_of("options") == stack.index_of(None)
    assert stack.index_of(None) == 0


def test_assign_group_rejects_unknown_layer():
    stack = LayerStack(order=("base", "popover"))
    try:
        stack.assign_group("options", "modal_hud")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown layer")


def test_ensure_overlay_stacking_raises_configured_layer_above_base(qapp):
    manager = FlyoutManager.get_instance()
    previous_stack = manager.layer_stack()
    try:
        stack = LayerStack(order=("base", "popover", "modal_hud"))
        stack.assign_group("hud", "modal_hud")
        manager.set_layer_stack(stack)

        host = QWidget()
        host.resize(400, 300)
        host.show()

        base_flyout = BaseFlyout(host)
        base_flyout.flyout_group = "options"
        base_flyout.setGeometry(10, 10, 100, 60)
        base_flyout.show()

        hud_flyout = BaseFlyout(host)
        hud_flyout.flyout_group = "hud"
        hud_flyout.setGeometry(10, 80, 100, 60)
        hud_flyout.show()

        # Simulate the base-layer flyout being raised afterward (e.g. by a
        # list refresh animation) — the hud flyout must stay on top.
        base_flyout.raise_()
        manager.ensure_overlay_stacking(raised=base_flyout)

        stack_order = host.children()
        assert stack_order.index(hud_flyout) > stack_order.index(base_flyout)

        base_flyout.deleteLater()
        hud_flyout.deleteLater()
        host.deleteLater()
    finally:
        manager.set_layer_stack(previous_stack)


def test_same_layer_stacking_follows_registration_order_not_set_hash_order():
    """``_registered_flyouts`` is a plain set -- without an explicit
    tie-break, two flyouts sharing a non-base layer would stack in
    whatever arbitrary order set iteration happens to produce instead of
    open order."""
    manager = FlyoutManager.get_instance()
    previous_stack = manager.layer_stack()
    try:
        stack = LayerStack(order=("base", "modal_hud"))
        stack.assign_group("hud", "modal_hud")
        manager.set_layer_stack(stack)

        host = QWidget()
        host.resize(400, 300)
        host.show()

        # Register enough same-layer flyouts that relying on set iteration
        # order would very likely show a mismatch if the tie-break were
        # missing (identity hash order has no relation to insertion order).
        huds = []
        for i in range(8):
            hud = BaseFlyout(host)
            hud.flyout_group = "hud"
            hud.setGeometry(10, 10 + i * 20, 100, 18)
            hud.show()
            huds.append(hud)

        manager.ensure_overlay_stacking()

        stack_order = host.children()
        indices = [stack_order.index(hud) for hud in huds]
        assert indices == sorted(indices), (
            "same-layer flyouts must stack in registration (open) order"
        )

        for hud in huds:
            hud.deleteLater()
        host.deleteLater()
    finally:
        manager.set_layer_stack(previous_stack)


def test_set_layer_stack_none_restores_default():
    manager = FlyoutManager.get_instance()
    previous_stack = manager.layer_stack()
    try:
        manager.set_layer_stack(LayerStack(order=("base", "popover")))
        manager.set_layer_stack(None)
        assert manager.layer_stack().index_of("context_menu") > manager.layer_stack().index_of("base")
    finally:
        manager.set_layer_stack(previous_stack)
