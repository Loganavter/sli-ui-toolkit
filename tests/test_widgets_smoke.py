from __future__ import annotations

import pytest

from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    Button,
    CheckBox,
    ComboBox,
    CustomLineEdit,
    Label,
    RadioButton,
    SimpleUnifiedFlyoutController,
    SimpleUnifiedFlyoutStore,
    Slider,
    SpinBox,
    Switch,
    UnifiedFlyout,
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


def test_unified_flyout_instantiates(qapp):
    store = SimpleUnifiedFlyoutStore()
    controller = SimpleUnifiedFlyoutController(store)
    host = QWidget()
    flyout = UnifiedFlyout(store=store, main_controller=controller, main_window=host)
    assert flyout is not None
    flyout.deleteLater()
    host.deleteLater()

