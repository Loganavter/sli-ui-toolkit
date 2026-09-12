"""Introspection contract for toolkit widgets.

Every toolkit (and app) widget family can be inspected uniformly through the
``WidgetInspection`` dataclass produced by ``registry.inspect_widget``.
Field names follow the toolkit docs vocabulary: ``config`` = "constructor
parameters", ``state`` = "runtime methods" (see docs/user/API_CATALOG.md).

Convention-driven extraction (``extract.py``) covers most families with zero
per-widget code; thin per-family extractors in ``families/`` curate the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldKind(str, Enum):
    """How the inspector view renders an ``InspectField`` value."""

    TEXT = "text"
    NUMBER = "number"
    BOOL = "bool"
    COLOR = "color"  # QColor / hex string → swatch
    ENUM = "enum"  # Enum member → chip + allowed values in meta
    RECT = "rect"  # QRect/QRectF → geometry text
    BLOCK = "block"  # nested tuple of InspectField → indented block
    REF = "ref"  # child QWidget → clickable (navigates the inspector)


@dataclass(slots=True)
class InspectField:
    """One config/state row of an inspected widget.

    ``private`` marks values read from a private attribute (legal in the
    toolkit repo, where the extractor sits next to the widget definition).
    """

    name: str
    value: Any
    kind: FieldKind = FieldKind.TEXT
    private: bool = False
    meta: dict = field(default_factory=dict)


@dataclass(slots=True)
class InspectRegion:
    """One Button-family region: identity, live geometry, states, rows.

    ``rect`` is real-px geometry in widget coordinates — reused by the
    inspector overlay for per-region highlighting.
    """

    id: str
    rect: Any = None  # QRectF
    states: frozenset = frozenset()
    weight: float = 1.0
    group: str | None = None
    z_index: int = 0
    corner_radii: tuple | None = None
    icon_size_px: int | None = None
    rows: tuple = ()
    override_bg: Any = None
    bg_locked: bool = False
    enabled: bool = True


@dataclass(slots=True)
class InspectLayer:
    """One active painter layer of a Button-family widget."""

    name: str
    scope: str = "region"
    active: bool = True


@dataclass(slots=True)
class WidgetInspection:
    """Uniform inspection output for any widget family."""

    family: str
    config: tuple[InspectField, ...] = ()
    state: tuple[InspectField, ...] = ()
    token_family: tuple[str, ...] = ()
    regions: tuple[InspectRegion, ...] = ()
    layers: tuple[InspectLayer, ...] = ()
    live_tokens: tuple[InspectField, ...] = ()
    #: docs reference for the widget family (repo-relative or absolute
    #: path, e.g. ``docs/user/BUTTON_API.md``) — surfaced in the Object
    #: section and reusable by host apps.
    docs: str = ""


__all__ = [
    "FieldKind",
    "InspectField",
    "InspectLayer",
    "InspectRegion",
    "WidgetInspection",
]
