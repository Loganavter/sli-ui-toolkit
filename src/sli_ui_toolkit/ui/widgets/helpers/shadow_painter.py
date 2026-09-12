from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter

def draw_rounded_shadow(
    painter: QPainter,
    rect: QRectF,
    *,
    steps: int,
    radius: float,
    alpha_max: int = 34,
    color: QColor | None = None,
) -> None:
    """Fade a rounded-rect shadow outward from ``rect``.

    ``color`` tints the shadow (e.g. an accent-colored glow instead of the
    default black drop shadow); only its RGB channels are used, alpha is
    always driven by ``alpha_max``. Defaults to opaque black, matching the
    historical hardcoded shadow.
    """
    base = color if color is not None else QColor(0, 0, 0)
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(steps):
        alpha = int(alpha_max * (1 - i / steps) ** 2)
        painter.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
        shadow_rect = QRectF(rect).adjusted(-i, -i + 1, i, i + 1)
        painter.drawRoundedRect(shadow_rect, radius + i, radius + i)

