"""Per-widget localization hooks with a process-global legacy fallback.

Widgets bind their ``TimelineCallbacks`` hooks via :func:`bind_widget`;
scoped accessors (:func:`localize_token_for` / :func:`localize_value_for`)
read the widget's own hooks first and only then fall back to the
process-global ``set_localize_*`` callbacks.

The globals stay because ``viewport.py`` / ``primitives.py`` format tooltips
and labels without a widget handle (out of scope for this change) — new code
must prefer the ``*_for`` accessors. Threading the widget through those
paint paths is a follow-up.
"""

from __future__ import annotations

from typing import Any, Callable

_localize_token_fn: Callable[[str], str] | None = None
_localize_value_fn: Callable[[object], str] | None = None

def set_localize_token(fn: Callable[[str], str] | None) -> None:
    """Legacy process-global hook (kept for viewport/primitives paths)."""
    global _localize_token_fn
    _localize_token_fn = fn

def set_localize_value(fn: Callable[[object], str] | None) -> None:
    """Legacy process-global hook (kept for viewport/primitives paths)."""
    global _localize_value_fn
    _localize_value_fn = fn

def bind_widget(
    widget: Any,
    *,
    token_fn: Callable[[str], str] | None = None,
    value_fn: Callable[[object], str] | None = None,
) -> None:
    """Scope localization hooks to one widget instance (no process state)."""
    widget._i18n_token_fn = token_fn
    widget._i18n_value_fn = value_fn

def _widget_hook(widget: Any, name: str) -> Callable[..., str] | None:
    if widget is None:
        return None
    fn = getattr(widget, name, None)
    return fn if callable(fn) else None

def localize_token(token: str) -> str:
    if _localize_token_fn is not None:
        return _localize_token_fn(token)
    return str(token)

def localize_value(value) -> str:
    if _localize_value_fn is not None:
        return _localize_value_fn(value)
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)

def localize_token_for(widget: Any, token: str) -> str:
    """Widget-scoped ``localize_token`` (global fallback when unbound)."""
    fn = _widget_hook(widget, "_i18n_token_fn")
    if fn is not None:
        return fn(token)
    return localize_token(token)

def localize_value_for(widget: Any, value: object) -> str:
    """Widget-scoped ``localize_value`` (global fallback when unbound)."""
    fn = _widget_hook(widget, "_i18n_value_fn")
    if fn is not None:
        return fn(value)
    return localize_value(value)
