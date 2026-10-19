"""A preview-mode flyout's rows must still be reachable by keyboard.

Regression (``plan-nav-coverage-2026-10-19`` / N3a): the host's
draw-background ``Switch`` sits in a flyout shown through the
``show_top_left_of`` → ``show_aligned`` path with ``grab_focus=False`` — a
settings panel that must not steal focus from the canvas. ``show_aligned``
derived its nav-registration default from ``grab_focus`` alone, so the panel
was never registered as a navigation section: arrow keys skipped over it
entirely and its rows were unreachable by keyboard, even though it holds a
real focusable control. "Do not grab focus" must not also mean "invisible to
the keyboard" once the flyout actually has navigable content.

The flow below drives real keys through the real ``NavigationManager``:
Down from the anchor's row hands off to the flyout's section (registered when
the flyout is shown), and Space toggles the focused ``Switch``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
from sli_ui_toolkit.widgets import BaseFlyout, Switch


def _host_with_anchor(qtbot):
    """A shown window with one navigable row holding the flyout's anchor."""
    host = QWidget()
    layout = QVBoxLayout(host)
    anchor_row = QWidget()
    row_layout = QVBoxLayout(anchor_row)
    anchor = QWidget()
    anchor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    row_layout.addWidget(anchor)
    layout.addWidget(anchor_row)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    return host, anchor_row, anchor


def test_switch_in_preview_flyout_is_owned_and_keyboard_reachable(qapp, qtbot):
    mgr = NavigationManager.get_instance()
    host, anchor_row, anchor = _host_with_anchor(qtbot)
    mgr.register(host, ToolbarRowsSection(lambda: [anchor_row], tag="anchor"))

    flyout = BaseFlyout(host)
    switch = Switch()
    flyout.add_row("Draw background", switch)
    # The host's show path: preview mode — no focus steal, and no explicit
    # ``register_nav_section`` (so the default decides).
    flyout.show_aligned(anchor, "top-left", "top-left", grab_focus=False)
    qapp.processEvents()

    row = switch.parentWidget()
    owning = [spec for _, spec in mgr._sections if spec.owns(switch)]
    assert owning, "the preview flyout's Switch is not owned by any nav section"
    assert any(spec.owns(row) for spec in owning), (
        "the row container must belong to the same section as its Switch"
    )

    # Down from the anchor's row yields at its boundary and the manager hands
    # the key to the flyout section registered above it.
    anchor.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    assert QApplication.focusWidget() is anchor

    QTest.keyClick(anchor, Qt.Key.Key_Down)
    qapp.processEvents()
    assert QApplication.focusWidget() is switch, (
        "Down from the anchor must enter the preview flyout and reach its Switch"
    )

    # Behaviour, not just focus: the key toggle must actually flip the state.
    before = switch.isChecked()
    QTest.keyClick(switch, Qt.Key.Key_Space)
    qapp.processEvents()
    assert switch.isChecked() is not before, "Space on the focused Switch must toggle it"
