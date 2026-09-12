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


def test_spinbox_yields_arrows_when_idle(qapp):
    assert_yields_arrows_when_idle(SpinBox)


def test_double_spinbox_yields_arrows_when_idle(qapp):
    assert_yields_arrows_when_idle(DoubleSpinBox)
