"""FlyoutManager contract — the hit-testing / trigger surface of BaseFlyout.

The manager's app-wide event filter asks every open flyout these questions
(is the cursor inside you / your anchor / your trigger?), and consults
``restore_focus_on_hide`` when deciding whether closing should hand focus
back to the host window. Kept as one mixin so the contract is visible in a
single module.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QWidget


class _FlyoutManagerApi:
    """Mixin: the surface FlyoutManager's event filter relies on.

    Not a QWidget itself — mixed into BaseFlyout; relies on instance state
    (``overlay_layer``, ``_anchor_widget``) and QWidget methods (isVisible,
    rect, mapFromGlobal, mapToGlobal, size).
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real values are assigned in BaseFlyout.__init__ (widget.py) or
    # live on QWidget itself (later in the MRO).
    overlay_layer: Any
    isVisible: Any
    rect: Any
    mapFromGlobal: Any
    mapToGlobal: Any
    size: Any

    def contains_global(self, global_pos) -> bool:
        if not self.isVisible():
            return False
        if self.overlay_layer is not None and hasattr(self.overlay_layer, "contains_global"):
            return self.overlay_layer.contains_global(self, global_pos)
        return self.rect().contains(self.mapFromGlobal(global_pos))

    def anchor_contains_global(self, global_pos) -> bool:
        anchor = getattr(self, "_anchor_widget", None)
        if anchor is None:
            return False
        try:
            anchor_top_left = anchor.mapToGlobal(QPoint(0, 0))
            return QRect(anchor_top_left, anchor.size()).contains(global_pos)
        except RuntimeError:
            return False

    def anchor_widgets(self) -> tuple[QWidget, ...]:
        anchor = getattr(self, "_anchor_widget", None)
        return (anchor,) if isinstance(anchor, QWidget) else ()

    def trigger_widgets(self) -> tuple[QWidget, ...]:
        """Widgets whose click toggles this flyout closed while it's open.

        Defaults to :meth:`anchor_widgets` -- for a typical flyout (dropdown,
        context menu) the anchor *is* the trigger button, so clicking it
        again while open should dismiss instead of reopening.

        Override to return ``()`` (or a narrower subset) when the anchor is
        used purely for positioning against a widget that isn't itself a
        click-to-toggle trigger -- e.g. a hover-driven flyout anchored to a
        whole button group for width/placement. Left coupled to
        ``anchor_widgets()`` by default, FlyoutManager's click-on-anchor
        heuristic (see its ``eventFilter``) would misread a click on any
        *sibling* button in that group as "clicked the trigger, dismiss".
        """
        return self.anchor_widgets()

    def trigger_contains_global(self, global_pos) -> bool:
        for widget in self.trigger_widgets():
            try:
                top_left = widget.mapToGlobal(QPoint(0, 0))
                if QRect(top_left, widget.size()).contains(global_pos):
                    return True
            except RuntimeError:
                continue
        return False

    def restore_focus_on_hide(self) -> bool:
        """Whether hide() should shove focus back onto the host window.

        Context menus return False: activateWindow/setFocus on Wayland can
        re-enter focusChanged handlers and visually jerk QRhi canvases.
        """
        return True
