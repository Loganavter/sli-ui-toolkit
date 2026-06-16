from .drag_drop_overlay import DragDropOverlay
from .in_window_overlay import OverlayItem, OverlaySlot, TopLevelInWindowOverlay

__all__ = [
    "DragDropOverlay",
    "OverlayItem",
    "OverlaySlot",
    "TopLevelInWindowOverlay",
]


def __getattr__(name: str):
    if name in {"ChoiceOverlay", "ChoiceSlot"}:
        import warnings

        from . import choice_overlay

        warnings.warn(
            f"{name} is deprecated and is not part of the public overlay API. "
            "Use TopLevelInWindowOverlay and OverlaySlot instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(choice_overlay, name)
    raise AttributeError(name)
