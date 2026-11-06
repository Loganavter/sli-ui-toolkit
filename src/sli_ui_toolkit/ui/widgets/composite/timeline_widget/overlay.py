"""The playhead/selection overlay that sits ABOVE the GPU filmstrip band.

Why this widget exists: a child widget composites above all of the parent's
``QPainter`` passes, so the band (``strip_band.py``) hides anything the
timeline paints across the strip row — the playhead line and the selection
wash. The renderer that draws the tiles cannot be made responsible for the
chrome: it belongs to the host, and the chrome belongs to the toolkit. So the
toolkit raises one more child over the band and paints those two things
itself, with the parent's own code.

What it draws (and only this): the selection wash (with its edge handles and
strip grips) and the playhead line — both through
``render.paint_selection_wash`` / ``render.paint_playhead``, the same
functions the parent pass calls, with the same culling. Everything else
(tiles, gutter, rows, ruler, scrollbars) stays where it was.

Geometry: :meth:`set_band_rect` tracks the band's rect (the timeline's
:meth:`TimelineWidget.sync_strip_band` places it from ``band.band_rect()``, so
both children share the single geometry owner, ``viewport.content_geometry``),
and the paint translates its painter onto that CONTENT frame — the same frame
the parent pass paints in. No local ``scroll`` arithmetic here.

Input: the overlay is paint-only — ``WA_TransparentForMouseEvents`` and no
focus policy — so hit-testing, wheel zoom and scrub stay on the timeline
underneath. It is shown only while the band is on screen and is destroyed with
the band.

Compositing note: offscreen tests can prove the widget tree, the geometry and
the paint calls, not the composited pixels (the band is GPU-composited); the
live capture is what proves the stacking on a real window.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QPaintEvent, QPainter
from PySide6.QtWidgets import QWidget

from . import render as timeline_render
from . import viewport as timeline_viewport


class TimelineOverlay(QWidget):
    """Paint-only sibling above the filmstrip band (playhead + selection).

    Child of the timeline widget, placed exactly over the band's rect. The
    parent owns creation/placement/visibility (``TimelineWidget``); this class
    owns its attributes and its paint pass.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        # ``parent`` is the TimelineWidget; typed Any so this module needs no
        # import of widget.py (widget.py imports this module).
        self._timeline: Any = parent
        # Translucent: only the two painted elements may show, the band's
        # tiles underneath must survive everywhere else.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Paint-only: the timeline keeps hit-testing (scrub, wheel zoom).
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(False)
        self._band_rect = QRect()
        self.hide()

    def set_band_rect(self, rect: QRect | QRectF) -> None:
        """Track the band's area (timeline/parent coordinates) and repaint."""
        area = rect.toRect() if isinstance(rect, QRectF) else QRect(rect)
        if area == self._band_rect:
            return
        self._band_rect = area
        self.setGeometry(area)
        self.update()

    def band_rect(self) -> QRect:
        """The tracked band area, in the parent's (content) coordinates."""
        return QRect(self._band_rect)

    def paintEvent(self, event: QPaintEvent) -> None:
        timeline = self._timeline
        if timeline is None or not timeline.strip_band_active():
            return
        geo = timeline_viewport.content_geometry(timeline)
        band = geo.band_rect
        if band.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # CONTENT frame -> this child's local frame. The band rect carries the
        # scroll offset (its geometry is content coordinates), so it is the
        # whole conversion: the playhead/selection code then runs unchanged.
        painter.translate(-band.left(), -band.top())
        start_x = float(band.left())
        end_x = float(band.right())
        timeline_render.paint_selection_wash(
            timeline, painter, geo, start_x=start_x, end_x=end_x
        )
        timeline_render.paint_playhead(
            timeline, painter, geo, start_x=start_x, end_x=end_x
        )
        painter.end()
