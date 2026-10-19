"""Hiding a flyout must not steal focus from another flyout.

Regression (Improve-ImgSLI magnifier group, 2026-10-19): a ScrollValueButton's
value pill is entered with Up; the anchor's FocusOut hides a sibling panel that
was shown on focus; that panel's ``_finish_hide → _restore_focus_policies`` then
``setFocus``-ed the anchor back, cancelling the entry — the keyboard ended on the
ButtonGroup and Up looked dead, for every button in the group (but not for
buttons whose focus does not open a sibling flyout).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import BaseFlyout


def _setup(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    anchor = QWidget()
    anchor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    layout.addWidget(anchor)
    qtbot.addWidget(host)
    host.show()
    hider = BaseFlyout(host)
    entering = BaseFlyout(host)
    # Mirror the value pill: a grab_focus=False preview (no focus guard), so
    # the buggy restore really does yank focus instead of being bounced back
    # by the entering flyout's own guard.
    entering.show_aligned(
        anchor,
        "bottom-center",
        "top-center",
        offset=5,
        grab_focus=False,
        register_nav_section=True,
    )
    qtbot.waitExposed(host)
    return host, anchor, hider, entering


def test_hide_does_not_steal_focus_from_another_flyout(qapp, qtbot):
    _host, anchor, hider, entering = _setup(qtbot)
    # A flyout that hid because focus moved into another flyout: its restore
    # target is the anchor (the trigger), like a focus-shown panel.
    hider._anchor_widget = anchor
    hider._previous_focus_widget = anchor

    anchor.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    entering.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is entering

    hider._restore_focus_policies()
    qapp.processEvents()

    assert QApplication.focusWidget() is entering, (
        "hiding a flyout must not yank the keyboard back from the flyout "
        "navigation just entered"
    )


def test_restore_still_returns_focus_to_the_anchor(qapp, qtbot):
    """The guard must stay narrow: focus that left to a non-flyout still
    comes back to the anchor (outside click / Escape paths)."""
    host, anchor, hider, entering = _setup(qtbot)
    hider._anchor_widget = anchor
    hider._previous_focus_widget = anchor
    entering.hide()
    entering.deleteLater()
    qapp.processEvents()

    anchor.clearFocus()
    qapp.processEvents()

    hider._restore_focus_policies()
    qapp.processEvents()

    assert QApplication.focusWidget() is anchor
