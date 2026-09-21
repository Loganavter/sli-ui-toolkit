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


#: meta flag marking disclosure rows (see ``capture_tokens``).
CAPTURE_LIMITATION_META = "capture_limitation"


def _limitation_field(name: str, value: str, *, kind: str) -> InspectField:
    return InspectField(
        name=name,
        value=value,
        kind=FieldKind.TEXT,
        meta={CAPTURE_LIMITATION_META: kind},
    )


def capture_tokens(
    widget: QWidget, theme_manager
) -> tuple[InspectField, ...]:
    """Repaint ``widget`` and record every theme key it resolves.

    Returns ordered ``(key -> hex)`` fields; keys that failed
    ``try_get_color`` are marked ``meta={"missing": True}``. Wrapping is
    exception-safe (the original methods are always restored).

    An empty repaint is disclosed, never silently empty:

    - a hidden widget cannot be repainted by ``grab()`` on real platforms
      (it records zero keys no matter how many tokens the widget uses) —
      an empty result on one carries a ``capture_limitation=hidden``
      disclosure row instead of ``()``;
    - a visible widget whose repaint resolves no keys most likely paints
      from cached colors/state rather than live ``ThemeManager`` lookups —
      an empty result carries a ``capture_limitation=cached`` disclosure
      row so it is not misread as "uses no theme tokens".

    (When the repaint *does* record keys the rows are returned as-is —
    offscreen ``grab()`` repaints unshown widgets, so hidden-ness alone
    suppresses nothing.)
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
    if not fields:
        # Empty repaint: disclose WHY instead of returning () (which reads
        # as "this widget uses no theme tokens"). A hidden widget cannot be
        # repainted by grab() — first-order explanation; otherwise the
        # widget most likely paints from cached colors/state without live
        # ThemeManager lookups (see paint state / token family).
        if not widget.isVisible():
            return (
                _limitation_field(
                    "capture (hidden widget)",
                    "widget is not visible: grab() cannot repaint it, so no "
                    "theme keys were recorded. Show the widget and capture "
                    "again — an empty result here says nothing about which "
                    "tokens the widget uses.",
                    kind="hidden",
                ),
            )
        return (
            _limitation_field(
                "capture (no tokens resolved)",
                "repaint resolved no theme keys: the widget likely paints "
                "from cached colors/state (see paint state / token family) "
                "rather than live ThemeManager lookups.",
                kind="cached",
            ),
        )
    return tuple(fields)


__all__ = ["CAPTURE_LIMITATION_META", "capture_tokens"]
