"""Inspection specs: widgets self-describe via an ``inspect_spec`` class
attribute; the inspector reads it with no matching/order."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector import inspect_widget
from sli_ui_toolkit.ui.inspector.contract import FieldKind
from sli_ui_toolkit.ui.inspector.spec import (
    InspectSpec,
    SpecField,
    build_inspection,
    spec_of,
)
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    ComboBox,
    Label,
    ScrollableComboBox,
    Slider,
    Switch,
)


def test_spec_of_reads_class_attribute(qapp):
    assert spec_of(Switch()) is not None
    assert spec_of(Label("x")).family == "Label"


def test_spec_inherited_by_subclass(qapp):
    class _MySlider(Slider):
        pass

    slider = _MySlider()
    spec = spec_of(slider)
    assert spec is not None
    assert spec.family == "Slider"


def test_spec_controls_family_and_state(qapp):
    switch = Switch()
    switch.setChecked(True)
    inspection = inspect_widget(switch)
    assert inspection.family == "Switch"
    state = {f.name: f for f in inspection.state}
    assert state["checked"].value is True
    assert state["progress"].private is True  # _progress is a private attr
    assert "switch.knob.on" in inspection.token_family


def test_spec_callable_source_transforms_value(qapp):
    combo = ComboBox()
    combo.addItems(["a", "b"])
    inspection = inspect_widget(combo)
    state = {f.name: f for f in inspection.state}
    assert state["items"].value == ["a", "b"]
    assert state["current_index"].value == 0


def test_spec_regions_and_layers_for_button(qapp):
    button = Button(regions=[ButtonRegion(id="main", weight=3.0)])
    inspection = inspect_widget(button)
    assert inspection.family == "Button"
    assert [r.id for r in inspection.regions] == ["main"]
    assert inspection.regions[0].weight == 3.0
    assert any(l.name == "BackgroundLayer" for l in inspection.layers)


def test_build_inspection_honors_config_include_list(qapp):
    slider = Slider(track_thickness=9)
    spec = InspectSpec(
        family="Probe",
        config=(SpecField("track_thickness"),),
        state=(SpecField("value", "value"),),
    )
    inspection = build_inspection(slider, spec)
    assert inspection.family == "Probe"
    assert inspection.config[0].name == "track_thickness"
    assert inspection.config[0].value == 9
    assert inspection.config[0].kind is FieldKind.NUMBER
    assert inspection.state[0].value == slider.value()


def test_config_field_kind_inferred(qapp):
    slider = Slider(show_value_fill=True)
    inspection = inspect_widget(slider)
    config = {f.name: f for f in inspection.config}
    assert config["show_value_fill"].kind is FieldKind.BOOL
    assert config["track_thickness"].kind is FieldKind.NUMBER


def test_config_derives_through_args_kwargs_forwarding_wrapper(qapp):
    class _WrapperSlider(Slider):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("track_thickness", 9)
            super().__init__(*args, **kwargs)

    slider = _WrapperSlider()
    inspection = inspect_widget(slider)
    config = {f.name: f for f in inspection.config}
    assert config["track_thickness"].value == 9
    assert config["track_thickness"].kind is FieldKind.NUMBER
