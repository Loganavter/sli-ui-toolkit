"""Overlay lifecycle/geometry coordination for ``InspectorController`` — split
out to keep that class down to event dispatch + selection state, mirroring
the thin-owner pattern already used in ``code/apply.py``. Functions here take
the controller as their first argument and read/write its ``_overlays`` /
``_active_overlay`` state directly. Distinct from ``overlay.py``, which holds
the ``InspectorOverlay`` *widget* itself — this module only coordinates when
and where that widget is created, shown, and targeted.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from .overlay import InspectorOverlay
from .registry import inspect_widget

logger = logging.getLogger("sli_ui_toolkit.inspector")


def refresh_overlay(controller) -> None:
    if controller._overlay_suspended:
        # The highlight is hidden while the user works in the inspected
        # window — tree hovers / region clicks / refresh paths must not
        # silently re-light it (that made the highlight look "stuck").
        logger.debug(
            "overlay refresh skipped (suspended; hover=%s committed=%s)",
            type(controller._hover_widget).__name__
            if controller._hover_widget is not None
            else None,
            type(controller._committed_widget).__name__
            if controller._committed_widget is not None
            else None,
        )
        return
    target = controller._hover_widget or controller._committed_widget
    if not controller._is_valid_widget(target):
        controller._reset_selection()
        return
    overlay = overlay_for(controller, target.window())
    rect = _map_widget_rect(target, overlay.parentWidget())
    label = controller._label_for(target)
    if controller._active_overlay is not None and controller._active_overlay is not overlay:
        controller._active_overlay.clear_target()
        controller._active_overlay.hide()
    controller._active_overlay = overlay
    overlay.set_target(rect, label)
    overlay.set_regions(mapped_regions(controller, target, overlay), controller._hovered_region)


def mapped_regions(controller, widget: QWidget, overlay: InspectorOverlay):
    if controller._hover_widget is not widget and controller._committed_widget is not widget:
        return []
    try:
        inspection = inspect_widget(widget, controller._theme_manager)
    except Exception:
        return []
    if not inspection.regions:
        return []
    origin = widget.mapTo(overlay.parentWidget(), QPoint(0, 0))
    out = []
    for region in inspection.regions:
        if region.rect is None:
            continue
        out.append((region.id, region.rect.translated(origin)))
    return out


def clear_active_overlay(controller) -> None:
    overlay = controller._active_overlay
    controller._active_overlay = None
    if overlay is None:
        return
    try:
        overlay.clear_target()
        overlay.hide()
    except RuntimeError:
        pass


def overlay_for(controller, window: QWidget) -> InspectorOverlay:
    overlay = controller._overlays.get(window)
    if overlay is None:
        overlay = InspectorOverlay(window)
        controller._overlays[window] = overlay
        window.installEventFilter(controller)
    overlay.setGeometry(window.rect())
    overlay.raise_()
    return overlay


def sync_overlay_for(controller, widget: QWidget) -> None:
    overlay = controller._overlays.get(widget)
    if overlay is None:
        return
    try:
        overlay.setGeometry(widget.rect())
        overlay.raise_()
    except RuntimeError:
        pass


def hide_overlays(controller) -> None:
    for overlay in controller._overlays.values():
        try:
            overlay.hide()
        except RuntimeError:
            pass
    controller._active_overlay = None


def _map_widget_rect(widget: QWidget, target_parent: QWidget):
    top_left = widget.mapTo(target_parent, QPoint(0, 0))
    return widget.rect().translated(top_left)
