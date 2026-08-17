"""Widget-family registry: ordered specific → generic, first match wins.

``inspect_widget`` is the single entry point the inspector UI (and the app's
thin layer) calls. Families register matcher + extractor functions; the
generic QWidget fallback guarantees every widget is inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QWidget

from .contract import FieldKind, InspectField, WidgetInspection
from .extract import (
    from_getters,
    from_init_kwargs,
    from_qt_props,
    kind_of,
)

#: family name, matcher, extractor
_REGISTERED: list[tuple[str, Callable[[QWidget], bool], Callable[[QWidget, Any], WidgetInspection]]] = []


def register_family(
    family: str,
    match: Callable[[QWidget], bool],
    extract: Callable[[QWidget, Any], WidgetInspection],
    *,
    priority: int = 0,
) -> None:
    """Register a family.

    Matching is first-wins over the registry order: register specific
    families before their generic bases (Button subclasses before Button).
    ``priority > 0`` inserts at the front — app-side families override
    toolkit defaults with the same duck-typed matcher.
    """
    entry = (family, match, extract)
    if priority > 0:
        _REGISTERED.insert(0, entry)
    else:
        _REGISTERED.append(entry)


def registered_families() -> tuple[str, ...]:
    return tuple(name for name, _match, _extract in _REGISTERED)


def _generic_extract(widget: QWidget, theme_manager=None) -> WidgetInspection:
    """Fallback: everything a bare QWidget can tell us without guessing."""
    config = from_init_kwargs(widget)
    state = from_qt_props(widget)
    state += from_getters(
        widget,
        (
            ("geometry", lambda w: w.geometry()),
            ("size", lambda w: w.size()),
            ("visible", lambda w: w.isVisible()),
            ("enabled", lambda w: w.isEnabled()),
            ("under_mouse", lambda w: w.underMouse()),
            ("mro", lambda w: ", ".join(c.__name__ for c in type(w).__mro__)),
        ),
    )
    return WidgetInspection(family="QWidget", config=config, state=state)


def inspect_widget(
    widget: QWidget, theme_manager=None
) -> WidgetInspection:
    """Inspect any widget.

    Priority: the widget's own ``InspectSpec`` (self-declared, no guessing) →
    the duck-typed family registry → the generic QWidget fallback.
    """
    from .spec import build_inspection, spec_of

    spec = spec_of(widget)
    if spec is not None:
        try:
            return build_inspection(widget, spec, theme_manager)
        except Exception:
            pass
    for family, match, extract in _REGISTERED:
        try:
            if match(widget):
                return extract(widget, theme_manager)
        except Exception:
            continue
    return _generic_extract(widget, theme_manager)


__all__ = ["inspect_widget", "register_family", "registered_families"]
