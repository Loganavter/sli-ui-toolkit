"""Live theme-token capture.

Every painter color resolution funnels through
``ThemeManager.get_color`` / ``try_get_color``. Wrapping these two methods
while the selected widget repaints records the *actual* keys it resolved —
ground truth, overriding the static per-family ``token_family``.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from .contract import FieldKind, InspectField


def capture_tokens(
    widget: QWidget, theme_manager
) -> tuple[InspectField, ...]:
    """Repaint ``widget`` and record every theme key it resolves.

    Returns ordered ``(key -> hex)`` fields; keys that failed
    ``try_get_color`` are marked ``meta={"missing": True}``. Wrapping is
    exception-safe (the original methods are always restored).
    """
    if theme_manager is None or widget is None:
        return ()
    original_get = getattr(theme_manager, "get_color", None)
    original_try = getattr(theme_manager, "try_get_color", None)
    if not callable(original_get):
        return ()

    hits: list[tuple[str, Any]] = []

    def _wrap(method_name: str):
        original = getattr(theme_manager, method_name)
        if not callable(original):
            return None

        def wrapper(key, *args, **kwargs):
            value = original(key, *args, **kwargs)
            hits.append((key, value))
            return value

        return wrapper

    wrapped_get = _wrap("get_color")
    wrapped_try = _wrap("try_get_color")
    try:
        if wrapped_get is not None:
            theme_manager.get_color = wrapped_get
        if wrapped_try is not None:
            theme_manager.try_get_color = wrapped_try
        try:
            widget.grab()
        except Exception:
            pass
    finally:
        if wrapped_get is not None:
            theme_manager.get_color = original_get
        if wrapped_try is not None:
            theme_manager.try_get_color = original_try

    fields: list[InspectField] = []
    for key, value in hits:
        if isinstance(value, QColor):
            display: Any = value.name()
        else:
            display = value
        fields.append(
            InspectField(
                name=str(key),
                value=display,
                kind=FieldKind.COLOR,
                meta={"missing": value is None},
            )
        )
    return tuple(fields)


__all__ = ["capture_tokens"]
