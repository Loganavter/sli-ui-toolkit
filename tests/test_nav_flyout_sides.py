"""Per-side flyout links + group-level ownership (``NavigationManager``).

Regression (Improve-ImgSLI magnifier group, 2026-10-19): the old single-slot
``_extensions_below`` kept ONE extension per anchor, so a value pill linked
*above* a button and a settings panel linked *below* the same button silently
overwrote each other — even though ``bind_flyout`` advertises four sides and a
host comment explicitly assumed the above-link survives. Sections also had to
re-derive the direction from ``flyout_side`` after a single ambiguous lookup.

The registry is now per ``(anchor, side)`` with a group-level variant
(``link_group`` / ``bind_group_flyout``) so one registration serves every
focusable member of a button group.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager


def _group_button(qtbot):
    """A shown window with a group container holding one focusable button."""
    win = QWidget()
    group = QWidget(win)
    layout = QHBoxLayout(group)
    button = QWidget(group)
    layout.addWidget(button)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win, group, button


def test_links_keep_both_sides(qapp, qtbot):
    mgr = NavigationManager.get_instance()
    win, _group, button = _group_button(qtbot)
    above, below = QWidget(win), QWidget(win)
    above.show()
    below.show()

    mgr.link(button, above, "above")
    mgr.link(button, below, "below")

    assert mgr.extension_for(button, "above") is above
    assert mgr.extension_for(button, "below") is below
    # Legacy single lookup still resolves, preferring "below".
    assert mgr.extension_below(button) is below

    mgr.unlink(button, "above")
    assert mgr.extension_for(button, "above") is None
    assert mgr.extension_for(button, "below") is below


def test_link_below_keeps_legacy_contract(qapp, qtbot):
    mgr = NavigationManager.get_instance()
    win, _group, button = _group_button(qtbot)
    flyout = QWidget(win)
    flyout.show()

    mgr.link_below(button, flyout)

    assert mgr.extension_for(button, "below") is flyout
    assert mgr.extension_below(button) is flyout
    assert mgr.flyout_side(flyout) == "below"

    mgr.unlink_below(button)
    assert mgr.extension_for(button, "below") is None


def test_group_flyout_serves_every_member(qapp, qtbot):
    mgr = NavigationManager.get_instance()
    win, group, button = _group_button(qtbot)
    panel = QWidget(win)
    panel.show()

    mgr.link_group(group, panel, "below")

    assert mgr.extension_for(button, "below") is panel
    # The reverse lookup names the member the user entered from, so the
    # panel's own Up/Down exit can hand focus back to the exact button.
    assert mgr.extension_owner(panel) is button


def test_group_link_does_not_shadow_owner_side(qapp, qtbot):
    """A member's own per-side link wins over the group link on the same side."""
    mgr = NavigationManager.get_instance()
    win, group, button = _group_button(qtbot)
    panel = QWidget(win)
    pill = QWidget(win)
    panel.show()
    pill.show()

    mgr.link_group(group, panel, "below")
    mgr.link(button, pill, "below")

    assert mgr.extension_for(button, "below") is pill

    mgr.unlink(button, "below")
    assert mgr.extension_for(button, "below") is panel


def test_flyout_up_hands_back_to_the_row_above(qapp, qtbot):
    """Up out of an above-linked flyout continues from the anchor's own row.

    Registration order is meaningless for a flyout (its section is appended
    when shown), so the plain neighbour hop landed on the toolbar section's
    ``focus_last`` — Up out of a value pill jumped to the window's BOTTOM row.
    """
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

    from sli_ui_toolkit.managers import bind_flyout
    from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
    from sli_ui_toolkit.widgets import BaseFlyout

    host = QWidget()
    layout = QVBoxLayout(host)
    row_above = QWidget()
    above_layout = QVBoxLayout(row_above)
    top_button = QWidget()
    top_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    above_layout.addWidget(top_button)
    row_anchor = QWidget()
    anchor_layout = QVBoxLayout(row_anchor)
    anchor = QWidget()
    anchor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    anchor_layout.addWidget(anchor)
    layout.addWidget(row_above)
    layout.addWidget(row_anchor)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    mgr = NavigationManager.get_instance()
    mgr.register(host, ToolbarRowsSection(lambda: [row_above, row_anchor], tag="two-rows"))

    flyout = BaseFlyout(host)
    bind_flyout(anchor, flyout, side="above")
    flyout.show_aligned(
        anchor, "top-center", "bottom-center", offset=4,
        grab_focus=False, register_nav_section=True,
    )
    qtbot.wait(10)
    # Emulate Up entering the pill: the section resolves (and stamps) the link.
    assert mgr.extension_for(anchor, "above") is flyout
    flyout.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is flyout

    QApplication.sendEvent(
        flyout,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier),
    )
    qapp.processEvents()

    assert QApplication.focusWidget() is top_button, (
        "Up out of the pill must land in the row ABOVE the anchor"
    )


def test_hidden_flyout_is_not_returned(qapp, qtbot):
    mgr = NavigationManager.get_instance()
    win, group, button = _group_button(qtbot)
    panel = QWidget(win)  # registered but never shown

    mgr.link_group(group, panel, "below")

    assert mgr.extension_for(button, "below") is None


def test_destroyed_flyout_is_forgotten(qapp, qtbot):
    import shiboken6

    mgr = NavigationManager.get_instance()
    win, _group, button = _group_button(qtbot)
    flyout = QWidget(win)
    flyout.show()
    mgr.link(button, flyout, "above")

    shiboken6.delete(flyout)

    assert mgr.extension_for(button, "above") is None
    assert mgr.extension_below(button) is None
