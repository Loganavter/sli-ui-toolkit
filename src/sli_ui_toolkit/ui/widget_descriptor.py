"""Unified widget self-description.

Single source of truth that replaces three parallel systems:

- ``InspectSpec`` (UI inspector) → ``inspect`` section
- ``NavigationSpec`` (arrow-key nav) → ``navigation`` section
- ``ActionTarget`` / ``ActionDescriptor`` (command palette) → ``action`` section

Widget classes attach a ``WidgetDescriptor`` as a class attribute::

    class MyWidget(QWidget):
        widget_descriptor = WidgetDescriptor(
            family="MyWidget",
            label="My Widget",
            inspect=InspectSection(state=(...)),
            navigation=NavigationSection(navigate=..., focus_first=...),
            action=ActionSection(run=..., shortcut="Ctrl+M"),
        )

``WidgetRegistry`` collects all descriptors and provides unified lookup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Sections — optional subsections of a WidgetDescriptor
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InspectSection:
    """What the UI inspector needs to know about this widget."""

    config: tuple[Any, ...] = ()
    config_exclude: tuple[str, ...] = ()
    state: tuple[Any, ...] = ()
    token_family: tuple[str, ...] = ()
    regions: bool = False
    layers: bool = False
    docs: str = ""
    preview_seed: Callable[[Any, Any], None] | None = None
    apply_config_refresh: Callable[[Any, tuple[str, ...]], None] | None = None


@dataclass(frozen=True, slots=True)
class NavigationSection:
    """How arrow-key navigation works within this widget.

    ``navigate(key, widget)``: handle arrow key while *widget* is focused.
    Return True if consumed, False to yield to adjacent section.
    """

    navigate: Callable[[int, QObject], bool]
    focus_first: Callable[[], bool]
    focus_last: Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ActionSection:
    """What the command palette needs to know to find and execute this widget."""

    action_id: str = ""
    label: str = ""
    shortcut: str = ""
    run: Callable[[], None] | None = None
    ensure_visible: Callable[[], None] | None = None
    search_terms: tuple[str, ...] = ()
    help_page: str | None = None
    help_anchor: str | None = None


# ------------------------------------------------------------------
# Unified descriptor
# ------------------------------------------------------------------


@dataclass(slots=True)
class WidgetDescriptor:
    """Unified self-description attached to a widget class.

    At minimum, declare ``family``.  Add sections as needed — each system
    (inspector, navigation, palette) reads only its own section.
    """

    #: Unique family name (e.g. "Button", "AdaptiveTabStrip").
    family: str

    #: Human-readable label for command palette / search.
    label: str = ""

    #: Inspector section — state/config for the UI inspector.
    inspect: InspectSection | None = None

    #: Navigation section — arrow-key routing.
    navigation: NavigationSection | None = None

    #: Action section — command palette / shortcut.
    action: ActionSection | None = None

    # ---- backward-compat helpers ------------------------------------

    @classmethod
    def from_inspect_spec(cls, spec: Any) -> WidgetDescriptor:
        """Create from legacy ``InspectSpec``."""
        return cls(
            family=spec.family,
            inspect=InspectSection(
                config=spec.config,
                config_exclude=spec.config_exclude,
                state=spec.state,
                token_family=spec.token_family,
                regions=spec.regions,
                layers=spec.layers,
                docs=spec.docs,
                preview_seed=spec.preview_seed,
                apply_config_refresh=spec.apply_config_refresh,
            ),
        )


# ------------------------------------------------------------------
# Global registry
# ------------------------------------------------------------------


class WidgetRegistry:
    """Process-wide registry of widget descriptors.

    Widgets register themselves (usually at class definition time).
    Consumers (inspector, navigation, palette) query the registry.
    """

    _instance: WidgetRegistry | None = None

    @classmethod
    def get_instance(cls) -> WidgetRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._descriptors: dict[str, WidgetDescriptor] = {}
        self._by_class: dict[type, WidgetDescriptor] = {}
        self._inspect_cache: dict[type, WidgetDescriptor] = {}

    def register(self, widget_class: type, descriptor: WidgetDescriptor) -> None:
        self._descriptors[descriptor.family] = descriptor
        self._by_class[widget_class] = descriptor

    def unregister(self, family: str) -> None:
        self._descriptors.pop(family, None)
        self._by_class = {k: v for k, v in self._by_class.items() if v.family != family}

    def get(self, family: str) -> WidgetDescriptor | None:
        return self._descriptors.get(family)

    def get_for_class(self, widget_class: type) -> WidgetDescriptor | None:
        """Return the descriptor for *widget_class*.

        Checks in order:
        1. Explicitly registered descriptor (``@widget_descriptor``)
        2. Instance-level ``widget_descriptor`` attribute (set in ``__init__``)
        3. Legacy ``inspect_spec`` → auto-converted to ``WidgetDescriptor``
        """
        # 1. Explicit registration
        desc = self._by_class.get(widget_class)
        if desc is not None:
            return desc

        # 2. Class-level inspect_spec → auto-convert
        inspect_spec = getattr(widget_class, "inspect_spec", None)
        if inspect_spec is not None:
            cached = self._inspect_cache.get(widget_class)
            if cached is not None:
                return cached
            desc = WidgetDescriptor.from_inspect_spec(inspect_spec)
            self._inspect_cache[widget_class] = desc
            return desc

        return None

    def all_descriptors(self) -> list[WidgetDescriptor]:
        return list(self._descriptors.values())

    def navigable(self) -> list[tuple[str, WidgetDescriptor]]:
        """All descriptors with a navigation section, in registration order."""
        return [
            (family, desc)
            for family, desc in self._descriptors.items()
            if desc.navigation is not None
        ]

    def searchable(self) -> list[tuple[str, WidgetDescriptor]]:
        """All descriptors with an action section, for command palette."""
        return [
            (family, desc)
            for family, desc in self._descriptors.items()
            if desc.action is not None and desc.action.run is not None
        ]


# ------------------------------------------------------------------
# Decorator for easy registration
# ------------------------------------------------------------------


def widget_descriptor(descriptor: WidgetDescriptor) -> Callable[[type], type]:
    """Class decorator that registers a ``WidgetDescriptor``.

    Usage::

        @widget_descriptor(WidgetDescriptor(
            family="MyWidget",
            navigation=NavigationSection(...),
        ))
        class MyWidget(QWidget):
            ...
    """
    def decorator(cls: type) -> type:
        WidgetRegistry.get_instance().register(cls, descriptor)
        # Also attach as class attribute for MRO-based lookup
        cls.widget_descriptor = descriptor
        return cls
    return decorator
