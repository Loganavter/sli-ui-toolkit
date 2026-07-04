from .drag_drop_overlay import DragDropOverlay
from .in_window_overlay import OverlayItem, OverlaySlot, TopLevelInWindowOverlay
from sli_ui_toolkit.deprecations import (
    CHOICE_OVERLAY_DEPRECATIONS,
    raise_missing_attribute,
    resolve_deprecated_attribute,
)

__all__ = [
    "DragDropOverlay",
    "OverlayItem",
    "OverlaySlot",
    "TopLevelInWindowOverlay",
]


def __getattr__(name: str):
    if name in {"ChoiceOverlay", "ChoiceSlot"}:
        from . import choice_overlay

        return resolve_deprecated_attribute(
            module_name=__name__,
            name=name,
            registry=CHOICE_OVERLAY_DEPRECATIONS,
            values={
                "ChoiceOverlay": choice_overlay.ChoiceOverlay,
                "ChoiceSlot": OverlaySlot,
            },
            stacklevel=2,
        )
    raise_missing_attribute(__name__, name)
