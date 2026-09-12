"""Rounded clipping for flyout / menu content areas."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsEffect


class RoundedClipEffect(QGraphicsEffect):
    """Clip a widget subtree to a rounded rectangle (antialiased)."""

    def __init__(self, radius: float, parent=None):
        super().__init__(parent)
        self._radius = float(radius)

    def set_radius(self, radius: float) -> None:
        self._radius = float(radius)

    def radius(self) -> float:
        return self._radius

    def draw(self, painter: QPainter) -> None:
        src = self.sourceBoundingRect()
        if src.isEmpty():
            return
        clip = QPainterPath()
        clip.addRoundedRect(src, self._radius, self._radius)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
        self.drawSource(painter)
        painter.restore()
