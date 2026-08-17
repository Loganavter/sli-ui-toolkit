"""Inspector registry + family extractors (Button, Label, inputs)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector import (
    inspect_widget,
    register_family,
    registered_families,
)
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    ComboBox,
    Label,
    ScrollableComboBox,
    Slider,
    Switch,
    VerticalSplit,
)


def test_generic_fallback_on_plain_qwidget(qapp):
    widget = QWidget()
    inspection = inspect_widget(widget)
    assert inspection.family == "QWidget"
    names = {f.name for f in inspection.state}
    assert {"geometry", "visible", "enabled", "mro"} <= names


def test_button_family_regions_layers_and_config(qapp):
    button = Button(
        regions=[
            ButtonRegion(id="cover", weight=1.0),
            ButtonRegion(id="text", weight=2.0),
        ],
        split=VerticalSplit(),
        variant="surface",
    )
    inspection = inspect_widget(button)
    assert inspection.family == "Button"
    assert [r.id for r in inspection.regions] == ["cover", "text"]
    assert all(r.rect is not None for r in inspection.regions)
    layer_names = [l.name for l in inspection.layers]
    assert "BackgroundLayer" in layer_names
    assert "ContentLayer" in layer_names
    config_names = {f.name for f in inspection.config}
    assert "variant" in config_names
    assert inspection.token_family  # variant-derived static tokens


def test_button_states_and_private_markers(qapp):
    button = Button(text="x")
    inspection = inspect_widget(button)
    by_name = {f.name: f for f in inspection.state}
    assert by_name["checked"].value is False
    assert by_name["hovered"].value is False
    assert by_name["pressed"].value is False
    config = {f.name: f for f in inspection.config}
    assert config["variant"].value == "default"


def test_combo_box_matches_before_button(qapp):
    combo = ComboBox()
    combo.addItems(["a", "b"])
    inspection = inspect_widget(combo)
    assert inspection.family == "ComboBox"
    state = {f.name: f for f in inspection.state}
    assert state["current_index"].value == 0
    assert state["current_text"].value == "a"
    assert state["items"].value == ["a", "b"]


def test_scrollable_combo_box_family(qapp):
    from sli_ui_toolkit.widgets import ScrollableComboBox as SCB

    combo = SCB()
    inspection = inspect_widget(combo)
    assert inspection.family == "ScrollableComboBox"


def test_label_family(qapp):
    label = Label("Hello", pixel_size=14, variant="group-title")
    inspection = inspect_widget(label)
    assert inspection.family == "Label"
    config = {f.name: f for f in inspection.config}
    assert config["pixel_size"].value == 14
    state = {f.name: f for f in inspection.state}
    assert state["variant"].value == "group-title"
    assert inspection.token_family == ("dialog.text",)


def test_switch_family_private_state(qapp):
    switch = Switch()
    inspection = inspect_widget(switch)
    assert inspection.family == "Switch"
    state = {f.name: f for f in inspection.state}
    assert "checked" in state
    assert "progress" in state
    assert state["progress"].private is True


def test_slider_family_config(qapp):
    slider = Slider(track_thickness=7)
    inspection = inspect_widget(slider)
    assert inspection.family == "Slider"
    config = {f.name: f for f in inspection.config}
    assert config["track_thickness"].value == 7
    assert "slider.track.unfilled" in inspection.token_family


def test_registered_families_ordered_specific_first(qapp):
    names = registered_families()
    assert "ComboBox" in names
    assert "Button" in names
    assert names.index("ComboBox") < names.index("Button")


def test_register_family_priority_overrides_default(qapp):
    """A widget WITHOUT a spec (duck-typed fallback path): priority>0 wins
    over the default-registered family. Spec'd widgets are unaffected — the
    spec is authoritative."""
    from sli_ui_toolkit.ui.inspector import registry as _registry
    from sli_ui_toolkit.ui.inspector.contract import WidgetInspection

    class _SpecLess(QWidget):
        pass

    widget = _SpecLess()
    assert inspect_widget(widget).family == "QWidget"

    def _match(w):
        return isinstance(w, _SpecLess)

    def _extract(w, tm=None):
        return WidgetInspection(family="CustomWidget")

    _registry.register_family("CustomWidget", _match, _extract, priority=1)
    try:
        assert inspect_widget(widget).family == "CustomWidget"
        # the default-priority registration comes later and loses
    finally:
        _registry._REGISTERED[:] = [
            entry
            for entry in _registry._REGISTERED
            if entry[0] != "CustomWidget"
        ]
        assert inspect_widget(widget).family == "QWidget"


def test_slider_config_kinds(qapp):
    from sli_ui_toolkit.ui.inspector.contract import FieldKind

    slider = Slider(track_thickness=7, show_value_fill=True)
    config = {f.name: f for f in inspect_widget(slider).config}
    assert config["track_thickness"].kind is FieldKind.NUMBER
    assert config["show_value_fill"].kind is FieldKind.BOOL


def test_default_variant_toggle_token_family(qapp):
    button = Button(text="x")  # default variant → button.toggle prefix
    tokens = inspect_widget(button).token_family
    assert "button.toggle.background.normal" in tokens
    assert "button.toggle.background.checked" in tokens


def test_region_states_reflect_checked(qapp):
    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

    button = Button(regions=[ButtonRegion(id="main")], toggle=True)
    button.setRegionChecked("main", True)
    inspection = inspect_widget(button)
    region = inspection.regions[0]
    assert ButtonState.CHECKED in region.states
