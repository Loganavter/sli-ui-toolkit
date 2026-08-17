"""Inspector contract: dataclasses + kind detection + extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from sli_ui_toolkit.ui.inspector.contract import (
    FieldKind,
    InspectField,
    InspectLayer,
    InspectRegion,
    WidgetInspection,
)
from sli_ui_toolkit.ui.inspector.extract import (
    from_dataclass,
    from_getters,
    from_init_kwargs,
    from_qt_props,
    kind_of,
)


class _Mode(Enum):
    AUTO = "auto"
    MANUAL = "manual"


def test_inspect_field_kinds():
    assert kind_of(True) is FieldKind.BOOL
    assert kind_of(3) is FieldKind.NUMBER
    assert kind_of(0.5) is FieldKind.NUMBER
    assert kind_of(_Mode.AUTO) is FieldKind.ENUM
    assert kind_of(QColor("#ff0000")) is FieldKind.COLOR
    assert kind_of("#aabbcc") is FieldKind.COLOR
    assert kind_of("#aabbccff") is FieldKind.COLOR
    assert kind_of(QRectF(0, 0, 10, 10)) is FieldKind.RECT
    assert kind_of("plain") is FieldKind.TEXT


def test_contract_dataclasses_round_trip():
    field_ = InspectField(name="variant", value="surface", kind=FieldKind.ENUM)
    region = InspectRegion(id="main", rect=QRectF(0, 0, 100, 40), states=frozenset())
    layer = InspectLayer(name="BackgroundLayer", scope="region")
    inspection = WidgetInspection(
        family="Button",
        config=(field_,),
        state=(InspectField(name="checked", value=False, kind=FieldKind.BOOL),),
        token_family=("accent",),
        regions=(region,),
        layers=(layer,),
    )
    assert inspection.family == "Button"
    assert inspection.config[0].name == "variant"
    assert inspection.regions[0].rect == QRectF(0, 0, 100, 40)
    assert inspection.layers[0].name == "BackgroundLayer"


@dataclass
class _Shape:
    corner_radius: int = 6
    size: tuple = (36, 36)


def test_from_dataclass_dumps_config(qapp):
    fields = from_dataclass(_Shape(corner_radius=8))
    by_name = {f.name: f for f in fields}
    assert by_name["corner_radius"].value == 8
    assert by_name["corner_radius"].kind is FieldKind.NUMBER


def test_from_init_kwargs_reads_attrs_and_marks_private(qapp):
    from sli_ui_toolkit.widgets import Slider

    slider = Slider(track_thickness=7, thumb_radius=11)
    fields = {f.name: f for f in from_init_kwargs(slider)}
    assert fields["track_thickness"].value == 7
    assert fields["track_thickness"].private is True  # stored as _track_thickness
    assert fields["thumb_radius"].value == 11
    # parent and **kwargs are never inspection data
    assert "parent" not in fields


def test_from_init_kwargs_skips_bound_methods(qapp):
    from sli_ui_toolkit.widgets import Label

    label = Label("hello", pixel_size=14)
    fields = {f.name: f for f in from_init_kwargs(label)}
    # QLabel.text is a method — must not leak as a config field
    assert "text" not in fields
    assert fields["pixel_size"].value == 14
    assert fields["pixel_size"].private is True  # _pixel_size_override


def test_from_getters_string_and_callable_sources(qapp):
    from sli_ui_toolkit.widgets import Switch

    switch = Switch()
    switch.setChecked(True)
    fields = from_getters(
        switch,
        (
            ("checked", "isChecked"),
            ("hover", lambda w: getattr(w, "_hover", False)),
        ),
    )
    by_name = {f.name: f for f in fields}
    assert by_name["checked"].value is True
    # Switch._hover is a progress float, not a bool
    assert by_name["hover"].value == 0.0


def test_from_qt_props_dumps_dynamic_properties(qapp):
    from sli_ui_toolkit.widgets import Button

    button = Button(text="x")
    button.setProperty("custom_tag", "hello")
    names = {f.name for f in from_qt_props(button)}
    assert "custom_tag" in names
    assert "_ui_inspector_owned" not in names


def test_inspect_field_block_kind_for_nested_fields():
    inner = InspectField(name="a", value=1, kind=FieldKind.NUMBER)
    outer = InspectField(name="rows", value=(inner,), kind=FieldKind.BLOCK)
    assert outer.kind is FieldKind.BLOCK


def test_inspect_field_survives_copy():
    import copy

    original = InspectField(name="checked", value=True, kind=FieldKind.BOOL)
    cloned = copy.copy(original)
    assert cloned == original
    assert cloned is not original

    inspection = WidgetInspection(
        family="Button",
        config=(original,),
        regions=(InspectRegion(id="a", rect=QRectF(0, 0, 4, 4)),),
    )
    assert copy.deepcopy(inspection) == inspection


def test_from_dataclass_dumps_real_shape_spec(qapp):
    from sli_ui_toolkit.ui.widgets.buttons.specs import ShapeSpec

    spec = ShapeSpec(corner_radius=10, size=(48, 48), icon_size=24)
    fields = {f.name: f for f in from_dataclass(spec)}
    assert fields["corner_radius"].value == 10
    assert fields["corner_radius"].kind is FieldKind.NUMBER
    assert fields["icon_size"].value == 24
