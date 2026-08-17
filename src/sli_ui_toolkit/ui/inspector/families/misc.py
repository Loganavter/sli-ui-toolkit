"""Misc families: CheckBox/RadioButton, DropZoneLabel, LoadingSpinner,
CustomGroupWidget, ToastNotification, CalendarWidget, SunburstChartWidget."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from ..contract import WidgetInspection
from ..extract import from_getters, from_init_kwargs, from_qt_props
from ..registry import register_family


def _make(family: str, match, state_pairs, token_family):
    def extract(widget, theme_manager=None) -> WidgetInspection:
        config = from_init_kwargs(widget)
        state = from_getters(widget, state_pairs) + from_qt_props(widget)
        return WidgetInspection(
            family=family, config=config, state=state, token_family=token_family
        )

    register_family(family, match, extract)


_make(
    "CheckBox",
    lambda w: type(w).__name__ == "CheckBox" and hasattr(w, "checkState"),
    (
        ("checked", lambda w: w.isChecked()),
        ("check_state", lambda w: str(w.checkState())),
        ("hover_progress", lambda w: w.property("hoverProgress")),
        ("checked_progress", lambda w: w.property("checkedProgress")),
    ),
    ("accent", "dialog.border", "dialog.text", "dialog.button.hover"),
)
_make(
    "RadioButton",
    lambda w: type(w).__name__ == "RadioButton" and hasattr(w, "isChecked"),
    (
        ("checked", lambda w: w.isChecked()),
        ("hover_progress", lambda w: w.property("hoverProgress")),
    ),
    ("accent", "dialog.border", "dialog.text", "dialog.button.hover"),
)
_make(
    "DropZoneLabel",
    lambda w: hasattr(w, "file_dropped") and hasattr(w, "get_original_text"),
    (
        ("text", lambda w: w.get_original_text()),
        ("drag_active", (lambda w: getattr(w, "_drag_active", False)), True),
        ("hovered", (lambda w: getattr(w, "_hovered", False)), True),
    ),
    ("accent", "dialog.border"),
)
_make(
    "LoadingSpinner",
    lambda w: hasattr(w, "is_spinning"),
    (
        ("spinning", lambda w: w.is_spinning()),
        ("angle", (lambda w: getattr(w, "_angle", 0)), True),
    ),
    ("accent",),
)
_make(
    "CustomGroupWidget",
    lambda w: hasattr(w, "add_widget") and hasattr(w, "set_title"),
    (
        ("title", lambda w: w.get_title()),
        ("children", lambda w: len(w.findChildren(QWidget))),
    ),
    ("dialog.border", "dialog.background", "dialog.text"),
)
_make(
    "ToastNotification",
    lambda w: hasattr(w, "show_message") and hasattr(w, "update_message"),
    (
        ("width_floor", (lambda w: getattr(w, "_width_floor", None)), True),
        ("visible", lambda w: w.isVisible()),
    ),
    (
        "toast.background",
        "toast.border",
        "toast.text",
        "toast.progress.background",
        "toast.progress.fill",
    ),
)
_make(
    "CalendarWidget",
    lambda w: hasattr(w, "update_view") and hasattr(w, "set_color"),
    (("day_buttons", (lambda w: len(getattr(w, "_day_buttons", []) or [])), True),),
    ("accent", "dialog.background", "dialog.text"),
)
_make(
    "SunburstChartWidget",
    lambda w: hasattr(w, "set_segments"),
    (("segments", lambda w: len(getattr(w, "_segments", []) or [])),),
    ("accent", "dialog.background", "dialog.text"),
)
