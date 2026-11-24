"""Widget-level trial-dispatch contract: Up/Down must stay unaccepted while
idle so ``NavigationManager``/``ToolbarRowsSection`` can route them (see
``docs/dev/NAVIGATION.md`` and ``tests/_nav_contract.py``).

``SpinBox``/``DoubleSpinBox`` broke this silently before this test existed
(unconditional ``event.accept()`` on Up/Down); ``Stepper``/``TimeLineEdit``
then repeated it in subclasses. The cases below are **derived** from
``tests/value_controls_allowlist.py`` — the registries the AST gate in
``test_value_control_edit_contract.py`` forces every value control into — so a
new value control is covered here the moment it registers its shape, instead of
waiting for someone to remember this module.
"""

from __future__ import annotations

import pytest

from sli_ui_toolkit.widgets import ComboBox

from tests._nav_contract import assert_yields_arrows_when_idle
from tests.value_controls_allowlist import KEYBOARD_STEP_CONTROLS, VALUE_CONTROLS


def test_combo_box_yields_arrows_when_idle(qapp):
    """Not a value control: Up/Down are consumed only while the list is open."""
    assert_yields_arrows_when_idle(ComboBox)


@pytest.mark.parametrize("control_id", sorted(VALUE_CONTROLS))
def test_edit_mode_value_control_yields_arrows_when_idle(qapp, control_id):
    """Shape (a): arrows adjust only inside Enter's edit mode."""
    assert_yields_arrows_when_idle(VALUE_CONTROLS[control_id].factory)


@pytest.mark.parametrize("control_id", sorted(KEYBOARD_STEP_CONTROLS))
def test_typed_field_value_control_yields_arrows_when_idle(qapp, control_id):
    """Shape (b): PageUp/PageDown step; idle Up/Down belong to navigation."""
    assert_yields_arrows_when_idle(KEYBOARD_STEP_CONTROLS[control_id].factory)


@pytest.mark.parametrize("control_id", sorted(VALUE_CONTROLS))
def test_edit_mode_value_control_yields_left_right_when_idle(qapp, control_id):
    """Left/Right are navigation keys while a value control is not editing.

    ``assert_yields_arrows_when_idle`` only probes Up/Down. ``Slider`` used to
    accept Left/Right unconditionally, so a focused slider in a row ate the
    navigation keys (see ``docs/dev/NAVIGATION.md`` §1). It must leave them
    unaccepted until Enter enters edit mode. Typed-field controls are exempt:
    there Left/Right are caret movement, which is their declared behaviour.
    """
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    for key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
        widget = VALUE_CONTROLS[control_id].factory()
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        widget.keyPressEvent(event)
        assert not event.isAccepted(), (
            f"{control_id} accepted {key!r} while idle -- arrows must stay "
            "available for ring navigation until Enter enters edit mode"
        )
