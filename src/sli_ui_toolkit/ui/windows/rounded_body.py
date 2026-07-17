from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBitmap,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QRegion,
    QTransform,
)
from PySide6.QtWidgets import QDialog, QWidget

from sli_ui_toolkit.theme import ThemeManager

DEFAULT_CORNER_RADIUS = 10
# Flatten Bézier arcs to polygons at this scale before building QRegion masks.
# Default toFillPolygon() yields ~5 verts/corner — visibly staircased.
_MASK_FLATTEN_SCALE = 32.0


def _clamp_radius(rect: QRectF, radius: float) -> float:
    return max(0.0, min(float(radius), rect.width() * 0.5, rect.height() * 0.5))


def rounded_window_path(rect: QRectF, *, radius: float, squared: bool) -> QPainterPath:
    """Rounded CSD body path — all four corners unless ``squared`` (max/fullscreen)."""
    path = QPainterPath()
    r = 0.0 if squared else _clamp_radius(rect, radius)
    if r <= 0.0:
        path.addRect(rect)
        return path
    path.addRoundedRect(rect, r, r)
    return path


def top_rounded_path(rect: QRectF, *, radius: float, squared: bool = False) -> QPainterPath:
    """Rect with only the top-left / top-right corners rounded (title bar)."""
    path = QPainterPath()
    r = 0.0 if squared else _clamp_radius(rect, radius)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if r <= 0.0:
        path.addRect(rect)
        return path
    path.moveTo(x, y + h)
    path.lineTo(x, y + r)
    path.arcTo(x, y, 2.0 * r, 2.0 * r, 180.0, -90.0)
    path.lineTo(x + w - r, y)
    path.arcTo(x + w - 2.0 * r, y, 2.0 * r, 2.0 * r, 90.0, -90.0)
    path.lineTo(x + w, y + h)
    path.closeSubpath()
    return path


def bottom_rounded_path(rect: QRectF, *, radius: float, squared: bool = False) -> QPainterPath:
    """Rect with only the bottom-left / bottom-right corners rounded (content host)."""
    path = QPainterPath()
    r = 0.0 if squared else _clamp_radius(rect, radius)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if r <= 0.0:
        path.addRect(rect)
        return path
    path.moveTo(x, y)
    path.lineTo(x + w, y)
    path.lineTo(x + w, y + h - r)
    path.arcTo(x + w - 2.0 * r, y + h - 2.0 * r, 2.0 * r, 2.0 * r, 0.0, -90.0)
    path.lineTo(x + r, y + h)
    path.arcTo(x, y + h - 2.0 * r, 2.0 * r, 2.0 * r, 270.0, -90.0)
    path.lineTo(x, y)
    path.closeSubpath()
    return path


def top_trailing_rounded_path(
    rect: QRectF, *, radius: float, squared: bool = False
) -> QPainterPath:
    """Rect with only the top-right corner rounded (window-control cluster)."""
    path = QPainterPath()
    r = 0.0 if squared else _clamp_radius(rect, radius)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if r <= 0.0:
        path.addRect(rect)
        return path
    path.moveTo(x, y + h)
    path.lineTo(x, y)
    path.lineTo(x + w - r, y)
    path.arcTo(x + w - 2.0 * r, y, 2.0 * r, 2.0 * r, 90.0, -90.0)
    path.lineTo(x + w, y + h)
    path.closeSubpath()
    return path


def paint_rounded_window_background(
    painter: QPainter,
    rect: QRectF,
    *,
    color: QColor,
    radius: float,
    squared: bool,
) -> None:
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(rect, Qt.GlobalColor.transparent)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(rounded_window_path(rect, radius=radius, squared=squared))


def paint_top_rounded_background(
    painter: QPainter,
    rect: QRectF,
    *,
    color: QColor,
    radius: float,
    squared: bool,
) -> None:
    """Title-bar fill: transparent outside the top-rounded silhouette."""
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.fillRect(rect, Qt.GlobalColor.transparent)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(top_rounded_path(rect, radius=radius, squared=squared))


def _dense_polygon_region(path: QPainterPath) -> QRegion:
    """Convert curves to a dense polygon region (logical coordinates)."""
    scale = _MASK_FLATTEN_SCALE
    transform = QTransform.fromScale(scale, scale)
    polygon = path.toFillPolygon(transform)
    inverted, invertible = transform.inverted()
    if invertible:
        polygon = inverted.map(polygon)
    return QRegion(polygon.toPolygon())


def _mask_from_path(widget: QWidget, path: QPainterPath) -> None:
    """Clip ``widget`` to ``path``.

    Prefer a device-pixel ``QBitmap`` with matching ``devicePixelRatio`` so the
    stair-steps sit at physical pixels (HiDPI-safe). Fall back to a densely
    flattened logical ``QRegion`` when the bitmap path is unavailable.
    """
    dpr = max(1.0, float(widget.devicePixelRatioF()))
    logical_w = max(0, int(widget.width()))
    logical_h = max(0, int(widget.height()))
    if logical_w <= 0 or logical_h <= 0:
        widget.clearMask()
        return

    phys_w = max(1, int(round(logical_w * dpr)))
    phys_h = max(1, int(round(logical_h * dpr)))
    try:
        image = QImage(phys_w, phys_h, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 255))
            painter.drawPath(path)
        finally:
            painter.end()
        bitmap = QBitmap.fromImage(
            image.createAlphaMask(Qt.ImageConversionFlag.NoOpaqueDetection)
        )
        bitmap.setDevicePixelRatio(dpr)
        if bitmap.size().width() > 0 and bitmap.size().height() > 0:
            widget.setMask(bitmap)
            return
    except Exception:
        pass

    widget.setMask(_dense_polygon_region(path))


def apply_rounded_window_mask(
    widget: QWidget,
    *,
    radius: float,
    squared: bool = False,
) -> None:
    """Clip a widget to the full rounded CSD silhouette.

    Prefer this on *opaque child* hosts (content stack). Avoid on top-level
    shells / title bars that already paint an antialiased rounded fill —
    ``setMask`` is binary and destroys the AA edge.
    """
    if squared or radius <= 0.0 or widget.width() <= 0 or widget.height() <= 0:
        widget.clearMask()
        return
    path = rounded_window_path(
        QRectF(widget.rect()),
        radius=float(radius),
        squared=False,
    )
    _mask_from_path(widget, path)


def apply_bottom_rounded_mask(
    widget: QWidget,
    *,
    radius: float,
    squared: bool = False,
) -> None:
    """Clip content under the title bar so bottom window corners stay transparent."""
    if squared or radius <= 0.0 or widget.width() <= 0 or widget.height() <= 0:
        widget.clearMask()
        return
    path = bottom_rounded_path(
        QRectF(widget.rect()),
        radius=float(radius),
        squared=False,
    )
    _mask_from_path(widget, path)


def apply_top_rounded_mask(
    widget: QWidget,
    *,
    radius: float,
    squared: bool = False,
) -> None:
    """Clip a widget to the top-rounded silhouette (legacy full title-bar mask)."""
    if squared or radius <= 0.0 or widget.width() <= 0 or widget.height() <= 0:
        widget.clearMask()
        return
    path = top_rounded_path(
        QRectF(widget.rect()),
        radius=float(radius),
        squared=False,
    )
    _mask_from_path(widget, path)


def apply_top_trailing_rounded_mask(
    widget: QWidget,
    *,
    radius: float,
    squared: bool = False,
) -> None:
    """Clip the window-control cluster so only its top-right corner is rounded."""
    if squared or radius <= 0.0 or widget.width() <= 0 or widget.height() <= 0:
        widget.clearMask()
        return
    path = top_trailing_rounded_path(
        QRectF(widget.rect()),
        radius=float(radius),
        squared=False,
    )
    _mask_from_path(widget, path)


def resolve_window_bg_color(window: QWidget, bg_token: str = "Window") -> QColor:
    try:
        tm = ThemeManager.get_instance()
        color = tm.get_color(bg_token)
        if color.isValid() and color.alpha() > 0:
            return QColor(color)
    except Exception:
        pass
    if isinstance(window, QDialog):
        bg = QColor(window.palette().color(window.backgroundRole()))
        if bg.isValid() and bg.alpha() > 0:
            return bg
    return QColor("#2b2b2b")


def make_rounded_paint_event(bg_color: QColor, radius: int):
    state: dict[str, Any] = {"color": QColor(bg_color), "radius": int(radius)}

    def paint_event(self, event):  # noqa: ARG001 — Qt API
        painter = QPainter(self)
        try:
            squared = self.isMaximized() or self.isFullScreen()
            paint_rounded_window_background(
                painter,
                QRectF(self.rect()),
                color=state["color"],
                radius=float(state["radius"]),
                squared=squared,
            )
        finally:
            painter.end()

    return paint_event, state
