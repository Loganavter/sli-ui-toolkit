"""Registry + allowlist for the toolkit value-edit contract gate.

``tests/test_value_control_edit_contract.py`` scans ``src/sli_ui_toolkit`` for
two shapes: a class that subclasses ``Slider`` (it inherits the value-edit
machinery) or a class that defines ``is_editing`` (it opts into
``navigation_sections.arrow_gate_open``, so arrows are withheld while it
reports not-editing). Every such declaration must appear in exactly one of
the two tables below, otherwise the guard fails and names
``module:Class`` — that is how a NEW value control is forced to opt in to the
contract (idle arrows untouched, Enter edits, Enter commits, Esc reverts)
instead of silently eating navigation keys again.

Why the two tables are separate:

* ``VALUE_CONTROLS`` — real value controls: they own a numeric/ordinal value
  that the edit-mode state machine adjusts. Each entry carries the reason, a
  factory used by the behavioural tests, and whether the control implements
  the WASD half of the contract. ``Slider`` is the only one today.
* ``ALLOWLIST`` — declarations that legitimately define ``is_editing`` but are
  **not** value controls, so they must not be held to the value-edit contract
  (they already use edit mode for text entry / caret behaviour). Every entry
  carries a one-line reason; an entry with an empty reason fails the test.

``SpinBox`` is deliberately **absent from both** (it is a typed control:
``CustomLineEdit`` subclass, arrows move the caret and it has no ``is_editing``
edit mode). The scan only gates ``is_editing`` / ``Slider`` subclasses, so a
typed control needs no entry; if a future SpinBox grows an edit mode it must
be registered here with a reason.

Ratchet rules (mirroring ``tests/px_scaling_allowlist.py``): add an entry only
together with its reason, and delete it once the declaration is gone — an
entry whose class cannot be found in the tree fails the scan test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import Slider


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
    "ui.widgets.composite.text_view.widget:TextView": (
        "text view: is_editing() delegates to its TextCanvas for text entry, "
        "not a value control"
    ),
}


def covered_ids() -> frozenset[str]:
    """Every ``module:Class`` the AST scan accepts as covered."""
    return frozenset(VALUE_CONTROLS) | frozenset(ALLOWLIST)
