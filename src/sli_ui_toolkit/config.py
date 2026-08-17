from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

ContextMenuSurface = Literal["in_window", "popup"]

@dataclass(slots=True)
class FlyoutTimingConfig:
    transient_auto_hide_delay_ms: int = 180
    flyout_animation_duration_ms: int = 160
    text_settings_flyout_animation_duration_ms: int = 180
    dropdown_drop_offset_px: int = 24
    flyout_fade_out_duration_ms: int = 150
    # Process-wide default for BaseFlyout.show_aligned's animation when the
    # caller omits it (one of "none" / "slide" / "fade" / "slide-fade").
    # "none" preserves the historical behavior; hosts set e.g. "slide-fade" to
    # animate every default flyout without touching each call site.
    default_flyout_animation: str = "none"

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
    default_underline_fade: bool | None = None,
    ui_scale_factor: float | None = None,
) -> None:
    """Configure process-wide toolkit behaviour.

    Button press feedback (ripple duration + default click deferral) can also
    be set via ``set_ripple_duration_ms`` / ``set_default_defer_click``.
    Underline tip fade (``set_default_underline_fade``) likewise.

    ``ui_scale_factor`` applies a logical-px multiplier to fonts, icons,
    tokens, and widget geometry via ``UiScale`` (clamped to the UiScale
    safety range 0.5–2.5; the host's settings UI exposes the same range,
    e.g. Improve-ImgSLI's "Interface Scale" slider 50–250). Live-applies
    immediately: widgets subscribed to ``UiScale.scale_changed``
    relayout/repaint on the spot.
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
    if ui_scale_factor is not None:
        from sli_ui_toolkit.ui.managers.ui_scale import UiScale

        UiScale.get_instance().set_factor(ui_scale_factor)
    if ripple_duration_ms is not None:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import set_ripple_duration_ms

        set_ripple_duration_ms(ripple_duration_ms)
    if default_defer_click is not None:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import set_default_defer_click

        set_default_defer_click(default_defer_click)
    if default_underline_fade is not None:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import set_default_underline_fade

        set_default_underline_fade(default_underline_fade)

def reset_toolkit_config() -> None:
    """Reset all process-wide toolkit configuration to library defaults.

    ``configure_toolkit`` state is module-level, so tests (or plugin reload)
    that call it must restore defaults afterward or leak state into
    unrelated code. This undoes everything ``configure_toolkit`` can set,
    including the button-feedback shorthands.
    """
    global _timings, _overlay_resolver, _rating_gesture_factory, _dragdrop_service_getter
    global _context_menu_surface
    _timings = FlyoutTimingConfig()
    _overlay_resolver = None
    _rating_gesture_factory = None
    _dragdrop_service_getter = None
    _context_menu_surface = "in_window"

    from sli_ui_toolkit.ui.widgets.buttons.feedback import reset_feedback_defaults

    reset_feedback_defaults()

    from sli_ui_toolkit.ui.managers.ui_scale import UiScale

    UiScale.get_instance().set_factor(1.0)

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
        logger.warning("overlay_resolver raised; falling back to no overlay", exc_info=True)
        return None

def create_rating_gesture(**kwargs):
    if _rating_gesture_factory is None:
        return None
    try:
        return _rating_gesture_factory(**kwargs)
    except Exception:
        logger.warning("rating_gesture_factory raised; rating gesture disabled", exc_info=True)
        return None

def get_dragdrop_service():
    if _dragdrop_service_getter is None:
        from sli_ui_toolkit.ui.services.dragdrop_service import ToolkitDragDropService

        return ToolkitDragDropService.get_instance()
    try:
        return _dragdrop_service_getter()
    except Exception:
        logger.warning(
            "dragdrop_service_getter raised; falling back to ToolkitDragDropService.get_instance()",
            exc_info=True,
        )
        from sli_ui_toolkit.ui.services.dragdrop_service import ToolkitDragDropService

        return ToolkitDragDropService.get_instance()
