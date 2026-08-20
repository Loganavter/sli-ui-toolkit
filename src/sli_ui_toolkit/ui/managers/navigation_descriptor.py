"""Bridge between ``WidgetDescriptor.navigation`` and ``NavigationManager``.

Kept out of ``navigation_manager.py`` (already large) and out of
``widget_descriptor.py`` (which must stay free of a hard runtime dependency
on the navigation manager — it only needs the ``NavigationSection`` type for
annotations, see its ``TYPE_CHECKING`` import).
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.widget_descriptor import WidgetRegistry


def register_navigation(owner: QObject) -> bool:
    """Register *owner*'s ``WidgetDescriptor.navigation`` section, if any.

    Checks an instance-level ``owner.widget_descriptor`` attribute first
    (a page/toolbar built per-instance, e.g. a settings page's dynamically
    assembled row list, can override whatever its class declares), then
    falls back to ``WidgetRegistry.get_for_class(type(owner))`` (the
    ``@widget_descriptor``-registered class-level descriptor) — the
    registry itself does not implement this instance-level step (only the
    legacy ``inspect_spec`` gets a class-level auto-convert), so it's done
    here instead.

    Returns ``True`` if a section was found and registered with
    ``NavigationManager``, ``False`` if *owner* has no navigation
    descriptor at all — never raises, so callers that don't participate in
    navigation can call this unconditionally.
    """
    descriptor = getattr(owner, "widget_descriptor", None)
    if descriptor is None or descriptor.navigation is None:
        descriptor = WidgetRegistry.get_instance().get_for_class(type(owner))
    if descriptor is None or descriptor.navigation is None:
        return False
    NavigationManager.get_instance().register(owner, descriptor.navigation)
    return True
