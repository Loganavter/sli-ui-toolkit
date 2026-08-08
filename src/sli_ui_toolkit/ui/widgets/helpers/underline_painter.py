from dataclasses import dataclass
from typing import List, Optional, Union

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath

from sli_ui_toolkit.theme import ThemeManager

# Physical height (pre-scale px) of the tip alpha-fade — fixed regardless of
# ``thickness``/``tongue_reach`` so it stays a subtle taper instead of
# consuming a whole short tongue or vanishing against a tall one.
_TIP_FADE_PX = 4.0


@dataclass
class UnderlineConfig:
    thickness: float = 0.15
    vertical_offset: float = 0.75
    arc_radius: float = 1.33
    alpha: Optional[int] = None
    color: Union[QColor, List[QColor], None] = None
    # How high above the bottom edge the underline's end caps ("tongues")
    # are allowed to climb, in the same (pre-scale) units as ``arc_radius``.
    # ``None`` keeps the old default of matching ``arc_radius`` exactly (the
    # cap only follows the corner's own rounding, nothing more). ``0`` means
    # no tongues at all — hard square ends right at the bottom edge. A value
    # reaching the widget's full height makes each end climb the whole side.
    tongue_reach: Optional[float] = None
    # When True, ignore ``tongue_reach`` and draw a full closed outline
    # (a ring/frame) around the whole widget instead of just a bottom band.
    ring: bool = False
    # Whether the true left/right ends of the strip fade to transparent at
    # their tip (soft taper) or stop with a hard edge (crisp block). Only
    # the two true outer ends are ever affected — interior seams between
    # color zones are always crisp regardless of this flag.
    fade: bool = True


def _widget_scale(rect) -> float:
    """Scale factor based on widget height (baseline: 32px button)."""
    h = float(rect.height())
    return max(1.0, h / 32.0)


def _rounded_rect_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    if rect.width() > 0 and rect.height() > 0:
        path.addRoundedRect(rect, radius, radius)
    return path


def _build_band_path(rect: QRectF, radius: float, thickness: float, reach: float, ring: bool) -> QPainterPath:
    """Filled path for the underline band.

    Built entirely from rounded-rect boolean ops (intersect/subtract)
    instead of hand-rolled arc math, so the result can never spill past the
    widget's own silhouette — the "outer" contour is always literally the
    widget's rounded-rect (or a sub-rectangle of it), never a separately
    stroked circle that can overshoot it at large thickness.
    """
    left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
    outer_rect_path = _rounded_rect_path(rect, radius)

    if ring:
        outer_region = outer_rect_path
    elif reach <= 1e-6:
        # No tongues: a plain square-cornered strip along the bottom edge,
        # deliberately ignoring the corner rounding entirely.
        outer_region = QPainterPath()
        strip = QRectF(left, bottom - thickness, right - left, thickness)
        if strip.height() > 0:
            outer_region.addRect(strip)
        return outer_region
    else:
        strip_path = QPainterPath()
        strip_path.addRect(QRectF(left, bottom - reach, right - left, reach))
        outer_region = outer_rect_path.intersected(strip_path)

    inner_rect = QRectF(
        left + thickness,
        top,
        max(0.0, (right - left) - 2 * thickness),
        max(0.0, (bottom - top) - thickness),
    )
    inner_radius = max(0.0, radius - thickness)
    inner_path = _rounded_rect_path(inner_rect, inner_radius)
    if inner_path.isEmpty():
        return outer_region
    return outer_region.subtracted(inner_path)


def draw_bottom_underline(
    painter, rect, theme_manager: ThemeManager, config: UnderlineConfig | None = None
):
    cfg = config or UnderlineConfig()
    widget = painter.device()

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
    thickness = max(0.0, float(cfg.thickness))
    vertical_offset = cfg.vertical_offset * scale

    left = float(rect.left())
    right = float(rect.right())
    top = float(rect.top())
    bottom = float(rect.bottom()) - vertical_offset
    band_rect = QRectF(left, top, right - left, bottom - top)

    span = max(0.0, bottom - top)
    arc_radius = min(arc_radius, span, (right - left) / 2.0)
    thickness = min(thickness, span)

    reach = (
        float(cfg.tongue_reach) * scale if cfg.tongue_reach is not None else arc_radius
    )
    reach = max(0.0, min(reach, span))

    band_path = _build_band_path(band_rect, arc_radius, thickness, reach, cfg.ring)
    if band_path.isEmpty():
        return

    segment_width = (right - left) / count

    # Tip fade: the very ends of the strip (true left/right edges only, not
    # interior seams between color zones) fade from transparent at the tip
    # down to full alpha. Fixed physical size (scaled with the widget, like
    # everything else here) rather than derived from ``reach``/``thickness``
    # — tying it to those either drowns a small tongue in fade with no solid
    # part left, or is imperceptible against a tall one.
    #
    # Only applies while the tongue is still an actual taper — i.e.
    # ``thickness < reach``. Once thickness reaches/exceeds reach, the end is
    # geometrically just a flat block (see _build_band_path: excess
    # thickness saturates the corner solid rather than narrowing it), and
    # smearing a gradient over a flat block just looks like a dirty edge,
    # not a taper.
    fade_height = (
        min(reach, _TIP_FADE_PX * scale)
        if (cfg.fade and not cfg.ring and thickness < reach)
        else 0.0
    )

    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        for i, color in enumerate(final_colors):
            seg_start = left + i * segment_width
            seg_end = left + (i + 1) * segment_width
            painter.save()
            painter.setClipRect(QRectF(seg_start, top, seg_end - seg_start, bottom - top))

            # Ordinary SourceOver blending only — deliberately never touches
            # the destination's own alpha (e.g. via CompositionMode_DestinationIn).
            # This widget's backing store is normally opaque (painted solid by
            # BackgroundLayer just before this layer runs); an alpha-reducing
            # composition mode would punch a real hole in that opaque surface
            # rather than just visually blending color into it, which — on
            # compositing window managers — can bleed through to whatever is
            # behind the actual OS window (most visible once a redraw happens
            # outside the normal repaint path, e.g. on window focus loss).
            # So each tip is built as two SourceOver fills instead: solid
            # everywhere except the fade rect, and a color-alpha gradient
            # (opaque-to-transparent-of-the-same-color) inside it.
            solid_region = band_path
            tip_pieces = []
            if fade_height > 1e-6:
                tip_y = bottom - reach
                fade_rect_width = max(arc_radius, thickness) + 2.0
                if i == 0:
                    tip_pieces.append(_tip_fade_piece(left, tip_y, fade_rect_width, fade_height, color, is_left=True))
                if i == count - 1:
                    tip_pieces.append(_tip_fade_piece(right, tip_y, fade_rect_width, fade_height, color, is_left=False))
            for fade_path, _grad in tip_pieces:
                solid_region = solid_region.subtracted(fade_path)

            painter.fillPath(solid_region, color)
            for fade_path, grad in tip_pieces:
                painter.fillPath(band_path.intersected(fade_path), grad)

            painter.restore()
    finally:
        painter.restore()


def _tip_fade_piece(
    edge_x: float, tip_y: float, width: float, height: float, color: QColor, is_left: bool
) -> tuple[QPainterPath, QLinearGradient]:
    fade_rect = QRectF(edge_x if is_left else edge_x - width, tip_y, width, height)
    fade_path = QPainterPath()
    fade_path.addRect(fade_rect)

    transparent = QColor(color)
    transparent.setAlpha(0)
    grad = QLinearGradient(edge_x, tip_y, edge_x, tip_y + height)
    grad.setColorAt(0.0, transparent)
    grad.setColorAt(1.0, color)
    return fade_path, grad
