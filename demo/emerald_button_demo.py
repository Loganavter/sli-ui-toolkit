"""Emerald gem Button — каждая грань это отдельный ButtonRegion с path_fn.

Тулкитовый pipeline сам обрабатывает hover/ripple/pressed для каждой зоны
независимо. Кастомная обводка поверх граней передаётся через high-level
параметр overlay_painter на Button.

Фиксы:
  - z_index=0 у всех граней → hit-тест по path_fn корректен, каждая грань
    получает HOVERED независимо
  - setMask(QRegion(polygon)) → углы вне октагона прозрачны (не красятся
    фоном темы/приложения)

Запуск из корня sli-ui-toolkit:
    python emerald_button_demo.py
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainterPath, QPen, QPolygon, QRegion
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sli_ui_toolkit.config import configure_toolkit
from sli_ui_toolkit.icons import configure_icon_resolver
from sli_ui_toolkit.palettes import FLUENT_LIGHT, FLUENT_DARK
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, ButtonRegion, Label, install_application_tooltips

# ─── Gem geometry ─────────────────────────────────────────────────────────────

def _build_facet_paths(w: float, h: float, cut: float = 0.22, bevel: float = 0.20):
    """Build QPainterPath for each of the 9 emerald facets.

    Outer octagon vertices (clockwise from TL going right):
      0: TL_right   1: TR_left   2: TR_down   3: BR_up
      4: BR_left    5: BL_right  6: BL_up     7: TL_down

    Inner table corners (TL, TR, BR, BL).
    """
    x0, y0 = 0.0, 0.0
    x1, y1 = float(w), float(h)
    cx = w * cut
    cy = h * cut
    bx = w * bevel
    by = h * bevel

    O = [
        (x0 + cx, y0),       # 0
        (x1 - cx, y0),       # 1
        (x1,      y0 + cy),  # 2
        (x1,      y1 - cy),  # 3
        (x1 - cx, y1),       # 4
        (x0 + cx, y1),       # 5
        (x0,      y1 - cy),  # 6
        (x0,      y0 + cy),  # 7
    ]
    I = [
        (x0 + bx, y0 + by),  # 0 TL
        (x1 - bx, y0 + by),  # 1 TR
        (x1 - bx, y1 - by),  # 2 BR
        (x0 + bx, y1 - by),  # 3 BL
    ]

    def poly(*pts) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(*pts[0])
        for pt in pts[1:]:
            path.lineTo(*pt)
        path.closeSubpath()
        return path

    return {
        # Corners — triangles
        "tl_corner": poly(O[7], O[0], I[0]),
        "tr_corner": poly(O[1], O[2], I[1]),
        "br_corner": poly(O[3], O[4], I[2]),
        "bl_corner": poly(O[5], O[6], I[3]),
        # Edges — trapezoids
        "top_edge":    poly(O[0], O[1], I[1], I[0]),
        "right_edge":  poly(O[2], O[3], I[2], I[1]),
        "bottom_edge": poly(O[4], O[5], I[3], I[2]),
        "left_edge":   poly(O[6], O[7], I[0], I[3]),
        # Central table
        "table":       poly(*I),
    }


# Facet base colors and their hover tints
_FACET_COLOR: dict[str, QColor] = {
    "tl_corner":   QColor("#1a5c36"),
    "tr_corner":   QColor("#1a5c36"),
    "br_corner":   QColor("#1a5c36"),
    "bl_corner":   QColor("#1a5c36"),
    "top_edge":    QColor("#2d9664"),
    "right_edge":  QColor("#2d9664"),
    "bottom_edge": QColor("#2d9664"),
    "left_edge":   QColor("#2d9664"),
    "table":       QColor("#5ddba0"),
}

# Hover wash per facet: lighter for the table, more vivid for corners
_FACET_HOVER: dict[str, QColor] = {
    "tl_corner":   QColor(255, 255, 255, 80),
    "tr_corner":   QColor(255, 255, 255, 80),
    "br_corner":   QColor(255, 255, 255, 80),
    "bl_corner":   QColor(255, 255, 255, 80),
    "top_edge":    QColor(255, 255, 255, 65),
    "right_edge":  QColor(255, 255, 255, 65),
    "bottom_edge": QColor(255, 255, 255, 65),
    "left_edge":   QColor(255, 255, 255, 65),
    "table":       QColor(255, 255, 255, 50),
}

# Facet labels shown in the status label
_FACET_LABEL: dict[str, str] = {
    "tl_corner":   "↖ угол",
    "tr_corner":   "↗ угол",
    "br_corner":   "↘ угол",
    "bl_corner":   "↙ угол",
    "top_edge":    "▲ верх",
    "right_edge":  "▶ право",
    "bottom_edge": "▼ низ",
    "left_edge":   "◀ лево",
    "table":       "⬛ стол",
}


# ─── Custom outline painter ───────────────────────────────────────────────────

def _draw_gem_outline(p: QPainter, rect: QRectF) -> None:
    """Draw facet seam lines and the thick outer octagon outline over all regions."""
    gem_w, gem_h = rect.width(), rect.height()
    paths = _build_facet_paths(gem_w, gem_h)

    # Seam lines (thin dark)
    seam_pen = QPen(QColor("#0a2e1a"), 1.2, Qt.PenStyle.SolidLine)
    seam_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(seam_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for facet_path in paths.values():
        p.drawPath(facet_path)

    # Outer octagon outline (thick)
    cx = gem_w * 0.22
    cy = gem_h * 0.22
    outer = QPainterPath()
    pts = [
        (cx, 0),                 (gem_w - cx, 0),
        (gem_w, cy),             (gem_w, gem_h - cy),
        (gem_w - cx, gem_h),     (cx, gem_h),
        (0, gem_h - cy),        (0, cy),
    ]
    outer.moveTo(*pts[0])
    for pt in pts[1:]:
        outer.lineTo(*pt)
    outer.closeSubpath()

    outline_pen = QPen(QColor("#061a0e"), 3.5, Qt.PenStyle.SolidLine)
    outline_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(outline_pen)
    p.drawPath(outer)


# ─── Build the gem Button ─────────────────────────────────────────────────────

def _octagon_mask(w: int, h: int, cut: float = 0.22) -> QRegion:
    """QRegion clipped to the gem octagon — applied via setMask()."""
    cx = int(w * cut)
    cy = int(h * cut)
    pts = [
        QPoint(cx,     0),
        QPoint(w - cx, 0),
        QPoint(w,      cy),
        QPoint(w,      h - cy),
        QPoint(w - cx, h),
        QPoint(cx,     h),
        QPoint(0,      h - cy),
        QPoint(0,      cy),
    ]
    return QRegion(QPolygon(pts))


def _build_gem_button(gem_w: int = 200, gem_h: int = 160) -> Button:
    """Create a Button where each emerald facet is an independent ButtonRegion."""

    paths = _build_facet_paths(gem_w, gem_h)

    regions: list[ButtonRegion] = []
    for fid, facet_path in paths.items():
        # Capture by value with default-argument trick
        def _make_path_fn(p: QPainterPath):
            return lambda r: p

        # rect_fn supplies the bounding rect for hit testing / content bounds.
        # BackgroundLayer automatically applies path_fn clipping whenever path_fn
        # is present (regardless of rect_fn).
        def _make_rect_fn(bb: QRectF):
            return lambda r: QRectF(bb)

        bb = facet_path.boundingRect()
        regions.append(
            ButtonRegion(
                id=fid,
                rect_fn=_make_rect_fn(bb),
                path_fn=_make_path_fn(facet_path),
                # Each facet has its own opaque base + independent hover wash.
                override_bg_color=_FACET_COLOR[fid],
                hover_color=_FACET_HOVER[fid],
                # All z_index=0: paths are mutually exclusive (no overlap),
                # so z_index priority never comes into play.
                z_index=0,
            )
        )

    btn = Button(
        regions=regions,
        size=(gem_w, gem_h),
        corner_radius=0,
        overlay_painter=_draw_gem_outline,
    )
    btn.regionClicked.connect(
        lambda rid: print(f"[gem] нажата грань: {_FACET_LABEL.get(rid, rid)}")
    )

    # Clip widget to the octagon so the rectangular widget corners outside
    # the gem are transparent (otherwise the theme background fills them).
    btn.setMask(_octagon_mask(gem_w, gem_h))

    return btn


# ─── Demo window ──────────────────────────────────────────────────────────────

class EmeraldDemo(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Emerald Gem — 9 независимых ButtonRegion")
        self.setStyleSheet("background: #f0faf5;")
        self.setMinimumSize(520, 320)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(20)

        root.addWidget(
            Label(
                "Изумруд: 9 зон с независимым hover/ripple",
                pixel_size=16,
                bold=True,
            )
        )

        hint = QLabel(
            "Каждая грань — отдельный ButtonRegion(path_fn=…)\n"
            "Hover, ripple и click обрабатываются тулкитом независимо."
        )
        hint.setStyleSheet("color: #2d7a50; font-size: 12px;")
        root.addWidget(hint)

        gem = _build_gem_button(200, 160)
        root.addWidget(gem, alignment=Qt.AlignmentFlag.AlignCenter)

        self._status = QLabel("наведи на грань…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #1a5c36; font-size: 13px; font-weight: bold;")
        root.addWidget(self._status)

        # Wire hover feedback to the status label
        gem.regionClicked.connect(
            lambda rid: self._status.setText(f"Кликнуто: {_FACET_LABEL.get(rid, rid)}")
        )

        root.addStretch()


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)

    # Null icon resolver — no icons used in this demo, but configure_icon_resolver
    # must be called so the toolkit doesn't error on first use.
    # configure_icon_resolver(lambda name, *a, **kw: QIcon(), named_icons={})

    configure_toolkit()

    tm = ThemeManager.get_instance()
    tm.register_palettes(light_palette=FLUENT_LIGHT, dark_palette=FLUENT_DARK)
    tm.set_theme("light", app)

    install_application_tooltips(app)

    win = EmeraldDemo()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
