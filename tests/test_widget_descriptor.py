"""Pin WidgetDescriptor.from_inspect_spec legacy adapter."""
from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor, WidgetRegistry
def _sample_spec():
    return InspectSpec(family="TestLegacyWidget", config=(SpecField(label="value", source="value"),), config_exclude=("internal",), state=(SpecField(label="enabled", source="isEnabled"),), token_family=("Button",), regions=True, layers=False, docs="docs/user/BUTTON_API.md", preview_seed=lambda preview, live: None, apply_config_refresh=lambda live, names: None)
def test_from_inspect_spec_copies_all_fields():
    spec = _sample_spec()
    desc = WidgetDescriptor.from_inspect_spec(spec)
    assert desc.family == "TestLegacyWidget"
    assert desc.inspect is not None
    assert desc.inspect.config == spec.config
    assert desc.inspect.config_exclude == spec.config_exclude
    assert desc.inspect.state == spec.state
    assert desc.inspect.token_family == spec.token_family
    assert desc.inspect.regions is True
    assert desc.inspect.layers is False
    assert desc.inspect.docs == spec.docs
    assert desc.inspect.preview_seed is spec.preview_seed
    assert desc.inspect.apply_config_refresh is spec.apply_config_refresh
def test_from_inspect_spec_label_defaults_empty():
    spec = InspectSpec(family="LegacyNoLabel")
    desc = WidgetDescriptor.from_inspect_spec(spec)
    assert desc.label == ""
    assert desc.family == "LegacyNoLabel"
def test_registry_auto_converts_inspect_spec(qapp):
    from PySide6.QtWidgets import QWidget
    spec = InspectSpec(family="AutoConvertWidget", token_family=("Label",))
    class LegacyWidget(QWidget):
        inspect_spec = spec
    try:
        registry = WidgetRegistry.get_instance()
        registry._inspect_cache.pop(LegacyWidget, None)
        desc = registry.get_for_class(LegacyWidget)
        assert desc is not None
        assert desc.family == "AutoConvertWidget"
        assert desc.inspect is not None
        assert desc.inspect.token_family == ("Label",)
        desc2 = registry.get_for_class(LegacyWidget)
        assert desc2 is desc
    finally:
        WidgetRegistry.get_instance()._inspect_cache.pop(LegacyWidget, None)
def test_widget_descriptor_decorator_registers():
    from PySide6.QtWidgets import QWidget
    from sli_ui_toolkit.ui.widget_descriptor import widget_descriptor
    desc = WidgetDescriptor(family="DecoratorWidget")
    @widget_descriptor(desc)
    class Decorated(QWidget):
        pass
    try:
        reg = WidgetRegistry.get_instance()
        assert reg.get("DecoratorWidget") is desc
        assert reg.get_for_class(Decorated) is desc
        assert getattr(Decorated, "widget_descriptor") is desc
    finally:
        reg.unregister("DecoratorWidget")
