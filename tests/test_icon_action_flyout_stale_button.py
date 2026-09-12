"""Stale action-button regression for ``IconActionFlyout``.

A host signal connection (e.g. a store ``state_changed`` observer) can keep
the flyout's Python wrapper alive past its buttons' C++ deletion (parent
teardown, or ``set_actions`` ``deleteLater`` processed by the event loop).
``set_action_state`` / ``_on_scale_changed`` / the ``set_actions`` cleanup
loop must self-heal via ``sip.isValid`` instead of crashing with
``RuntimeError: Internal C++ object (Button) already deleted``.

Regression for: ``magnifier_color_controls.py`` ``_on_store_state_changed``
→ ``update_state`` → ``set_action_state`` (``icon_action_flyout.py``).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import IconAction, IconActionFlyout


def test_set_action_state_self_heals_deleted_button(qtbot, qapp):
    """A freed button kept in ``_buttons`` must be purged, not touched."""
    host = QWidget()
    host.resize(400, 300)
    host.show()
    qtbot.addWidget(host)
    flyout = IconActionFlyout(host)
    flyout.set_actions([IconAction("a", "copy", "Copy")])

    stale = flyout.action_button("a")
    assert stale is not None
    stale.deleteLater()
    qtbot.wait(20)  # process the deletion: the C++ Button is gone now,
    # but flyout._buttons["a"] still holds the wrapper -- exactly the state
    # a host that kept the flyout's Python wrapper alive would be in.

    flyout.set_action_state("a", visible=False)  # must not raise

    assert "a" not in flyout._buttons
    assert "a" not in flyout._actions

    # The flyout keeps working with fresh actions.
    flyout.set_actions([IconAction("b", "copy", "Copy")])
    assert flyout.action_button("b") is not None
    flyout.set_action_state("b", visible=True)


def test_scale_changed_skips_deleted_button(qtbot, qapp):
    """UiScale can also fire on a wrapper kept alive past deletion."""
    host = QWidget()
    host.resize(400, 300)
    host.show()
    qtbot.addWidget(host)
    flyout = IconActionFlyout(host)
    flyout.set_actions([IconAction("a", "copy", "Copy")])

    stale = flyout.action_button("a")
    stale.deleteLater()
    qtbot.wait(20)

    flyout._on_scale_changed(1.5)  # must not raise, must purge

    assert "a" not in flyout._buttons
    assert "a" not in flyout._actions