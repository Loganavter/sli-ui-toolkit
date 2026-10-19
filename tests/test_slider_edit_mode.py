"""A value changes only after an explicit Enter — the value-edit contract.

Owner request 2026-10-19 (colour-picker navigation now works): navigating must
never adjust a value. Arrows move the ring (Up/Down rows, Left/Right inside a
row); **Enter on a value control enters edit mode** (a visible affordance is
mandatory); in edit mode arrows (and W/A/S/D) adjust; Enter again commits; Esc
reverts to the value captured when edit mode was entered.

Before this, ``ToolbarRowsSection``/``AutoNavigationSection`` trial-dispatched
arrows to whatever was focused and the flyout's ``_FlyoutNavigationSection``
gave ``Slider`` unconditional Left/Right first refusal, so a focused slider ate
the navigation keys (``ui/widgets/atomic/slider.py`` used to accept Left/Right
unconditionally).

The tests drive REAL widgets through real keys: a section path
(``ToolbarRowsSection``) for "arrows navigate, value untouched", a standalone
slider for the edit-mode state machine, and a flyout for the first-refusal gate.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
from sli_ui_toolkit.widgets import BaseFlyout, Slider


class _Focusable(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class _AcceptingWidget(QWidget):
    """A non-value control: accepts Left without any edit-mode contract."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hits = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.hits += 1
        event.accept()


def _two_row_host(qtbot):
    """host → row1 (a container holding ``top``), row2 (``neighbor`` + slider).

    Rows are containers (``ToolbarRowsSection._focusable`` reads a row's
    children, not the row itself), so geometry is deterministic and
    ``_focusable``'s x-sort orders ``neighbor`` before ``slider`` inside row 2.
    """
    host = QWidget()
    host.resize(400, 200)
    qtbot.addWidget(host)

    row1 = QWidget(host)
    row1.setGeometry(10, 10, 120, 30)
    top = _Focusable("top", row1)
    top.setGeometry(0, 0, 120, 30)

    row2 = QWidget(host)
    row2.setGeometry(10, 60, 320, 40)
    neighbor = _Focusable("neighbor", row2)
    neighbor.setGeometry(0, 5, 80, 30)
    slider = Slider(Qt.Orientation.Horizontal, row2)
    slider.setGeometry(120, 5, 160, 30)
    slider.setRange(0, 100)
    slider.setValue(50)
    slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    host.show()
    qtbot.waitExposed(host)
    section = ToolbarRowsSection(lambda: [row1, row2], tag="edit-mode-test")
    NavigationManager.get_instance().register(host, section)
    return host, top, row2, neighbor, slider


def _focus(widget: QWidget) -> None:
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()


def _press(widget: QWidget, key) -> None:
    QTest.keyClick(widget, key)
    QApplication.processEvents()


def _render(widget: QWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    return image


def _diff_in_band(a: QImage, b: QImage) -> int:
    """Differing pixels in the central horizontal band (the track/thumb area)."""
    band_top = a.height() // 3
    band_bottom = (2 * a.height()) // 3
    count = 0
    for y in range(band_top, band_bottom):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                count += 1
    return count


# ---------------------------------------------------------------------------
# (a) navigating never adjusts a focused value control
# ---------------------------------------------------------------------------

def test_arrows_move_the_ring_and_never_change_a_focused_slider(qapp, qtbot):
    host, top, row2, neighbor, slider = _two_row_host(qtbot)
    base = slider.value()

    _focus(slider)
    assert QApplication.focusWidget() is slider

    # Left/Right stay navigation: the ring steps inside the row.
    _press(slider, Qt.Key.Key_Left)
    assert QApplication.focusWidget() is neighbor, "Left must move the ring, not the value"
    assert slider.value() == base, "navigating with Left changed the slider value"

    _press(neighbor, Qt.Key.Key_Right)
    assert QApplication.focusWidget() is slider
    assert slider.value() == base, "navigating with Right changed the slider value"

    # Up/Down stay navigation: the ring steps rows.
    _press(slider, Qt.Key.Key_Up)
    assert QApplication.focusWidget() is top, "Up must move the ring, not the value"
    assert slider.value() == base, "navigating with Up changed the slider value"


# ---------------------------------------------------------------------------
# (b) Enter enters edit mode, arrows/WASD adjust, Enter commits
# ---------------------------------------------------------------------------

def test_enter_edits_arrows_and_wasd_adjust_and_enter_commits(qapp, qtbot):
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    slider.show()
    qtbot.addWidget(slider)
    _focus(slider)

    assert slider.is_editing() is False
    base = slider.value()

    _press(slider, Qt.Key.Key_Return)
    assert slider.is_editing() is True, "Enter on a value control must enter edit mode"

    _press(slider, Qt.Key.Key_Right)
    assert slider.value() > base, "Right in edit mode must raise the value"
    after_right = slider.value()

    _press(slider, Qt.Key.Key_D)
    assert slider.value() > after_right, "D in edit mode must raise the value"
    after_d = slider.value()

    _press(slider, Qt.Key.Key_Left)
    assert slider.value() < after_d, "Left in edit mode must lower the value"
    after_left = slider.value()

    _press(slider, Qt.Key.Key_A)
    assert slider.value() < after_left, "A in edit mode must lower the value"

    # Up/Down adjust too once editing (they are navigation keys while idle).
    before_up = slider.value()
    _press(slider, Qt.Key.Key_Up)
    assert slider.value() > before_up, "Up in edit mode must raise the value"
    before_down = slider.value()
    _press(slider, Qt.Key.Key_Down)
    assert slider.value() < before_down, "Down in edit mode must lower the value"
    committed = slider.value()

    _press(slider, Qt.Key.Key_Return)
    assert slider.is_editing() is False, "Enter again must leave edit mode"
    assert slider.value() == committed, "committing must keep the adjusted value"


# ---------------------------------------------------------------------------
# (c) Esc reverts to the value captured on entry
# ---------------------------------------------------------------------------

def test_escape_reverts_to_the_entry_value(qapp, qtbot):
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    slider.show()
    qtbot.addWidget(slider)
    _focus(slider)

    entry = slider.value()
    _press(slider, Qt.Key.Key_Return)
    assert slider.is_editing() is True
    for _ in range(3):
        _press(slider, Qt.Key.Key_Right)
    assert slider.value() != entry, "test setup: the value must have moved"

    _press(slider, Qt.Key.Key_Escape)
    assert slider.is_editing() is False, "Esc must leave edit mode"
    assert slider.value() == entry, "Esc must revert to the value captured on entry"


# ---------------------------------------------------------------------------
# (d) the editing affordance changes the render
# ---------------------------------------------------------------------------

def test_editing_paints_a_distinct_affordance(qapp, qtbot):
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    slider.show()
    qtbot.addWidget(slider)
    _focus(slider)
    slider._keyboard_focus = False
    QApplication.processEvents()

    idle = _render(slider)
    _press(slider, Qt.Key.Key_Return)
    assert slider.is_editing() is True
    editing = _render(slider)

    assert idle != editing, (
        "an editing slider renders identically to an idle one — the owner cannot "
        "tell 'the ring is on this slider' from 'this slider is being edited'"
    )
    assert _diff_in_band(idle, editing) > 0, (
        "the editing affordance must live on the track/thumb band"
    )


# ---------------------------------------------------------------------------
# (e) a control without the edit-mode contract keeps today's behaviour
# ---------------------------------------------------------------------------

def test_control_without_the_edit_contract_still_receives_arrows(qapp, qtbot):
    # Imported lazily so a missing gate helper fails THIS test, not collection.
    from sli_ui_toolkit.ui.managers.navigation_sections import (
        arrow_gate_open,
        value_control_is_editing,
    )

    plain = _AcceptingWidget()
    assert arrow_gate_open(plain) is True, "no is_editing() → arrows reach the widget"
    assert value_control_is_editing(plain) is False

    idle_slider = Slider(Qt.Orientation.Horizontal)
    try:
        assert arrow_gate_open(idle_slider) is False, (
            "a not-editing value control must keep arrows for ring navigation"
        )
        assert value_control_is_editing(idle_slider) is False
        idle_slider._editing = True
        assert arrow_gate_open(idle_slider) is True
        assert value_control_is_editing(idle_slider) is True
    finally:
        idle_slider.deleteLater()

    # Through a real section: the plain accepting control still gets its key
    # (the section does not steal it for ring navigation).
    host = QWidget()
    host.resize(400, 200)
    qtbot.addWidget(host)
    row = QWidget(host)
    row.setGeometry(10, 10, 320, 40)
    plain = _AcceptingWidget(row)
    plain.setGeometry(0, 5, 120, 30)
    other = _Focusable("other", row)
    other.setGeometry(160, 5, 120, 30)
    host.show()
    qtbot.waitExposed(host)
    NavigationManager.get_instance().register(
        host, ToolbarRowsSection(lambda: [row], tag="no-contract-test")
    )
    _focus(plain)
    _press(plain, Qt.Key.Key_Right)
    assert plain.hits >= 1, "a control without is_editing() must still receive arrows"
    assert QApplication.focusWidget() is plain, "the section must not steal the key"


# ---------------------------------------------------------------------------
# flyout path: the unconditional first-refusal is gated on edit mode
# ---------------------------------------------------------------------------

def _flyout_with_slider(qtbot):
    host = QWidget()
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    anchor = _Focusable("anchor", host)
    anchor.setGeometry(10, 10, 80, 24)
    NavigationManager.get_instance().register(
        host, ToolbarRowsSection(lambda: [anchor], tag="anchor-row")
    )

    flyout = BaseFlyout(host)
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    flyout.add_row("Opacity", slider)
    flyout.show_aligned(anchor, "top-left", "top-left", grab_focus=False)
    QApplication.processEvents()
    return host, flyout, slider


def test_flyout_gates_value_arrows_on_edit_mode(qapp, qtbot):
    host, flyout, slider = _flyout_with_slider(qtbot)
    _focus(slider)
    assert QApplication.focusWidget() is slider
    base = slider.value()

    # Not editing: Left/Right must NOT be eaten by the slider.
    _press(slider, Qt.Key.Key_Right)
    assert slider.value() == base, "the flyout handed Right to a non-editing slider"

    # Enter enters edit mode through the flyout's first-refusal path, then the
    # arrows adjust the value (including Up/Down, which navigate otherwise).
    _press(slider, Qt.Key.Key_Return)
    assert slider.is_editing() is True, "Enter through the flyout must enter edit mode"
    _press(slider, Qt.Key.Key_Right)
    assert slider.value() > base, "Right in flyout edit mode must raise the value"
    raised = slider.value()
    _press(slider, Qt.Key.Key_Up)
    assert slider.value() > raised, "Up in flyout edit mode must raise the value"
    committed = slider.value()

    _press(slider, Qt.Key.Key_Return)
    assert slider.is_editing() is False
    assert slider.value() == committed
    assert QApplication.focusWidget() is slider, "editing must not move the ring away"
