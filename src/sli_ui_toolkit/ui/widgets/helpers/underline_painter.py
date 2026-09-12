import math
from dataclasses import dataclass
from typing import List, Optional, Union

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QLineEdit

_TAPER_SEGMENTS = 24

from sli_ui_toolkit.theme import ThemeManager

@dataclass
class UnderlineConfig:
    thickness: float = 0.15
    vertical_offset: float = 0.75
    arc_radius: float = 1.33
    alpha: Optional[int] = None
    color: Union[QColor, List[QColor], None] = None

def _widget_scale(rect) -> float:
    """Scale factor based on widget height (baseline: 32px button)."""
    h = float(rect.height())
    return max(1.0, h / 32.0)


def _draw_tapered_arc(
    painter,
    base_color: QColor,
    thickness: float,
    cx: float,
    cy: float,
    radius: float,
    start_deg: float,
    sweep_deg: float,
    full_alpha: int,
    alpha_at_start: float,
    alpha_at_end: float,
) -> None:
    """Рисует дугу короткими сегментами с переменной альфой.

    alpha_at_start/end — нормализованные коэффициенты [0..1] от full_alpha
    в точках t=0 (start_deg) и t=1 (start_deg + sweep_deg).
    """
    pen = QPen(base_color)
    pen.setWidthF(thickness)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)

    prev_pt = None
    for s in range(_TAPER_SEGMENTS + 1):
        t = s / _TAPER_SEGMENTS
        ang = math.radians(start_deg + sweep_deg * t)
        # Y экран вниз: используем -sin для отображения стандартных углов
        x = cx + radius * math.cos(ang)
        y = cy - radius * math.sin(ang)
        pt = QPointF(x, y)
        if prev_pt is not None:
            t_mid = (s - 0.5) / _TAPER_SEGMENTS
            alpha_norm = alpha_at_start + (alpha_at_end - alpha_at_start) * t_mid
            alpha_val = int(round(full_alpha * max(0.0, min(1.0, alpha_norm))))
            seg_color = QColor(base_color)
            seg_color.setAlpha(alpha_val)
            pen.setColor(seg_color)
            painter.setPen(pen)
            painter.drawLine(prev_pt, pt)
        prev_pt = pt

def draw_bottom_underline(
    painter, rect, theme_manager: ThemeManager, config: UnderlineConfig | None = None
):
    cfg = config or UnderlineConfig()
    widget = painter.device()

    if theme_manager.is_dark():
        if not (widget and isinstance(widget, QLineEdit)):
            return

    if widget and hasattr(widget, "property"):
        btn_class = str(widget.property("class") or "")
        prefix = "button.primary" if btn_class == "primary" else "button.default"
    else:
        prefix = "button.default"

    if isinstance(cfg.color, list) and cfg.color:
        colors = cfg.color
    elif isinstance(cfg.color, QColor):
        colors = [cfg.color]
    else:
        colors = [QColor(theme_manager.get_color(f"{prefix}.bottom.edge"))]

    final_colors = []
    for color in colors:
        new_color = QColor(color)
        if cfg.alpha is not None:
            new_color.setAlpha(int(cfg.alpha))
        final_colors.append(new_color)

    count = len(final_colors)
    if count == 0:
        return

    scale = _widget_scale(rect)
    arc_radius = float(cfg.arc_radius) * scale
    thickness = cfg.thickness
    vertical_offset = cfg.vertical_offset * scale
    base_y = float(rect.bottom()) - vertical_offset
    start_x = float(rect.left())
    end_x = float(rect.right())
    total_width = end_x - start_x
    segment_width = total_width / count

    for i, color in enumerate(final_colors):
        pen = QPen(color)
        pen.setWidthF(thickness)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)

        seg_start = start_x + (i * segment_width)
        seg_end = start_x + ((i + 1) * segment_width)
        line_start_x = seg_start + arc_radius if i == 0 else seg_start
        line_end_x = seg_end - arc_radius if i == count - 1 else seg_end

        if line_end_x > line_start_x:
            painter.drawLine(
                QPointF(line_start_x, base_y),
                QPointF(line_end_x, base_y),
            )

        full_alpha = color.alpha()
        if arc_radius <= 0:
            continue

        if i == 0:
            # Левый кончик: дуга 180°→270°. Альфа линейно нарастает от 0 (кончик) до full (стык с линией).
            cx = start_x + arc_radius
            cy = base_y - arc_radius
            _draw_tapered_arc(
                painter, color, thickness, cx, cy, arc_radius,
                start_deg=180.0, sweep_deg=90.0,
                full_alpha=full_alpha, alpha_at_start=0.0, alpha_at_end=1.0,
            )

        if i == count - 1:
            # Правый кончик: дуга 270°→360°. Альфа падает от full (стык) до 0 (кончик).
            cx = end_x - arc_radius
            cy = base_y - arc_radius
            _draw_tapered_arc(
                painter, color, thickness, cx, cy, arc_radius,
                start_deg=270.0, sweep_deg=90.0,
                full_alpha=full_alpha, alpha_at_start=1.0, alpha_at_end=0.0,
            )
