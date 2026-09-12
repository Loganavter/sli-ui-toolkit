"""Toolkit widget inspector.

Uniform config/state inspection for every toolkit (and app) widget family,
plus the visual inspector UI (InspectorWindow, per-region overlay,
controller). The app wires it and registers app-specific families.

Public entry point: ``inspect_widget(widget, theme_manager=None)``.
"""

from __future__ import annotations

# Import order = family priority: specific families register before their
# generic bases. Inputs (ComboBox...) and misc (DropZoneLabel, CheckBox...)
# before labels; everything before Button (the generic base of many widget
# families) — Button must be registered last among button subclasses.
#
# NOTE: only lightweight modules are imported here. view/controller/overlay
# import widget modules themselves; eagerly importing them from the package
# __init__ creates a cycle (widgets import ``inspector.spec`` → package
# __init__ runs → view → widgets → atomic …). Import them explicitly:
#   from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from . import capture, contract, extract, qss_scan, registry, spec  # noqa: F401
from .families import (  # noqa: F401
    inputs,
    misc,
    labels,
    nav,
    flyouts,
    timeline,
    buttons,
)
from .contract import (  # noqa: F401
    FieldKind,
    InspectField,
    InspectLayer,
    InspectRegion,
    WidgetInspection,
)
from .registry import (  # noqa: F401
    inspect_widget,
    register_family,
    registered_families,
)

__all__ = [
    "FieldKind",
    "InspectField",
    "InspectLayer",
    "InspectRegion",
    "WidgetInspection",
    "inspect_widget",
    "register_family",
    "registered_families",
]
