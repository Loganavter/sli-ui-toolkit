from .drag_drop_overlay import DragDropOverlay
from .in_window_overlay import OverlayItem, OverlaySlot, TopLevelInWindowOverlay
from .marquee_state import (
    DEFAULT_MARQUEE_ACCENT,
    MarqueeState,
    marquee_dirty_rect,
    paint_marquee_band,
)
from sli_ui_toolkit.deprecations import (
    CHOICE_OVERLAY_DEPRECATIONS,
    raise_missing_attribute,
    resolve_deprecated_attribute,
)

__all__ = [
    "DEFAULT_MARQUEE_ACCENT",
    "DragDropOverlay",
    "MarqueeState",
    "OverlayItem",
    "OverlaySlot",
    "TopLevelInWindowOverlay",
    "marquee_dirty_rect",
    "paint_marquee_band",
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
