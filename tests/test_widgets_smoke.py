from __future__ import annotations

import pytest

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    Button,
    CheckBox,
    ComboBox,
    CustomLineEdit,
    Label,
    RadioButton,
    Slider,
    SpinBox,
    Switch,
)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Button(text="Click"),
        lambda: CheckBox("Check"),
        lambda: ComboBox(),
        lambda: CustomLineEdit(),
        lambda: Label("Hello"),
        lambda: RadioButton("Radio"),
        lambda: Slider(),
        lambda: SpinBox(),
        lambda: Switch(),
    ],
)
def test_widget_instantiates(qapp, factory):
    widget = factory()
    assert widget is not None
    widget.deleteLater()



