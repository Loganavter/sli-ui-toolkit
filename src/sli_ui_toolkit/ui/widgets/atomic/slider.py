from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, Property
from PySide6.QtGui import QBrush, QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSlider

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin, register_hover_widget

TrackPainter = Callable[[QPainter, QRectF], None]


class Slider(WheelScrollPolicyMixin, QSlider):
    """Rounded-track slider with an animated thumb.

    Supports both orientations (the track/thumb geometry is orientation-aware,
    not just the inherited value semantics), a configurable track thickness
    and thumb radius, and an optional ``track_painter`` hook so callers can
    fill the track with arbitrary content (a gradient, a checkerboard, ...)
    instead of the default flat theme-color track. When a custom painter is
    supplied the usual accent "value fill" overlay can be turned off via
    ``show_value_fill=False`` for content (hue/alpha strips) where the full
    track is always meaningful and there is no "progress" to shade in.
    """

    TRACK_HEIGHT = 5
    RADIUS = 8
    MARGIN = 10

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent=None,
        *,
        wheel_requires_focus: bool = False,
        track_thickness: float | None = None,
        thumb_radius: float | None = None,
        track_painter: TrackPainter | None = None,
        show_value_fill: bool = True,
    ):
        super().__init__(orientation, parent)
        self.init_wheel_scroll_policy(wheel_requires_focus=wheel_requires_focus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hovered = False
        self._pressed = False
        self._track_thickness = float(track_thickness) if track_thickness is not None else float(self.TRACK_HEIGHT)
        self._thumb_radius = float(thumb_radius) if thumb_radius is not None else float(self.RADIUS)
        self._track_painter = track_painter
        self._show_value_fill = bool(show_value_fill)
        self._inner_scale_current = 0.50
        self._inner_anim = QPropertyAnimation(self, b"innerScale", self)
        self._inner_anim.setDuration(140)
        self._inner_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)
        if self.maximum() == 99 and self.minimum() == 0:
            self.setMaximum(100)

        self.valueChanged.connect(self._update_hover_from_cursor)
        register_hover_widget(self)

    def get_inner_scale(self) -> float:
        return self._inner_scale_current

    def set_inner_scale(self, v: float):
        v = max(0.0, min(1.0, float(v)))
        if abs(v - self._inner_scale_current) > 1e-4:
            self._inner_scale_current = v
            self.update()

    innerScale = Property(float, fget=get_inner_scale, fset=set_inner_scale)

    def setTrackThickness(self, px: float) -> None:
        self._track_thickness = max(1.0, float(px))
        self.updateGeometry()
        self.update()

    def trackThickness(self) -> float:
        return self._track_thickness

    def setThumbRadius(self, px: float) -> None:
        self._thumb_radius = max(1.0, float(px))
        self.updateGeometry()
        self.update()

    def thumbRadius(self) -> float:
        return self._thumb_radius

    def setTrackPainter(self, painter_fn: TrackPainter | None) -> None:
        """Paint the track content with ``painter_fn(painter, rect)`` instead of a flat fill.

        ``rect`` is the track's local, already-rounded-corner-clipped groove
        rect (origin at the widget's groove position) — draw into it like any
        other clipped paint operation (gradients, tiled patterns, ...).
        """
        self._track_painter = painter_fn
        self.update()

    def setShowValueFill(self, enabled: bool) -> None:
        self._show_value_fill = bool(enabled)
        self.update()

    def showValueFill(self) -> bool:
        return self._show_value_fill

    def _is_horizontal(self) -> bool:
        return self.orientation() == Qt.Orientation.Horizontal

    def _target_inner_scale(self) -> float:
        if self._pressed:
            return 0.40
        if self._hovered:
            return 0.60
        return 0.50

    def _animate_inner_to_target(self):
        target = self._target_inner_scale()
        if abs(target - self._inner_scale_current) < 1e-4:
            return
        self._inner_anim.stop()
        self._inner_anim.setStartValue(self._inner_scale_current)
        self._inner_anim.setEndValue(target)
        self._inner_anim.start()

    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        fm_h = self.fontMetrics().height()
        pad = 5
        cross = max(
            2 * self._thumb_radius + 2,
            self._track_thickness + 2 * pad,
            fm_h + pad,
        )
        if self._is_horizontal():
            return QSize(base.width(), max(base.height(), int(round(cross))))
        return QSize(max(base.width(), int(round(cross))), base.height())

    def minimumSizeHint(self) -> QSize:
        sh = self.sizeHint()
        if self._is_horizontal():
            return QSize(60, sh.height())
        return QSize(sh.width(), 60)

    def _groove_rect(self) -> QRectF:
        r = self.rect()
        thickness = self._track_thickness
        if self._is_horizontal():
            y = r.center().y() - thickness / 2
            return QRectF(self.MARGIN, y, max(1.0, r.width() - 2 * self.MARGIN), thickness)
        x = r.center().x() - thickness / 2
        return QRectF(x, self.MARGIN, thickness, max(1.0, r.height() - 2 * self.MARGIN))

    def thumbCenter(self) -> QPoint:
        """Public accessor for the thumb's current center, local coordinates."""
        return self._thumb_center()

    def flyoutAnchorRect(self) -> QRect:
        """Narrow flyout anchoring (see ``surface_anchor_rect``) to a small
        square centered on the thumb, instead of the whole track -- a value
        flyout anchored to this widget then tracks the handle as it moves
        along the track rather than staying pinned to the track's center."""
        center = self._thumb_center()
        r = int(round(self._thumb_radius))
        return QRect(center.x() - r, center.y() - r, 2 * r, 2 * r)

    def _thumb_center(self) -> QPoint:
        groove = self._groove_rect()
        span = self.maximum() - self.minimum()
        t = 0.0 if span <= 0 else (self.value() - self.minimum()) / span
        if self._is_horizontal():
            x = groove.left() + groove.width() * t
            return QPoint(int(round(x)), int(round(groove.center().y())))
        # Vertical convention: minimum at the bottom, maximum at the top.
        y = groove.bottom() - groove.height() * t
        return QPoint(int(round(groove.center().x())), int(round(y)))

    def _is_point_in_thumb(self, p: QPoint) -> bool:
        c = self._thumb_center()
        dx = p.x() - c.x()
        dy = p.y() - c.y()
        hit_r = self._thumb_radius + 4
        return (dx * dx + dy * dy) <= (hit_r * hit_r)

    def hoverHitTest(self, pos) -> bool:
        point = pos.toPoint() if hasattr(pos, "toPoint") else pos
        return self._is_point_in_thumb(point)

    def setHoverActive(self, active: bool) -> None:
        active = bool(active)
        if active != self._hovered:
            self._hovered = active
            self._animate_inner_to_target()
            self.update()

    def _update_hover_from_cursor(self):
        pos = self.mapFromGlobal(QCursor.pos())
        new_hovered = self._is_point_in_thumb(pos)
        if new_hovered != self._hovered:
            self._hovered = new_hovered
            self._animate_inner_to_target()
            self.update()

    def event(self, e):
        if e.type() in (QEvent.Type.HoverEnter, QEvent.Type.HoverMove):
            self.setHoverActive(self.hoverHitTest(e.position()))
            return True
        if e.type() == QEvent.Type.HoverLeave:
            self.setHoverActive(False)
            return True
        return super().event(e)

    def _axis_coord(self, pos: QPoint) -> float:
        return pos.x() if self._is_horizontal() else pos.y()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._is_point_in_thumb(e.pos()):
                self._pressed = True
                self._animate_inner_to_target()
                e.accept()
                self.update()
                return
            else:
                self._set_value_from_pos(self._axis_coord(e.pos()))
                self._pressed = True
                self._animate_inner_to_target()
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pressed:
            self._set_value_from_pos(self._axis_coord(e.pos()))
            e.accept()
            self.update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._animate_inner_to_target()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        if not self.shouldHandleWheelEvent(e):
            return

        angle = e.angleDelta()
        # Prefer the horizontal component when present -- a horizontal
        # trackpad swipe or Shift+wheel reports through angleDelta().x(),
        # not .y() -- so both scroll directions drive the slider regardless
        # of its own orientation, same convention as adaptive_tab_strip's
        # wheelEvent.
        delta = angle.x() if angle.x() != 0 else angle.y()
        if delta == 0:
            return
        # //100 (1 notch == 1% of the range) took ~100 notches to cross the
        # whole slider -- //40 (2.5% per notch, 1 physical mouse click ==
        # 120 units) is a full traverse in ~40 clicks instead. Scaled by
        # notch count so higher-resolution wheels/trackpads (which report
        # several hundred units per gesture) still move proportionally, not
        # by a single low-res-mouse-sized step per event.
        step = max(1, (self.maximum() - self.minimum()) // 40)
        notches = max(1, round(abs(delta) / 120))
        step *= notches
        if delta > 0:
            self.setValue(min(self.maximum(), self.value() + step))
        elif delta < 0:
            self.setValue(max(self.minimum(), self.value() - step))
        e.accept()

    def _set_value_from_pos(self, coord: float):
        groove = self._groove_rect()
        if self._is_horizontal():
            span_px = groove.width()
            if span_px <= 0:
                return
            t = (coord - groove.left()) / span_px
        else:
            span_px = groove.height()
            if span_px <= 0:
                return
            t = (groove.bottom() - coord) / span_px
        t = max(0.0, min(1.0, t))
        span = self.maximum() - self.minimum()
        new_val = int(round(self.minimum() + t * span))
        self.setValue(new_val)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        groove = self._groove_rect()
        rectf = groove.adjusted(0.5, 0.5, -0.5, -0.5)
        corner = (rectf.height() if self._is_horizontal() else rectf.width()) / 2.0

        tm = self.theme_manager
        gray = QColor(tm.get_color("dialog.border"))
        accent = QColor(tm.get_color("accent"))

        painter.setPen(Qt.PenStyle.NoPen)
        if self._track_painter is not None:
            painter.save()
            clip_path = QPainterPath()
            clip_path.addRoundedRect(rectf, corner, corner)
            painter.setClipPath(clip_path)
            self._track_painter(painter, rectf)
            painter.restore()
        else:
            base_bg = QColor(tm.get_color("slider.track.unfilled"))
            painter.setBrush(QBrush(base_bg))
            painter.drawRoundedRect(rectf, corner, corner)

        if self._show_value_fill:
            span = max(1, self.maximum() - self.minimum())
            t = (self.value() - self.minimum()) / span
            if t > 0.0:
                painter.save()
                if self._is_horizontal():
                    clip_rect = QRectF(rectf.left(), rectf.top(), rectf.width() * t, rectf.height())
                else:
                    fill_h = rectf.height() * t
                    clip_rect = QRectF(rectf.left(), rectf.bottom() - fill_h, rectf.width(), fill_h)
                painter.setClipRect(clip_rect)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(accent))
                painter.drawRoundedRect(rectf, corner, corner)
                painter.restore()

        painter.setPen(QPen(gray, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, corner, corner)

        center = self._thumb_center()
        outer_r = self._thumb_radius
        inner_scale = self._inner_scale_current

        outer_color = QColor(tm.get_color("slider.thumb.outer"))
        painter.setPen(QPen(gray, 1))
        painter.setBrush(QBrush(outer_color))
        painter.drawEllipse(center, outer_r, outer_r)

        inner_r = max(1.0, float(outer_r) * float(inner_scale))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(QPointF(float(center.x()), float(center.y())), inner_r, inner_r)
