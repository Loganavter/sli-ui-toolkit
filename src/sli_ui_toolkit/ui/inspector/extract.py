"""Convention-driven extraction helpers.

The inspector must not guess and must not require hand-written field lists
for every widget. These helpers derive config/state from what already exists:

- ``__init__`` signatures ↔ instance attrs / Qt dynamic properties;
- declarative config dataclasses (``LabelConfig``, ``ButtonSpec``, ...);
- existing runtime getters;
- Qt dynamic properties;
- Button-family regions/layers/states.

Per-family extractors in ``families/`` compose these helpers into 10-25 line
functions.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from enum import Enum
from typing import Any, Callable, Iterable

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from .contract import FieldKind, InspectField, InspectLayer, InspectRegion

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6,8}$")

#: Constructor kwargs that are never inspection data.
_SKIP_INIT_KWARGS = frozenset({"self", "parent", "store", "callbacks"})


def kind_of(value: Any) -> FieldKind:
    """Auto-detect the render kind for a raw value."""
    if isinstance(value, bool):
        return FieldKind.BOOL
    if isinstance(value, (int, float)):
        return FieldKind.NUMBER
    if isinstance(value, Enum):
        return FieldKind.ENUM
    if isinstance(value, QColor) or (
        isinstance(value, str) and _HEX_COLOR_RE.match(value)
    ):
        return FieldKind.COLOR
    if isinstance(value, (QRect, QRectF)):
        return FieldKind.RECT
    if isinstance(value, QWidget):
        return FieldKind.REF
    if isinstance(value, tuple) and value and all(
        isinstance(item, InspectField) for item in value
    ):
        return FieldKind.BLOCK
    return FieldKind.TEXT


def _read_attr(widget: QWidget, name: str) -> tuple[Any, bool] | None:
    """Read ``widget.name`` / ``widget._name`` / a Qt dynamic property.

    Returns ``(value, private)`` or ``None`` when nothing is set. Bound
    methods are skipped (only plain data attributes are config/state).
    """
    for attr in (name, f"_{name}", f"_{name}_override"):
        try:
            if hasattr(widget, attr):
                value = getattr(widget, attr)
                if callable(value) and not isinstance(value, QColor):
                    continue
                return value, attr.startswith("_")
        except Exception:
            continue
    for raw in widget.dynamicPropertyNames():
        if bytes(raw).decode() == name:
            value = widget.property(name)
            if value is not None:
                return value, False
    return None


def _init_signature_with_kwargs(widget: QWidget) -> inspect.Signature:
    """First ``__init__`` in the MRO that declares usable named kwargs.

    Thin subclasses that forward ``*args, **kwargs`` (e.g. app-side
    ``WorkspaceTabStrip(AdaptiveTabStrip)``) would otherwise hide every
    constructor parameter from ``from_init_kwargs``; walking the MRO makes
    the nearest ancestor that actually declares named parameters the source
    of truth.
    """
    for cls in type(widget).__mro__:
        try:
            sig = inspect.signature(cls.__init__)
        except (TypeError, ValueError):
            continue
        usable = [
            (name, param)
            for name, param in sig.parameters.items()
            if name not in _SKIP_INIT_KWARGS
            and param.kind
            not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        ]
        if usable:
            return sig
    return inspect.signature(type(widget).__init__)


def from_init_kwargs(
    widget: QWidget,
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    skip_unset: bool = True,
) -> tuple[InspectField, ...]:
    """Config from the widget's ``__init__`` signature ↔ instance state.

    For each constructor kwarg reads ``widget.<name>``, ``widget._<name>`` or
    a Qt dynamic property with the same name, auto-kinding the value. Fields
    read from a private attribute are marked ``private=True``. When the leaf
    class declares no usable named kwargs (``*args, **kwargs`` forwarding
    wrapper), the nearest MRO ancestor with named parameters is used instead.
    """
    include_set = set(include) if include is not None else None
    exclude_set = set(exclude) if exclude is not None else set()
    try:
        sig = _init_signature_with_kwargs(widget)
    except (TypeError, ValueError):
        return ()
    out: list[InspectField] = []
    for name, param in sig.parameters.items():
        if name in _SKIP_INIT_KWARGS or name in exclude_set:
            continue
        if include_set is not None and name not in include_set:
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        resolved = _read_attr(widget, name)
        if resolved is None:
            continue
        value, private = resolved
        if skip_unset and value is None:
            continue
        out.append(
            InspectField(name=name, value=value, kind=kind_of(value), private=private)
        )
    return tuple(out)


def from_dataclass(obj: Any, *, label: str | None = None) -> tuple[InspectField, ...]:
    """Dump a declarative config dataclass (LabelConfig, ButtonSpec, ...)."""
    if not dataclasses.is_dataclass(obj):
        return ()
    fields = []
    for f in dataclasses.fields(obj):
        try:
            value = getattr(obj, f.name)
        except Exception:
            continue
        fields.append(
            InspectField(
                name=f.name if label is None else f"{label}.{f.name}",
                value=value,
                kind=kind_of(value),
            )
        )
    return tuple(fields)


def from_getters(
    widget: QWidget,
    pairs: Iterable[tuple[str, str | Callable[[QWidget], Any]] | tuple[str, str | Callable[[QWidget], Any], bool]],
) -> tuple[InspectField, ...]:
    """State from existing runtime getters / public attrs.

    ``pairs`` maps a docs-vocabulary name to either an attribute/method name
    or a callable invoked with the widget. A third element marks the field as
    read from a private attribute. Exceptions are guarded (a failing getter
    yields no field rather than breaking the whole inspection).
    """
    out: list[InspectField] = []
    for entry in pairs:
        if len(entry) == 3:
            docs_name, source, private = entry
        else:
            docs_name, source = entry
            private = False
        try:
            if callable(source) and not isinstance(source, str):
                value = source(widget)
            else:
                value = getattr(widget, source)
                if callable(value) and not isinstance(value, QWidget):
                    value = value()
        except Exception:
            continue
        if value is None:
            continue
        out.append(
            InspectField(
                name=docs_name, value=value, kind=kind_of(value), private=private
            )
        )
    return tuple(out)


def from_qt_props(
    widget: QWidget, *, exclude: Iterable[str] = ()
) -> tuple[InspectField, ...]:
    """Qt dynamic properties (toolkit mirrors config as dynamic props)."""
    exclude_set = set(exclude) | {"_ui_inspector_owned"}
    out: list[InspectField] = []
    for raw in widget.dynamicPropertyNames():
        name = bytes(raw).decode()
        if name.startswith("qt_") or name in exclude_set:
            continue
        try:
            value = widget.property(name)
        except Exception:
            continue
        if value is None:
            continue
        out.append(InspectField(name=name, value=value, kind=kind_of(value)))
    return tuple(out)


def from_regions(button: QWidget) -> tuple[InspectRegion, ...]:
    """Button-family regions with live geometry and per-region states."""
    regions = getattr(button, "regions", None)
    if not callable(regions):
        return ()
    rects = getattr(button, "_region_rects", None) or {}
    region_states = getattr(button, "region_states", None)
    out: list[InspectRegion] = []
    for region in regions():
        states = frozenset()
        if callable(region_states):
            try:
                states = frozenset(region_states(region.id))
            except Exception:
                states = frozenset()
        out.append(
            InspectRegion(
                id=region.id,
                rect=rects.get(region.id),
                states=states,
                weight=getattr(region, "weight", 1.0),
                group=getattr(region, "group", None),
                z_index=getattr(region, "z_index", 0),
                corner_radii=getattr(region, "corner_radii", None),
                icon_size_px=getattr(region, "icon_size_px", None),
                rows=tuple(getattr(region, "rows", None) or ()),
                override_bg=getattr(region, "override_bg_color", None),
                bg_locked=bool(getattr(region, "bg_locked", False)),
                enabled=bool(getattr(region, "enabled", True)),
            )
        )
    return tuple(out)


def from_layers(button: QWidget) -> tuple[InspectLayer, ...]:
    """Active painter layers (``Painter.layers``)."""
    painter = getattr(button, "_painter", None)
    if painter is None:
        return ()
    layers = getattr(painter, "layers", ()) or ()
    return tuple(
        InspectLayer(
            name=type(layer).__name__,
            scope=str(getattr(layer, "scope", "region")),
        )
        for layer in layers
    )


__all__ = [
    "from_dataclass",
    "from_getters",
    "from_init_kwargs",
    "from_layers",
    "from_qt_props",
    "from_regions",
    "kind_of",
]
