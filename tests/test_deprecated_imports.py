from __future__ import annotations

import importlib
import sys
import warnings

import pytest


def _fresh_import(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_public_widget_import_does_not_warn_for_internal_shims():
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        importlib.import_module("sli_ui_toolkit.widgets")

    assert not [
        warning for warning in recorded
        if "atomic.combobox" in str(warning.message)
    ]


def test_deprecation_registry_formats_replacement_context():
    from sli_ui_toolkit.deprecations import BUTTON_COMPAT_DEPRECATIONS

    message = BUTTON_COMPAT_DEPRECATIONS["ToolButton"].message()

    assert "ToolButton is deprecated since 0.2.11" in message
    assert "will be removed in 0.3.0" in message
    assert "Use the composable Button class instead" in message
    assert "CHANGELOG.md section 0.2.11" in message


def test_legacy_atomic_combobox_import_warns():
    with pytest.warns(DeprecationWarning, match="atomic.combobox is deprecated"):
        module = _fresh_import("sli_ui_toolkit.ui.widgets.atomic.combobox")

    assert hasattr(module, "ComboBox")


def test_legacy_atomic_scrollable_combobox_import_warns():
    with pytest.warns(DeprecationWarning, match="atomic.comboboxes is deprecated"):
        module = _fresh_import("sli_ui_toolkit.ui.widgets.atomic.comboboxes")

    assert hasattr(module, "ScrollableComboBox")


def test_legacy_button_package_names_warn():
    from sli_ui_toolkit.ui.widgets import buttons

    with pytest.warns(DeprecationWarning, match="AutoRepeatButton is deprecated"):
        legacy_button = getattr(buttons, "AutoRepeatButton")
    with pytest.warns(DeprecationWarning, match="ButtonGroupContainer is deprecated"):
        legacy_group = getattr(buttons, "ButtonGroupContainer")
    with pytest.warns(DeprecationWarning, match="ButtonMode is deprecated"):
        legacy_mode = getattr(buttons, "ButtonMode")

    assert legacy_button is buttons.Button
    assert legacy_group is buttons.ButtonGroup
    assert legacy_mode is buttons.Button


def test_legacy_public_widget_button_names_warn():
    import sli_ui_toolkit.widgets as widgets

    with pytest.warns(
        DeprecationWarning,
        match="ToolButtonWithMenu is deprecated since 0.2.11",
    ):
        legacy_button = getattr(widgets, "ToolButtonWithMenu")

    assert legacy_button is widgets.Button


def test_unknown_public_widget_compat_name_points_to_changelog():
    import sli_ui_toolkit.widgets as widgets

    with pytest.raises(AttributeError, match="check CHANGELOG.md"):
        getattr(widgets, "DefinitelyRemovedWidget")


def test_legacy_button_instance_api_warns(qapp):
    from sli_ui_toolkit.widgets import Button

    button = Button(toggle=True)

    with pytest.warns(DeprecationWarning, match="Button.triggered is deprecated"):
        legacy_signal = button.triggered
    assert hasattr(legacy_signal, "connect")
    with pytest.warns(DeprecationWarning, match="emit_signal=.*deprecated"):
        button.setChecked(True, emit_signal=False)
    with pytest.warns(DeprecationWarning, match="variant 'primary' is deprecated"):
        button.setVariant("primary")

    assert button.getVariant() == "surface"
