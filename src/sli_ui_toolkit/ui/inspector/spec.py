"""Declarative inspection specs — widgets self-describe.

Instead of the inspector guessing (duck-typed matchers, match order), every
widget family can carry an ``InspectSpec`` class attribute: the family name,
the ``__init__`` kwargs to surface as config (read automatically from the
instance), the runtime state fields with human labels, the static token
family, and flags for Button-family extras (regions/layers).

``inspect_widget`` prefers the spec when present; the duck-typed registry
stays as fallback for widgets without one (e.g. app widgets before they
migrate), and the generic QWidget fallback guarantees everything is
inspectable.

Import note: this module imports only PySide6 + the contract — widget
modules can import it without cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Union

from PySide6.QtWidgets import QWidget

from .contract import WidgetInspection
from .extract import (
    _read_attr,
    from_layers,
    from_regions,
    kind_of,
)

# Lazy import to avoid circular dependency
_InspectSection = None


def _get_inspect_section():
    global _InspectSection
    if _InspectSection is None:
        from sli_ui_toolkit.ui.widget_descriptor import InspectSection
        _InspectSection = InspectSection
    return _InspectSection


@dataclass(slots=True)
class SpecField:
    """One config/state field of a widget's inspection spec.

    ``source`` is an attribute/method name (called when callable) or a
    zero-arg callable returning the display value; it defaults to ``label``.
    ``private`` marks values read from a private attribute (legal here — the
    spec sits next to the widget definition).
    """

    label: str
    source: str | Callable[[QWidget], Any] = ""
    private: bool = False


@dataclass(slots=True)
class InspectSpec:
    """Self-description attached to a widget class as ``inspect_spec``.

    ``config`` is optional: when empty it is auto-derived from the widget's
    ``__init__`` signature (the biggest drift risk is therefore never
    declared). Explicit entries are used verbatim when curation is needed
    (noisy internals such as Button's region/layer plumbing).
    """

    family: str
    config: tuple[SpecField, ...] = ()
    config_exclude: tuple[str, ...] = ()
    state: tuple[SpecField, ...] = ()
    token_family: tuple[str, ...] = ()
    regions: bool = False  # Button-family regions/states/rects
    layers: bool = False  # active painter layers
    #: documentation reference for the widget family — a path to the docs
    #: file (e.g. ``docs/user/BUTTON_API.md``, repo-relative or absolute).
    #: Surfaced in the inspector's Object section as a clickable row and
    #: carried on ``WidgetInspection.docs`` for host apps to reuse (e.g.
    #: a "help for this widget" entry in the app's own UI).
    docs: str = ""
    #: optional ``(preview, live) -> None`` hook: reproduces the live
    #: widget's runtime state (tabs, selection, rows, ...) onto a freshly
    #: built preview instance. The config snippet carries construction
    #: values only — without a seed, stateful composites (e.g. a tab strip)
    #: preview as empty shells. Inherited through the MRO like the spec.
    preview_seed: Callable[[QWidget, QWidget], None] | None = None
    #: optional ``(live, applied_names) -> None`` hook: re-runs the layout/
    #: refresh passes that ``__init__`` normally performs, so config
    #: snippet values written onto the live instance actually take effect
    #: (e.g. the tab strip re-syncs margins/spacing and rebuilds its
    #: close buttons). Without it, attribute writes + repaint are all the
    #: generic Apply can do — layout-affected values would appear inert.
    apply_config_refresh: Callable[[QWidget, tuple[str, ...]], None] | None = None


def _resolve_field(widget: QWidget, field: SpecField):
    source = field.source or field.label
    try:
        if callable(source) and not isinstance(source, str):
            return source(widget), field.private
        resolved = _read_attr(widget, source)
        if resolved is not None:
            return resolved
        value = getattr(widget, source)
        if callable(value) and not isinstance(value, QWidget):
            value = value()
        return value, field.private
    except Exception:
        return None


def build_inspection(
    widget: QWidget, spec: InspectSpec | Any, theme_manager=None
) -> WidgetInspection:
    """Build a ``WidgetInspection`` from a widget's spec.

    Accepts either ``InspectSpec`` (legacy) or ``InspectSection`` (new
    ``WidgetDescriptor`` system) — both have the same field shape.

    Config auto-derives from the ``__init__`` signature when the spec
    declares none (with ``config_exclude`` honoured), so constructor changes
    never drift from the inspection.
    """
    from .contract import InspectField
    from .extract import from_init_kwargs

    if spec.config:
        config_specs = spec.config
        config: list = []
        for field in config_specs:
            resolved = _resolve_field(widget, field)
            if resolved is None:
                continue
            value, private = resolved
            if value is None:
                continue
            config.append(
                InspectField(
                    name=field.label,
                    value=value,
                    kind=kind_of(value),
                    private=bool(private or field.private),
                )
            )
    else:
        config = list(
            from_init_kwargs(widget, exclude=spec.config_exclude or ())
        )

    state: list = []
    for field in spec.state:
        resolved = _resolve_field(widget, field)
        if resolved is None:
            continue
        value, private = resolved
        if value is None:
            continue
        state.append(
            InspectField(
                name=field.label,
                value=value,
                kind=kind_of(value),
                private=bool(private or field.private),
            )
        )

    return WidgetInspection(
        family=spec.family,
        config=tuple(config),
        state=tuple(state),
        token_family=spec.token_family,
        regions=from_regions(widget) if spec.regions else (),
        layers=from_layers(widget) if spec.layers else (),
        docs=spec.docs,
    )


def docs_for(widget: QWidget) -> str:
    """The effective docs reference for ``widget`` (MRO-inherited), or
    ``""`` when the widget carries no spec (or its spec has none).

    Host apps can use this to show "documentation for this widget" entries
    without re-deriving the mapping themselves.
    """
    spec = spec_of(widget)
    return spec.docs if spec is not None else ""


def _resolve_docs_path(ref: str) -> str:
    """Resolve a docs reference to a filesystem path.

    Absolute refs are used as-is; relative refs resolve against the
    toolkit repository root first (the nearest ancestor of the installed
    package that carries a ``docs/`` directory — for an editable src-layout
    install that is the repo root, wherever the app runs from), then the
    current working directory (for app-side refs). The best guess is
    returned even when nothing exists — the system editor then reports
    the miss.
    """
    from pathlib import Path

    candidate = Path(ref)
    if candidate.is_absolute():
        return str(candidate)
    bases: list[Path] = []
    try:
        import sli_ui_toolkit

        pkg_dir = Path(sli_ui_toolkit.__file__).resolve().parent
        for ancestor in (pkg_dir, *pkg_dir.parents):
            if (ancestor / "docs").is_dir():
                bases.append(ancestor)
                break
    except Exception:
        pass
    bases.append(Path.cwd())
    for base in bases:
        hit = base / ref
        if hit.exists():
            return str(hit)
    return str(bases[-1] / ref)


def spec_of(widget: QWidget) -> InspectSpec | InspectSection | None:
    """The effective spec for ``widget``.

    Resolution order:
    1. Instance ``widget_descriptor`` attribute (set in ``__init__``)
    2. Own-class ``inspect_spec`` (class attribute, not inherited)
    3. MRO ``inspect_spec`` (legacy, inherited)
    4. MRO ``widget_descriptor.inspect`` (new system, inherited)
    """
    InspectSection = _get_inspect_section()

    # 1. Instance-level widget_descriptor
    desc = widget.__dict__.get("widget_descriptor")
    if desc is not None:
        inspect = getattr(desc, "inspect", None)
        if inspect is not None:
            return inspect

    # 2-3. inspect_spec — check each class in MRO (own class first)
    for cls in type(widget).__mro__:
        spec = cls.__dict__.get("inspect_spec")
        if isinstance(spec, (InspectSpec, InspectSection)):
            return spec

    # 4. widget_descriptor.inspect — check each class in MRO
    for cls in type(widget).__mro__:
        desc = cls.__dict__.get("widget_descriptor")
        if desc is not None:
            inspect = getattr(desc, "inspect", None)
            if inspect is not None:
                return inspect

    return None


def preview_seed_for(widget: QWidget) -> Callable[[QWidget, QWidget], None] | None:
    """The effective preview-seed callable for ``widget`` (MRO-inherited).

    ``None`` when the widget carries no spec (or its spec has no seed) —
    the preview then shows the config-built widget as-is.
    """
    spec = spec_of(widget)
    return spec.preview_seed if spec is not None else None


def apply_config_refresh_for(
    widget: QWidget,
) -> Callable[[QWidget, tuple[str, ...]], None] | None:
    """The effective config-apply refresh hook for ``widget``
    (MRO-inherited), or ``None`` when the spec declares none — Apply then
    falls back to plain attribute writes + repaint."""
    spec = spec_of(widget)
    return spec.apply_config_refresh if spec is not None else None


__all__ = [
    "InspectSpec",
    "SpecField",
    "build_inspection",
    "spec_of",
    "docs_for",
    "preview_seed_for",
    "apply_config_refresh_for",
]
