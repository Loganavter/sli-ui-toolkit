"""Process-wide button press feedback (ripple duration + click deferral).

Hosts typically set both at startup via ``configure_toolkit`` or the
standalone setters — same pattern as flyout timings.
"""

from __future__ import annotations

from typing import Literal

# Wait for the current system ripple duration before emitting clicked.
DEFER_CLICK_AWAIT_RIPPLE: Literal["ripple"] = "ripple"

_DEFAULT_RIPPLE_DURATION_MS = 280
_ripple_duration_ms = _DEFAULT_RIPPLE_DURATION_MS
_default_defer_click: bool | int | str = False
_default_underline_fade: bool = True


def set_ripple_duration_ms(ms: int) -> None:
    """Set the process-wide Material ripple duration (ms).

    Updates ``RippleEffect.DURATION_MS`` so existing docs/call sites that
    read the class attribute stay in sync. Buttons already animating keep
    their elapsed clock; new waves use the new duration.
    """
    global _ripple_duration_ms
    _ripple_duration_ms = max(1, int(ms))
    # Keep the class attribute aligned for ``RippleEffect.DURATION_MS`` reads.
    from sli_ui_toolkit.ui.widgets.buttons.layers.ripple import RippleEffect

    RippleEffect.DURATION_MS = _ripple_duration_ms


def get_ripple_duration_ms() -> int:
    """Return the process-wide ripple duration in milliseconds."""
    return _ripple_duration_ms


def set_default_defer_click(value: bool | int | str) -> None:
    """Set the process-wide default for ``Button(..., defer_click=None)``.

    ``False`` — emit ``clicked`` synchronously (toolkit library default).
    ``True`` — next event-loop tick (``QTimer.singleShot(0, …)``).
    ``int`` — wait that many milliseconds.
    ``DEFER_CLICK_AWAIT_RIPPLE`` / ``"ripple"`` — wait
    ``get_ripple_duration_ms()`` so the wave finishes before heavy slots.
    """
    global _default_defer_click
    if isinstance(value, str) and value != DEFER_CLICK_AWAIT_RIPPLE:
        raise ValueError(
            f"default_defer_click string must be {DEFER_CLICK_AWAIT_RIPPLE!r}, "
            f"got {value!r}"
        )
    _default_defer_click = value


def get_default_defer_click() -> bool | int | str:
    """Return the process-wide default ``defer_click`` policy."""
    return _default_defer_click


def set_default_underline_fade(value: bool) -> None:
    """Set the process-wide default for ``Button(..., underline_fade=None)``.

    Controls whether the true left/right ends of a ``show_underline`` strip
    taper to transparent (``True``, library default) or stop with a crisp
    hard edge (``False``). Buttons that pass an explicit ``underline_fade=``
    always override this.
    """
    global _default_underline_fade
    _default_underline_fade = bool(value)


def get_default_underline_fade() -> bool:
    """Return the process-wide default underline tip-fade policy."""
    return _default_underline_fade


def reset_feedback_defaults() -> None:
    """Reset ripple duration, click deferral, and underline fade to defaults."""
    global _default_defer_click, _default_underline_fade
    set_ripple_duration_ms(_DEFAULT_RIPPLE_DURATION_MS)
    _default_defer_click = False
    _default_underline_fade = True


def coerce_defer_click_ms(value: bool | int | str) -> int | None:
    """Normalize a ``defer_click`` policy to a ``QTimer.singleShot`` delay.

    ``False`` → emit synchronously (``None``).
    ``True`` → next event-loop tick (``0``).
    ``int`` → wait that many milliseconds.
    ``"ripple"`` → wait ``get_ripple_duration_ms()``.
    """
    if value == DEFER_CLICK_AWAIT_RIPPLE:
        return get_ripple_duration_ms()
    if isinstance(value, bool):
        return 0 if value else None
    if isinstance(value, str):
        raise ValueError(
            f"defer_click string must be {DEFER_CLICK_AWAIT_RIPPLE!r}, got {value!r}"
        )
    return max(0, int(value))
