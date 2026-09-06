"""BaseFlyout surface style — the flyout's own visual API.

Same shape as Button's style_api.py: a plain setter storing an instance
override, ``None`` falls back to the theme token, and the setter repaints.
No QSS/property dispatch here (unlike Button) because BaseFlyout doesn't
expose Qt Designer-style dynamic properties — these are plain Python
attributes.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.in_window_surface import paint_shadowed_surface
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path


class _FlyoutStyleApi:
    """Mixin: flyout panel fill / border / shadow + the shell paint.

    Not a QWidget itself — mixed into BaseFlyout; relies on instance
    attributes assigned in ``BaseFlyout.__init__`` (``_background_brush``,
    ``_border_color_override``, ``_shadow_color``, ``_gpu_fill``,
    ``theme_manager``, ``container``) and on QWidget methods (update).
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real assignments live in BaseFlyout.__init__ (widget.py) or on
    # QWidget itself. Plain annotations only (no `= value`); QWidget-provided
    # names are ``Any`` (a precise Callable would clash with QWidget's own
    # definition when the mixin precedes it in the MRO).
    update: Any
    container: Any
    theme_manager: Any
    _gpu_fill: Any
    _fade: Any
    _background_brush: QBrush | None
    _border_color_override: QColor | None
    _shadow_color: QColor | None

    def _apply_base_style(self):
        self.container.style().unpolish(self.container)
        self.container.style().polish(self.container)
        self.container.update()

    def set_background_brush(self, brush: QBrush | QColor | None) -> None:
        """Override the flyout panel's fill.

        Accepts a flat ``QColor`` (solid override) or any ``QBrush`` —
        a ``QLinearGradient``/``QRadialGradient`` for a glass-style tint,
        or ``QBrush(QPixmap(...))`` to stretch a custom texture. Pass
        ``None`` to go back to the ``flyout.background`` theme token.
        """
        self._background_brush = (
            QBrush(brush) if brush is not None and not isinstance(brush, QBrush) else brush
        )
        if self._gpu_fill is not None:
            brush = self._background_brush
            solid = brush is not None and brush.style() == Qt.BrushStyle.SolidPattern
            self._gpu_fill.setVisible(solid)
            if solid and brush is not None:
                self._gpu_fill.set_fill_color(brush.color())
        self.update()

    def background_brush(self) -> QBrush | None:
        return self._background_brush

    def set_border_color(self, color: QColor | None) -> None:
        """Override the panel's stroke color; ``None`` restores ``flyout.border``."""
        self._border_color_override = QColor(color) if color is not None else None
        self.update()

    def border_color(self) -> QColor | None:
        return self._border_color_override

    def set_shadow_color(self, color: QColor | None) -> None:
        """Tint the drop shadow (e.g. an accent-colored glow); ``None`` restores
        the default black shadow. Only RGB is used — alpha falloff is
        computed by the shadow painter, not taken from ``color``."""
        self._shadow_color = QColor(color) if color is not None else None
        self.update()

    def shadow_color(self) -> QColor | None:
        return self._shadow_color

    def paintEvent(self, event):
        if self._fade.cache is not None and self._fade.opacity < 1.0:
            # Fade by compositing the pre-rendered snapshot with the current
            # opacity. The snapshot is captured once, outside paintEvent (see
            # _capture_fade_cache), so no QWidget.render()/repaint happens
            # during paint — that would recurse on composited windows
            # ("Recursive repaint detected"). Deliberately no QGraphicsEffect
            # either (nested-effect / double-begin conflicts), and in-window
            # flyouts are plain child widgets, so windowOpacity() would not
            # work.
            painter = QPainter(self)
            painter.setOpacity(self._fade.opacity)
            painter.drawPixmap(0, 0, self._fade.cache)
            painter.end()
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_shadowed_surface(
            painter,
            self.container.geometry(),
            shadow_radius=self.SHADOW_RADIUS,
            corner_radius=self.CONTENT_RADIUS,
            shadow_color=self._shadow_color,
        )
        rect = QRectF(self.container.geometry())
        stroke_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        r = self.CONTENT_RADIUS
        path = rounded_rect_path(stroke_rect, (r, r, r, r))
        background = self._background_brush or QBrush(
            self.theme_manager.get_color("flyout.background")
        )
        border = self._border_color_override or self.theme_manager.get_color(
            "flyout.border"
        )
        # A visible _gpu_fill already painted this frame's solid fill via its
        # own QRhi pass (see set_background_brush) -- painting it again here
        # would just be redundant CPU work under the same rounded clip.
        gpu_fill_active = self._gpu_fill is not None and self._gpu_fill.isVisible()
        # Anchor texture/gradient brushes to the panel's own corner instead
        # of (0, 0) of the flyout widget (which is inset by the shadow
        # margin), so a custom texture lines up with the visible panel.
        painter.setBrushOrigin(stroke_rect.topLeft())
        painter.setBrush(Qt.BrushStyle.NoBrush if gpu_fill_active else background)
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)
        painter.end()
