"""Widget-level trial-dispatch contract: Up/Down must stay unaccepted while
idle so ``NavigationManager``/``ToolbarRowsSection`` can route them (see
``docs/dev/NAVIGATION.md`` and ``tests/_nav_contract.py``).

``SpinBox``/``DoubleSpinBox`` broke this silently before this test existed
(unconditional ``event.accept()`` on Up/Down) -- these cases guard against
a fourth widget doing the same.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.atomic.spinbox import DoubleSpinBox, SpinBox
from sli_ui_toolkit.widgets import ComboBox, Slider

from tests._nav_contract import assert_yields_arrows_when_idle


def test_combo_box_yields_arrows_when_idle(qapp):
    assert_yields_arrows_when_idle(ComboBox)


def test_slider_yields_arrows_when_idle(qapp):
    assert_yields_arrows_when_idle(Slider)


def test_slider_yields_left_right_when_idle(qapp):
    """Left/Right are navigation keys while a value control is not editing.

    ``assert_yields_arrows_when_idle`` only probes Up/Down. ``Slider`` used to
    accept Left/Right unconditionally, so a focused slider in a row ate the
    navigation keys (see ``docs/dev/NAVIGATION.md`` §1). It must leave them
    unaccepted until Enter enters edit mode.
    """
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
        widget = Slider()
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        widget.keyPressEvent(event)
        assert not event.isAccepted(), (
            "Slider accepted Left/Right while idle -- arrows must stay available "
            "for ring navigation until Enter enters edit mode"
        )



def test_spinbox_yields_arrows_when_idle(qapp):
    assert_yields_arrows_when_idle(SpinBox)


def test_double_spinbox_yields_arrows_when_idle(qapp):
    assert_yields_arrows_when_idle(DoubleSpinBox)
