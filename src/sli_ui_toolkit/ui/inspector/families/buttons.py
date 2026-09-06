"""Button-family extractor: every Button subclass in one place.

Covers Button and all its toolkit subclasses (ComboBox, ScrollableComboBox,
InstancesCounterButton, ScrollValueButton, ...) — regions, layers, states,
spec, and the static token family from the variant prefix.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from ..contract import InspectField, WidgetInspection
from ..extract import (
    from_dataclass,
    from_getters,
    from_init_kwargs,
    from_layers,
    from_qt_props,
    from_regions,
    kind_of,
)
from ..registry import register_family


def _match(widget: QWidget) -> bool:
    if not isinstance(widget, QWidget):
        return False
    return hasattr(widget, "region_states") and hasattr(widget, "attach_capability")


def _token_family(widget) -> tuple[str, ...]:
    try:
        from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant

        variant = get_variant(getattr(widget, "_variant", "default"))
        prefix = variant.token_prefix
    except Exception:
        prefix = getattr(widget, "_variant", "default")
    if prefix == "button.toggle":
        return (
            "surface.list",
            "button.toggle.background.hover",
            "button.toggle.background.pressed",
            "button.toggle.background.checked",
            "button.toggle.background.checked.hover",
        )
    if prefix:
        return (
            f"{prefix}.background",
            f"{prefix}.background.hover",
            f"{prefix}.background.pressed",
            f"{prefix}.background.disabled",
            f"{prefix}.border",
        )
    return ()


def _extract(widget, theme_manager=None) -> WidgetInspection:
    config = from_init_kwargs(
        widget,
        exclude={"regions", "split", "divider", "spec", "layers", "extra_layers"},
    )
    spec = getattr(widget, "spec", None)
    spec_fields = from_dataclass(spec(), label="spec") if callable(spec) else ()
    state = from_getters(
        widget,
        (
            ("checked", "isChecked"),
            ("hovered", lambda w: bool(getattr(w, "_hovered", False))),
            ("pressed", lambda w: bool(getattr(w, "_pressed", False))),
            ("hovered_region", lambda w: getattr(w, "_hovered_region", None)),
            ("pressed_region", lambda w: getattr(w, "_pressed_region", None)),
            ("defer_click", lambda w: getattr(w, "_defer_click", None)),
            ("variant", lambda w: getattr(w, "_variant", None)),
            ("density", lambda w: getattr(w, "_density", None)),
        ),
    )
    state += from_qt_props(
        widget, exclude={"regions", "split", "spec", "layers", "variant", "density"}
    )
    return WidgetInspection(
        family="Button",
        config=config + spec_fields,
        state=state,
        token_family=_token_family(widget),
        regions=from_regions(widget),
        layers=from_layers(widget),
    )


register_family("Button", _match, _extract)
