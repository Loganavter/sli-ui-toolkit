from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

ContextMenuSurface = Literal["in_window", "popup"]

@dataclass(slots=True)
class FlyoutTimingConfig:
    transient_auto_hide_delay_ms: int = 180
    flyout_animation_duration_ms: int = 160
    text_settings_flyout_animation_duration_ms: int = 180
    dropdown_drop_offset_px: int = 24

_timings = FlyoutTimingConfig()
_overlay_resolver: Callable[[object | None], object | None] | None = None
_rating_gesture_factory: Callable[..., object] | None = None
_dragdrop_service_getter: Callable[[], object | None] | None = None
_context_menu_surface: ContextMenuSurface = "in_window"

def configure_toolkit(
    *,
    timings: FlyoutTimingConfig | None = None,
    overlay_resolver: Callable[[object | None], object | None] | None = None,
    rating_gesture_factory: Callable[..., object] | None = None,
    dragdrop_service_getter: Callable[[], object | None] | None = None,
    context_menu_surface: ContextMenuSurface | None = None,
    ripple_duration_ms: int | None = None,
    default_defer_click: bool | int | str | None = None,
) -> None:
    """Configure process-wide toolkit behaviour.

    Button press feedback (ripple duration + default click deferral) can also
    be set via ``set_ripple_duration_ms`` / ``set_default_defer_click``.
    """
    global _timings, _overlay_resolver, _rating_gesture_factory, _dragdrop_service_getter
    global _context_menu_surface
    if timings is not None:
        _timings = timings
    if overlay_resolver is not None:
        _overlay_resolver = overlay_resolver
    if rating_gesture_factory is not None:
        _rating_gesture_factory = rating_gesture_factory
    if dragdrop_service_getter is not None:
        _dragdrop_service_getter = dragdrop_service_getter
    if context_menu_surface is not None:
        _context_menu_surface = context_menu_surface
    if ripple_duration_ms is not None:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import set_ripple_duration_ms

        set_ripple_duration_ms(ripple_duration_ms)
    if default_defer_click is not None:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import set_default_defer_click

        set_default_defer_click(default_defer_click)

def get_flyout_timings() -> FlyoutTimingConfig:
    return _timings

def get_context_menu_surface() -> ContextMenuSurface:
    return _context_menu_surface

def resolve_overlay_layer(widget: object | None):
    if _overlay_resolver is None:
        return None
    try:
        return _overlay_resolver(widget)
    except Exception:
        return None

def create_rating_gesture(**kwargs):
    if _rating_gesture_factory is None:
        return None
    try:
        return _rating_gesture_factory(**kwargs)
    except Exception:
        return None

def get_dragdrop_service():
    if _dragdrop_service_getter is None:
        from sli_ui_toolkit.ui.services.dragdrop_service import ToolkitDragDropService

        return ToolkitDragDropService.get_instance()
    try:
        return _dragdrop_service_getter()
    except Exception:
        from sli_ui_toolkit.ui.services.dragdrop_service import ToolkitDragDropService

        return ToolkitDragDropService.get_instance()
