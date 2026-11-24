"""Registry + allowlist for the toolkit value-edit contract gate.

``tests/test_value_control_edit_contract.py`` scans ``src/sli_ui_toolkit`` for
declarations a value control can take: a class that subclasses ``Slider`` (it
inherits the value-edit machinery), a class that defines ``is_editing`` (it
opts into ``navigation_sections.arrow_gate_open``, so arrows are withheld while
it reports not-editing), or a class whose ``keyPressEvent`` steps its own value
(it can eat navigation keys whether or not it names an edit mode). Every such
declaration must appear in exactly one of the tables below, otherwise the
guard fails and names ``module:Class`` — that is how a NEW value control is
forced to opt in to the contract instead of silently eating navigation keys
again.

The contract has exactly two declared shapes, and a value control picks one:

* ``VALUE_CONTROLS`` — **edit-mode shape** (``Slider``): Enter enters edit
  mode, arrows/WASD adjust only while editing, Enter commits, Esc reverts,
  idle arrows leave the value untouched. Each entry carries the reason, a
  factory used by the behavioural tests, and whether the control implements
  the WASD half of the contract.
* ``KEYBOARD_STEP_CONTROLS`` — **typed-field shape** (``SpinBox``): the
  control is a text field, so Left/Right must stay caret movement. Up/Down are
  ignored while idle (navigation owns them) and the value is stepped with
  PageUp/PageDown. Each entry carries the reason, a factory, and a ``read``
  accessor the behavioural test compares.
* ``ALLOWLIST`` — declarations that define ``is_editing`` but are **not**
  value controls, so they must not be held to either shape (they already use
  edit mode for text entry / caret behaviour). Every entry carries a one-line
  reason; an entry with an empty reason fails the test.

Ratchet rules (mirroring ``tests/px_scaling_allowlist.py``): add an entry only
together with its reason, and delete it once the declaration is gone — an
entry whose class cannot be found in the tree fails the scan test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    DoubleSpinBox,
    Slider,
    SpinBox,
    Stepper,
    TimeLineEdit,
)


def _make_slider() -> QWidget:
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    return slider


@dataclass(frozen=True)
class ValueControl:
    """One registered value control (the behavioural tests read all fields)."""

    #: Why this widget is a value control under the contract.
    reason: str
    #: Builds a fresh, shown-ready instance (range/value configured by the
    #: factory, the test only focuses it inside a section host).
    factory: Callable[[], QWidget]
    #: Whether the contract's WASD half applies (W/A/S/D adjust in edit mode).
    wasd: bool = True


def _make_spinbox() -> QWidget:
    box = SpinBox(default_value=5)
    box.setRange(0, 20)
    return box


def _make_double_spinbox() -> QWidget:
    box = DoubleSpinBox(default_value=5.0, single_step=1.0)
    box.setRange(0.0, 20.0)
    return box


def _make_stepper() -> QWidget:
    box = Stepper(default_value=5)
    box.setRange(0, 20)
    return box


def _make_time_line_edit() -> QWidget:
    return TimeLineEdit("10:20")


def _read_value(widget: QWidget) -> float:
    return float(widget.value())


def _read_time_minutes(widget: QWidget) -> float:
    time_obj = widget.time()
    return float(time_obj.hour() * 60 + time_obj.minute())


@dataclass(frozen=True)
class KeyboardStepControl:
    """One typed value field that steps with PageUp/PageDown (shape b)."""

    #: Why this widget takes the typed-field shape instead of an edit mode.
    reason: str
    #: Builds a fresh, shown-ready instance (range/value preconfigured).
    factory: Callable[[], QWidget]
    #: Comparable snapshot of the control's value (int/float; QTime is mapped
    #: to minutes by its entry).
    read: Callable[[QWidget], float]


#: ``"relative.module:Class"`` (relative to ``src/sli_ui_toolkit``) -> entry.
#: Behavioural coverage in ``test_value_control_edit_contract.py`` runs once
#: per entry through a real ``ToolbarRowsSection``.
VALUE_CONTROLS: dict[str, ValueControl] = {
    "ui.widgets.atomic.slider:Slider": ValueControl(
        reason=(
            "numeric value control: QSlider-derived, owns the explicit edit "
            "mode (Enter) that arrow/WASD adjustment is gated on"
        ),
        factory=_make_slider,
    ),
}

#: ``"relative.module:Class"`` -> entry, typed-field shape (PageUp/PageDown).
#: Behavioural coverage in ``test_value_control_edit_contract.py`` runs once
#: per entry through a real ``ToolbarRowsSection``.
KEYBOARD_STEP_CONTROLS: dict[str, KeyboardStepControl] = {
    "ui.widgets.atomic.spinbox:SpinBox": KeyboardStepControl(
        reason=(
            "typed numeric field: Left/Right are caret movement, so idle "
            "Up/Down are ignored and PageUp/PageDown step the value"
        ),
        factory=_make_spinbox,
        read=_read_value,
    ),
    "ui.widgets.atomic.spinbox:DoubleSpinBox": KeyboardStepControl(
        reason="float variant of SpinBox: same typed-field shape",
        factory=_make_double_spinbox,
        read=_read_value,
    ),
    "ui.widgets.atomic.stepper:Stepper": KeyboardStepControl(
        reason=(
            "SpinBox with a wide ▲/▼ gutter: still a typed field, so the "
            "SpinBox shape applies (PageUp/PageDown, idle Up/Down ignored)"
        ),
        factory=_make_stepper,
        read=_read_value,
    ),
    "ui.widgets.atomic.time_line_edit:TimeLineEdit": KeyboardStepControl(
        reason=(
            "typed HH:mm field: digits/colon are typed, Left/Right are caret "
            "movement, so PageUp/PageDown step one minute and idle Up/Down "
            "stay available for navigation"
        ),
        factory=_make_time_line_edit,
        read=_read_time_minutes,
    ),
}

#: ``"relative.module:Class"`` -> one-line reason it is NOT a value control.
ALLOWLIST: dict[str, str] = {
    "ui.widgets.text.text:Text": (
        "text editor: is_editing() reports the code-buffer text-edit mode "
        "(set_editing), not a value being adjusted by arrows"
    ),
    "ui.widgets.text.engine.canvas:TextCanvasCore": (
        "text canvas: is_editing() mirrors the painted text buffer's edit "
        "state (caret/typing), not a value control"
    ),
    "ui.widgets.composite.text_scroll:TextScrollArea": (
        "text scroll host: is_editing() forwards to its hosted Text's "
        "text-edit mode, not a value control"
    ),
}


def covered_ids() -> frozenset[str]:
    """Every ``module:Class`` the AST scan accepts as covered."""
    return (
        frozenset(VALUE_CONTROLS)
        | frozenset(KEYBOARD_STEP_CONTROLS)
        | frozenset(ALLOWLIST)
    )
