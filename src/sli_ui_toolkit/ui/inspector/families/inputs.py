"""Input families: Switch, Slider/ValueSlider, SpinBox/DoubleSpinBox,
TimeLineEdit, CustomLineEdit, CheckBox, RadioButton, ComboBox,
ScrollableComboBox.

Config comes from ``__init__`` kwargs ↔ instance attrs; runtime state from
existing getters plus marked-private attrs where no getter exists.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from ..contract import WidgetInspection
from ..extract import (
    from_getters,
    from_init_kwargs,
    from_qt_props,
)
from ..registry import register_family


def _make(family: str, match, state_pairs, token_family):
    def extract(widget, theme_manager=None) -> WidgetInspection:
        config = from_init_kwargs(widget)
        state = from_getters(widget, state_pairs) + from_qt_props(widget)
        return WidgetInspection(
            family=family, config=config, state=state, token_family=token_family
        )

    register_family(family, match, extract)


_SWITCH_STATE = (
    ("checked", "isChecked"),
    ("hover", (lambda w: getattr(w, "_hover", 0.0)), True),
    ("progress", (lambda w: getattr(w, "_progress", 0.0)), True),
    ("show_state_text", (lambda w: getattr(w, "_show_text", False)), True),
    ("on_text", (lambda w: getattr(w, "_on_text", "")), True),
    ("off_text", (lambda w: getattr(w, "_off_text", "")), True),
)
_make(
    "Switch",
    lambda w: hasattr(w, "set_state_texts") and hasattr(w, "isChecked"),
    _SWITCH_STATE,
    ("switch.knob.on", "switch.knob.off", "switch.track.off.border", "accent"),
)

_SLIDER_STATE = (
    ("value", lambda w: w.value()),
    ("minimum", lambda w: w.minimum()),
    ("maximum", lambda w: w.maximum()),
    ("single_step", lambda w: w.singleStep()),
    ("orientation", lambda w: str(w.orientation())),
    ("hovered", (lambda w: getattr(w, "_hovered", False)), True),
    ("pressed", (lambda w: getattr(w, "_pressed", False)), True),
)
_make(
    "Slider",
    lambda w: hasattr(w, "trackThickness") and hasattr(w, "thumbRadius"),
    _SLIDER_STATE,
    ("slider.track.unfilled", "slider.thumb.outer", "accent", "dialog.border"),
)

_SPINBOX_STATE = (
    ("value", lambda w: w.value()),
    ("minimum", lambda w: getattr(w, "_minimum", 0)),
    ("maximum", lambda w: getattr(w, "_maximum", 0)),
    ("default_value", lambda w: getattr(w, "_default_value", None)),
)
_make(
    "DoubleSpinBox",
    lambda w: type(w).__name__ == "DoubleSpinBox" and hasattr(w, "singleStep"),
    _SPINBOX_STATE + (("single_step", lambda w: w.singleStep()), ("decimals", lambda w: getattr(w, "_decimals", 2))),
    ("surface.background", "input.border.thin", "dialog.text", "accent"),
)
_make(
    "SpinBox",
    lambda w: hasattr(w, "value") and hasattr(w, "_minimum") and not hasattr(w, "singleStep"),
    _SPINBOX_STATE,
    ("surface.background", "input.border.thin", "dialog.text", "accent"),
)

_LINE_EDIT_STATE = (
    ("text", lambda w: w.text()),
    ("placeholder", lambda w: w.placeholderText()),
    ("alignment", lambda w: str(w.textAlignment())),
    ("underline_color", "underlineColor"),
    ("underline_thickness", "underlineThickness"),
    ("focused_underline_color", "focusedUnderlineColor"),
    ("focused_underline_thickness", "focusedUnderlineThickness"),
)
_make(
    "CustomLineEdit",
    lambda w: hasattr(w, "underlineThickness") and hasattr(w, "textAlignment"),
    _LINE_EDIT_STATE,
    ("surface.background", "input.border.thin", "dialog.text", "accent"),
)

_COMBO_STATE = (
    ("current_index", lambda w: w.currentIndex()),
    ("current_text", lambda w: w.currentText()),
    ("count", lambda w: w.count()),
    ("items", lambda w: [t for t, _d in w.items()]),
)
_make(
    "ComboBox",
    lambda w: hasattr(w, "showDropdown") and hasattr(w, "items"),
    _COMBO_STATE,
    ("surface.background", "input.border.thin", "list_item.background.hover", "surface.background"),
)
_make(
    "ScrollableComboBox",
    lambda w: hasattr(w, "updateState") and hasattr(w, "currentIndex"),
    _COMBO_STATE,
    ("surface.background", "input.border.thin", "dialog.text"),
)
