"""``ControlRow``: the labelled control row both hosts were assembling by hand.

The row is surface, not behaviour: the hosted control keeps its own signals and
setters, and the row only arranges a title, the control, an optional caption
and an optional units suffix. These tests pin the two named orientations, the
text parts (including their absence), the live ``set_control`` swap that
releases the previous widget, real toolkit controls inside the row, and the
label column following ``UiScale`` exactly once per change.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.widgets import CheckBox, ComboBox, ControlRow, Slider, Text

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "sli_ui_toolkit"
    / "ui"
    / "widgets"
    / "composite"
    / "control_row.py"
)


@pytest.fixture(autouse=True)
def _appearance(qapp):
    """A registered palette and a known factor, restored after each test."""
    theme = ThemeManager.get_instance()
    theme.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    theme.set_theme("light", qapp, await_ripples=False)
    scale = UiScale.get_instance()
    original = scale.factor()
    scale.set_factor(1.0)
    qapp.processEvents()
    yield
    scale.set_factor(original)
    qapp.processEvents()


def _row(qtbot, control: QWidget | None = None, **kwargs) -> ControlRow:
    control = control if control is not None else CheckBox("Option", row=True)
    row = ControlRow(control, **kwargs)
    qtbot.addWidget(row)
    row.resize(320, 160)
    row.show()
    qtbot.waitExposed(row)
    return row


def _part(row: ControlRow, name: str) -> Text:
    widget = row.findChild(Text, name)
    assert widget is not None, f"ControlRow has no Text named {name!r}"
    return widget


def test_label_hint_and_units_are_present_and_visible(qtbot):
    row = _row(qtbot, label="Resolution", hint="Higher costs more time.", units="px")

    label = _part(row, "controlRowLabel")
    hint = _part(row, "controlRowHint")
    units = _part(row, "controlRowUnits")

    assert label.text() == "Resolution"
    assert hint.text() == "Higher costs more time."
    assert units.text() == "px"
    for part in (label, hint, units):
        assert part.isVisible()


def test_absent_parts_are_hidden_and_appear_when_set(qtbot):
    row = _row(qtbot)
    label = _part(row, "controlRowLabel")
    hint = _part(row, "controlRowHint")
    units = _part(row, "controlRowUnits")
    for part in (label, hint, units):
        assert not part.isVisible()

    row.set_label("Quality")
    row.set_hint("Higher is slower.")
    row.set_units("%")
    assert label.text() == "Quality" and label.isVisible()
    assert hint.text() == "Higher is slower." and hint.isVisible()
    assert units.text() == "%" and units.isVisible()

    row.set_hint("")
    assert hint.text() == ""
    assert not hint.isVisible()


def test_vertical_orientation_stacks_label_control_and_hint(qtbot):
    control = CheckBox("Option", row=True)
    row = _row(qtbot, control, label="Option", hint="caption", units="px")
    label = _part(row, "controlRowLabel")
    hint = _part(row, "controlRowHint")
    units = _part(row, "controlRowUnits")

    assert row.orientation() == "vertical"
    assert label.geometry().bottom() <= control.geometry().top()
    assert control.geometry().bottom() <= hint.geometry().top()
    # Units are the suffix of the control line, not a fourth row.
    assert units.geometry().left() >= control.geometry().right()
    assert units.geometry().top() < hint.geometry().top()


def test_horizontal_orientation_puts_the_label_in_a_left_column(qtbot):
    control = CheckBox("Option", row=True)
    row = _row(qtbot, control, label="Resolution", hint="caption", orientation="horizontal")
    label = _part(row, "controlRowLabel")

    assert row.orientation() == "horizontal"
    assert label.geometry().right() <= control.geometry().left()
    assert label.width() == scaled_px(ControlRow.LABEL_COLUMN_WIDTH) == 96
    # The caption stays below the control line, not beside the label.
    assert _part(row, "controlRowHint").geometry().top() >= control.geometry().bottom()


def test_set_control_swaps_and_releases_the_previous_widget(qtbot):
    first = CheckBox("first", row=True)
    qtbot.addWidget(first)
    row = _row(qtbot, first, label="Mode")
    second = ComboBox()
    qtbot.addWidget(second)

    row.set_control(second)

    assert row.control() is second
    assert second.parent() is row
    assert first.parent() is None
    assert row.findChild(CheckBox) is None
    assert second.isVisible()

    # Asking for the control already in the row is a no-op, not a reparent.
    row.set_control(second)
    assert row.control() is second
    assert second.parent() is row


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: CheckBox("Option", row=True), id="checkbox"),
        pytest.param(ComboBox, id="combobox"),
        pytest.param(Slider, id="slider"),
    ],
)
def test_a_real_toolkit_control_is_hosted(qtbot, factory):
    control = factory()
    row = _row(qtbot, control, label="Control")
    assert row.control() is control
    assert control.parent() is row
    assert control.isVisible()


def test_a_plain_composite_widget_is_hosted_too(qtbot):
    composite = QWidget()
    inner = CheckBox("inside", row=True, parent=composite)
    row = _row(qtbot, composite, label="Composite")
    assert row.control() is composite
    assert inner.parent() is composite


def test_the_label_column_re_resolves_through_ui_scale_without_double_scaling(qtbot):
    row = _row(qtbot, label="Resolution", orientation="horizontal")
    label = _part(row, "controlRowLabel")
    scale = UiScale.get_instance()

    assert label.width() == scaled_px(ControlRow.LABEL_COLUMN_WIDTH) == 96

    scale.set_factor(2.0)
    qtbot.wait(50)
    assert label.width() == scaled_px(ControlRow.LABEL_COLUMN_WIDTH) == 192
    # A cached-then-multiplied value would land on 384.
    assert label.width() != 4 * ControlRow.LABEL_COLUMN_WIDTH

    scale.set_factor(1.5)
    qtbot.wait(50)
    assert label.width() == scaled_px(ControlRow.LABEL_COLUMN_WIDTH) == 144

    scale.set_factor(1.0)
    qtbot.wait(50)
    assert label.width() == scaled_px(ControlRow.LABEL_COLUMN_WIDTH) == 96


def test_orientation_defaults_to_vertical_and_rejects_an_unknown_name(qtbot):
    row = ControlRow(QWidget())
    qtbot.addWidget(row)
    assert row.orientation() == "vertical"
    with pytest.raises(ValueError):
        ControlRow(QWidget(), orientation="diagonal")


def test_control_row_is_exported_from_the_public_surface():
    from sli_ui_toolkit import widgets
    from sli_ui_toolkit.ui.widgets import composite

    assert "ControlRow" in widgets.__all__
    assert widgets.ControlRow is ControlRow
    assert "ControlRow" in composite.__all__


def test_the_module_sets_no_stylesheet():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"setStyleSheet", "styleSheet"}
    ]
    assert offenders == []
