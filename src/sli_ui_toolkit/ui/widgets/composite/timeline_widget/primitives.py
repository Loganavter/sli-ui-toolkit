from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPolygonF

from sli_ui_toolkit.managers import scaled_px
from .i18n import localize_token_for
from .theme import playhead_outline_color, resolve_accent_color, timeline_alpha

_TRANSPARENT = QColor(0, 0, 0, 0)
"""Shared transparent stop for wash/edge gradients (module constant)."""

_alpha_cache: dict[tuple[int, int, int, int], QColor] = {}
_pen_cache: dict[tuple[int, int, int, int, float, Qt.PenCapStyle], QPen] = {}


def _alpha_color(base: QColor, alpha: int) -> QColor:
    """Cached ``(r, g, b) + alpha`` copy of *base* for the paint path.

    Per-row/per-paint alpha derivations (channel labels, chevron fills,
    washes, selection fills) resolve through here instead of building a
    ``QColor`` + ``setAlpha`` per row: after warmup no allocation
    happens. Returned colors are SHARED — call sites must use them
    read-only (``setPen``/``fillRect``), never mutate.
    """
    key = (base.red(), base.green(), base.blue(), int(alpha))
    hit = _alpha_cache.get(key)
    if hit is None:
        if len(_alpha_cache) > 512:
            _alpha_cache.clear()
        hit = QColor(key[0], key[1], key[2], key[3])
        _alpha_cache[key] = hit
    return hit


def _pen_for(color: QColor, width: float, cap: Qt.PenCapStyle = Qt.PenCapStyle.SquareCap) -> QPen:
    """Cached 1-style pen for the paint path (same sharing rule as above).

    Replaces per-row/per-tick ``QPen(color, width)`` construction in
    ``render.py`` loops and in the per-row primitive helpers.
    """
    key = (color.red(), color.green(), color.blue(), color.alpha(), float(width), cap)
    hit = _pen_cache.get(key)
    if hit is None:
        if len(_pen_cache) > 512:
            _pen_cache.clear()
        hit = QPen(QColor(key[0], key[1], key[2], key[3]), key[4])
        hit.setCapStyle(cap)
        _pen_cache[key] = hit
    return hit

def draw_gutter_background(widget, painter: QPainter, rect: QRectF, gutter_bg: QColor, sep_soft: QColor) -> None:
    painter.save()
    painter.fillRect(rect, gutter_bg)

    tm = widget.theme_manager
    accent = resolve_accent_color(widget)
    wash = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    top = _alpha_color(accent, timeline_alpha(tm, "timeline.gutter.wash.top.alpha"))
    bottom = _alpha_color(accent, timeline_alpha(tm, "timeline.gutter.wash.bottom.alpha"))
    wash.setColorAt(0.0, top)
    wash.setColorAt(0.35, bottom)
    wash.setColorAt(1.0, _TRANSPARENT)
    painter.fillRect(rect, wash)

    edge = QLinearGradient(rect.topLeft(), rect.topRight())
    glow = _alpha_color(accent, timeline_alpha(tm, "timeline.gutter.edge.alpha"))
    edge.setColorAt(0.0, glow)
    edge.setColorAt(0.18, _TRANSPARENT)
    painter.fillRect(rect, edge)
    painter.restore()

def draw_group_header_label(widget, painter: QPainter, rect: QRectF, group, label: str, text_col: QColor, sep_soft: QColor) -> None:
    painter.save()
    # Thin-owner geometry: the group helpers live in layout.py as plain
    # functions-taking-widget (function-level import — no new top-level
    # cross-module edge per the cycle rule).
    from . import layout as timeline_layout

    accent = timeline_layout.group_accent_color(widget, group)
    collapsed = timeline_layout.is_group_collapsed(widget, group)
    gradient = QLinearGradient(rect.topLeft(), rect.topRight())
    start = _alpha_color(accent, timeline_alpha(widget.theme_manager, "timeline.group.header.start.alpha"))
    end = _alpha_color(accent, timeline_alpha(widget.theme_manager, "timeline.group.header.end.alpha"))
    gradient.setColorAt(0.0, start)
    gradient.setColorAt(0.6, end)
    gradient.setColorAt(1.0, _TRANSPARENT)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(rect.adjusted(4, 1, -8, -1), 7, 7)

    accent_bar = QRectF(rect.left() + 4, rect.top() + 2, 3, rect.height() - 4)
    accent_fill = _alpha_color(accent, 210)
    painter.setBrush(accent_fill)
    painter.drawRoundedRect(accent_bar, 1.5, 1.5)

    # The painter font is design-sized; ui_font() applies the UiScale
    # factor exactly once (see render.py draw_footer_and_ruler).
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    font = ui_font(point_size=max(8, painter.font().pointSize() - 1))
    font.setBold(True)
    painter.setFont(font)

    chevron_rect = timeline_layout.group_chevron_rect(rect)
    chevron_x = chevron_rect.left() + 5
    center_y = rect.center().y()
    if collapsed:
        chevron = QPolygonF([QPointF(chevron_x, center_y - 4), QPointF(chevron_x + 6, center_y), QPointF(chevron_x, center_y + 4)])
    else:
        chevron = QPolygonF([QPointF(chevron_x - 1, center_y - 3), QPointF(chevron_x + 5, center_y - 3), QPointF(chevron_x + 2, center_y + 3)])
    chevron_fill = _alpha_color(text_col, 230)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(chevron_fill)
    painter.drawPolygon(chevron)

    text_rect = QRectF(rect.left() + 30, rect.top(), max(10.0, rect.width() - 42), rect.height())
    painter.setPen(_pen_for(text_col, 1))
    painter.drawText(
        text_rect,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        painter.fontMetrics().elidedText(str(label), Qt.TextElideMode.ElideRight, int(text_rect.width())),
    )
    painter.setPen(_pen_for(sep_soft, 1))
    painter.drawLine(int(rect.left() + 12), int(rect.bottom()), int(rect.right() - 12), int(rect.bottom()))
    painter.restore()

def draw_track_title_label(widget, painter: QPainter, rect: QRectF, label: str, text_col: QColor) -> None:
    painter.save()
    # Scale-resolve the font like draw_group_header_label: the painter font
    # is design-sized (the widget inherits the app font unscaled), so
    # ui_font() applies the UiScale factor exactly once.
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    font = ui_font(point_size=max(8, painter.font().pointSize()))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(_pen_for(text_col, 1))
    painter.drawText(
        rect,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        painter.fontMetrics().elidedText(str(label), Qt.TextElideMode.ElideRight, int(rect.width())),
    )
    painter.restore()

def draw_channel_label(widget, painter: QPainter, rect: QRectF, label: str, text_col: QColor, dot_color: QColor) -> None:
    painter.save()
    center_y = rect.center().y()
    dot_x = rect.left() + scaled_px(6)
    dot = _alpha_color(dot_color, 230)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(dot)
    # Scale the indicator dot with the UI scale (it used to stay at the
    # design 2.5px radius while the lane text grew — a "tiny dot" like the
    # old context-menu arrow glyph).
    dot_radius = scaled_px(5) / 2.0
    painter.drawEllipse(QPointF(dot_x, center_y), dot_radius, dot_radius)

    guide_col = _alpha_color(dot_color, 120)
    painter.setPen(_pen_for(guide_col, 1))
    painter.drawLine(
        int(dot_x), int(rect.top()) + scaled_px(2),
        int(dot_x), int(rect.bottom()) - scaled_px(2),
    )

    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    font = ui_font(point_size=max(8, painter.font().pointSize()))
    painter.setFont(font)
    text_rect = QRectF(rect.left() + 14, rect.top(), max(10.0, rect.width() - 14), rect.height())
    painter.setPen(_pen_for(text_col, 1))
    painter.drawText(
        text_rect,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        painter.fontMetrics().elidedText(localize_token_for(widget, label), Qt.TextElideMode.ElideRight, int(text_rect.width())),
    )
    painter.restore()

def draw_vertical_scrollbar_track(widget, painter: QPainter, bg_color: QColor) -> None:
    if not widget._v_scrollbar.isVisible():
        return
    rect = widget._v_scrollbar.geometry().adjusted(1, 6, -1, -6)
    if rect.isEmpty():
        return
    track = _alpha_color(bg_color, timeline_alpha(widget.theme_manager, "timeline.scrollbar.track.alpha"))
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(track)
    radius = min(rect.width(), 8) / 2.0
    painter.drawRoundedRect(QRectF(rect), radius, radius)
    painter.restore()

def draw_right_gutter_background(widget, painter: QPainter, rect: QRectF, gutter_bg: QColor, sep_soft: QColor) -> None:
    if rect.isEmpty():
        return
    draw_gutter_background(widget, painter, rect, gutter_bg, sep_soft)
    painter.save()
    painter.setPen(_pen_for(sep_soft, 1))
    painter.drawLine(int(rect.left()), int(rect.top()), int(rect.left()), int(rect.bottom()))
    painter.restore()

def draw_center_line(
    painter: QPainter, x0: float, x1: float, center_y: float, color: QColor
) -> None:
    """Paint a 1px lane center line spanning ``[x0, x1)`` at ``center_y``.

    Single primitive for both lane kinds (``render.draw_rows`` calls it
    after the keyframe curve, so the center stays visible — center-last
    order). A ``QRectF`` fill, never ``int(drawLine)``: ``int()``
    truncation floors fractional ``.5`` centers from odd scaled heights
    and shrinks the span by up to 1px at the right edge. The fill is
    exactly 1px tall, centered on ``center_y``.
    """
    if x1 <= x0:
        return
    painter.save()
    painter.fillRect(
        QRectF(float(x0), float(center_y) - 0.5, float(x1) - float(x0), 1.0),
        color,
    )
    painter.restore()


def draw_playhead(widget, painter: QPainter, *, x_head: float, footer_top: int, width: int) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    extended_rect = QRectF(
        -widget.HANDLE_WIDTH,
        -widget.HANDLE_HEIGHT - 5,
        width + 2 * widget.HANDLE_WIDTH,
        widget.height() + widget.HANDLE_HEIGHT + 5,
    )
    painter.setClipRect(extended_rect, Qt.ClipOperation.ReplaceClip)

    accent_color = resolve_accent_color(widget)
    outline_color = playhead_outline_color(widget)
    painter.setPen(_pen_for(outline_color, widget.HEAD_LINE_WIDTH + 2, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(x_head, 0), QPointF(x_head, footer_top))
    painter.setPen(_pen_for(accent_color, widget.HEAD_LINE_WIDTH, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(x_head, 0), QPointF(x_head, footer_top))
    painter.restore()
