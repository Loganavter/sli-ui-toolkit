"""ListPanel surface styling — split out of ``widget.py`` to keep the
facade thin, matching the ``appearance.py`` precedent used in
``ui/windows/custom_title_bar/``. Functions take the panel as their first
argument.

The panel surface is painted with ``QPainter`` (never QSS — the painter
pipeline owns all toolkit-widget visuals per AGENTS.md): a small
per-panel event filter paints the rounded ``surface.background`` fill +
1 px ``flyout.border`` frame, resolving both tokens live at paint time so
``theme_changed`` only needs an ``update()``. The scroll area viewport
and content widget are pinned transparent via attributes (same trick as
``SurfaceScrollArea._pin_content_transparent``), so the painted panel
surface shows through the content gaps.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPen

#: Panel corner radius, matching ``OverlayScrollArea``'s content mask.
PANEL_RADIUS = 8


class _PanelSurfaceFilter(QObject):
    """Paints the panel's rounded surface on ``QEvent.Paint``.

    Installed once per panel by :func:`apply_style` (guarded by the
    ``_sli_surface_filter`` dynamic property). Runs before the panel's own
    ``paintEvent`` — which is a no-op once ``WA_StyledBackground`` is off —
    and beneath all child widgets, so it is strictly the background layer.
    """

    def __init__(self, panel) -> None:
        super().__init__(panel)
        self._panel = panel

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self._panel and event.type() == QEvent.Type.Paint:
            self._paint_surface()
        return False

    def _paint_surface(self) -> None:
        panel = self._panel
        try:
            bg = QColor(panel.theme_manager.get_color("surface.background"))
            border = QColor(panel.theme_manager.get_color("flyout.border"))
        except Exception:
            return
        if not bg.isValid():
            return
        painter = QPainter(panel)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = panel.rect().adjusted(0, 0, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
        if border.isValid():
            painter.setPen(QPen(border, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
        painter.end()


def _ensure_surface_filter(panel) -> None:
    if panel.property("_sli_surface_filter") is True:
        return
    try:
        # No stylesheet → the styled-background fill must go off, or the
        # default paintEvent would fight the filter with a palette fill.
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
    except Exception:
        pass
    panel.installEventFilter(_PanelSurfaceFilter(panel))
    panel.setProperty("_sli_surface_filter", True)


def _pin_content_transparent(panel) -> None:
    """Pin scroll viewport + content transparent (attribute, never QSS)."""
    try:
        viewport = panel.scroll_area.viewport()
        if viewport is not None:
            viewport.setAutoFillBackground(False)
    except Exception:
        pass
    try:
        panel.content_widget.setAutoFillBackground(False)
    except Exception:
        pass


def apply_style(panel) -> None:
    accent = panel.theme_manager.try_get_color("accent")
    if accent is None or not accent.isValid():
        accent = panel.theme_manager.get_color("accent")
    panel.drop_overlay.set_color(accent)

    # Painter path: the surface filter resolves surface/border tokens live
    # at paint time, so theme switches only need a repaint — no stylesheet
    # round-trip, no object-name selectors.
    _ensure_surface_filter(panel)
    _pin_content_transparent(panel)
    try:
        panel.update()
    except Exception:
        pass
