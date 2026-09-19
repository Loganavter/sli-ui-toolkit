from __future__ import annotations

import bisect
import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from . import layout as timeline_layout
from . import primitives as timeline_primitives
from . import theme as timeline_theme
from . import viewport as timeline_viewport
from .debug import _timeline_debug_enabled, _timeline_paint_debug
from .segments import _draw_keyframe_segments

# Accent-wash alphas for the row paint path: ``token -> (light, dark)``.
#
# Wave-G interim (flagged for wave A promotion into
# ``theme._TIMELINE_ALPHA_DEFAULTS``): every wash strength the row painters
# used to pick with a per-theme ternary now resolves through
# ``ThemeManager.try_get_color`` on a ``timeline.*`` token first, so hosts
# can already override any entry via ``register_palettes``. The local
# per-theme default below applies only while the token is unregistered —
# the same chain ``theme.timeline_alpha`` implements for the older wash
# tokens. Values are the exact pre-refactor per-theme strengths, so default
# paints are pixel-identical in both themes.
_WASH_ALPHA_DEFAULTS: dict[str, tuple[int, int]] = {
    "timeline.group.wash.track.alpha": (22, 46),
    "timeline.group.wash.first.alpha": (18, 42),
    "timeline.group.wash.channel.alpha": (10, 24),
    "timeline.ruler.minor.tick.alpha": (180, 150),
}


def _wash_alpha(tm, token: str) -> int:
    """Resolve a row-paint wash alpha through theme tokens.

    Chain: ``timeline.*`` token alpha (host override) → local per-theme
    default from ``_WASH_ALPHA_DEFAULTS``. The fallback reads the active
    theme name (never a hardcoded paint-path branch), mirroring
    ``theme.timeline_alpha``; wave A promotes these tokens into theme.py
    and this helper collapses to that function.
    """
    hit = tm.try_get_color(token)
    if hit is not None:
        return max(0, min(255, hit.alpha()))
    light, dark = _WASH_ALPHA_DEFAULTS[token]
    return dark if tm.get_current_theme() == "dark" else light


def draw_thumbnail_strip(widget, painter: QPainter, *, canvas_bg: QColor, content_start_x: float, strip_top: float, width: int, start_x: float, end_x: float, logical_width: float, slot_width: float) -> None:
    painter.fillRect(QRectF(content_start_x, strip_top, width - content_start_x, widget.STRIP_HEIGHT), canvas_bg)
    blocks = timeline_viewport.strip_block_layout(
        widget, content_start_x=content_start_x, start_x=start_x, end_x=end_x
    )
    base_tile = timeline_viewport.get_base_tile_width(widget)
    draw_w = blocks[0][1] if blocks else base_tile
    frames_per_block = draw_w / slot_width if slot_width > 0 else 1.0
    first_rep = blocks[0][2] if blocks else 0
    last_rep = blocks[-1][2] if blocks else 0
    if _timeline_debug_enabled():
        # Check if strip is actually visible in widget
        _timeline_paint_debug("draw_strip id=%s vis=%s width=%s start_x=%s end_x=%s logical=%s slot=%s base=%s fpb=%.2f draw_w=%.2f blocks=%s first=%s last=%s total=%s thumb_n=%s thumb_ids=%s strip_top=%s height=%s isVisible=%s", id(widget), widget.isVisible(), width, start_x, end_x, logical_width, slot_width, base_tile, frames_per_block, draw_w, len(blocks), first_rep, last_rep, widget._total_frames, len(widget._thumbnails), sorted(list(widget._thumbnails.keys()))[:12], strip_top, widget.height(), widget.isVisible())
        # Coverage audit: which blocks actually get a pixmap (same verdict
        # as the draw loop below) and whether their rects tile the visible
        # span without gaps. A gap here is background showing between
        # thumbs — distinguishable from content (dark scene) because it
        # reports geometry, not pixels.
        _cov_lo = max(float(content_start_x), float(start_x))
        _cov_hi = min(float(end_x), float(content_start_x) + float(logical_width))
        _drawn_spans: list[tuple[float, float]] = []
        for _bx, _bw, _rep in blocks:
            _ti = -1
            if widget._thumb_indices:
                _pos = bisect.bisect_right(widget._thumb_indices, _rep)
                _ti = widget._thumb_indices[_pos-1] if _pos>0 else widget._thumb_indices[0]
            _pix = widget._thumbnails.get(_ti) if _ti!=-1 else None
            _drawn = bool(_pix is not None and _pix.height() > 0)
            _timeline_paint_debug("block x=%.3f w=%.3f rep=%s thumb_idx=%s pix_null=%s pix_size=%s drawn=%s", _bx, _bw, _rep, _ti, _pix.isNull() if _pix else True, (_pix.width(), _pix.height()) if _pix and not _pix.isNull() else None, _drawn)
            if _drawn:
                _drawn_spans.append((float(_bx), float(_bx) + float(_bw)))
        _gaps: list[str] = []
        _cursor = _cov_lo
        for _s0, _s1 in _drawn_spans:
            if _s0 > _cursor + 1e-6:
                _gaps.append("[%.2f,%.2f]=%.2fpx" % (_cursor, _s0, _s0 - _cursor))
            _cursor = max(_cursor, _s1)
        if _cursor < _cov_hi - 1e-6:
            _gaps.append("[%.2f,%.2f]=%.2fpx" % (_cursor, _cov_hi, _cov_hi - _cursor))
        _timeline_paint_debug("strip_coverage id=%s span=[%.2f,%.2f] drawn=%d gaps=%s", id(widget), _cov_lo, _cov_hi, len(_drawn_spans), ",".join(_gaps) if _gaps else "none")

    for block_x, block_w, rep_frame in blocks:
        if block_w <= 0:
            break
        thumb_idx = -1
        if widget._thumb_indices:
            pos = bisect.bisect_right(widget._thumb_indices, rep_frame)
            thumb_idx = widget._thumb_indices[pos - 1] if pos > 0 else widget._thumb_indices[0]
        if thumb_idx != -1:
            pix = widget._thumbnails.get(thumb_idx)
            if pix and pix.height() > 0:
                # +1px overlap: adjacent opaque draws must overlap by at
                # least a pixel, otherwise DPR rounding / smoothing fringes
                # leave a background sliver at the seam (static 1-2px lines
                # that do not scale with zoom). The neighbor overdraws the
                # shared pixel with its own content — invisible at 128px
                # blocks. Layout (strip_block_layout) stays exactly tiled.
                painter.drawPixmap(QRectF(block_x, strip_top, block_w + 1.0, float(widget.STRIP_HEIGHT)), pix, QRectF(pix.rect()))

def _row_segments_culled(widget, *, track, channel, duration: float, logical_width: float, start_x: float, end_x: float) -> bool:
    """Per-row horizontal cull: True when the row has no keyframe content
    inside the damage interval and segment work can be skipped.

    The row still paints its (damage-clipped) background fills; only the
    segment computation + point drawing is skipped. Falls back to drawing
    (False) when the duration is degenerate, matching the old behavior.
    """
    if duration <= 0:
        return False
    x_range = timeline_layout.row_time_x_range(widget, track, channel, duration, logical_width)
    if x_range is None:
        return True
    return x_range[1] < start_x or x_range[0] > end_x


def draw_rows(widget, painter: QPainter, *, width: int, rows_top: int, rows_bottom: int, content_start_x: float, start_x: float, end_x: float, duration: float, logical_width: float, gutter_bg: QColor, track_bg: QColor, lane_bg: QColor, text_col: QColor, sep_soft: QColor) -> None:
    # Row geometry comes from layout.iter_row_rects — the single
    # y-accumulation site shared with the sticky-gutter overlay and the
    # group hit-test — so lane paint, gutter paint, and hit-testing visit
    # identical rects under scroll/collapse. Damage clipping: lane
    # backgrounds are filled only inside [start_x, end_x] — pixels outside
    # the damage rect are never presented, so filling them was pure
    # overdraw. Gutter fills stay full-gutter (narrow sticky region,
    # repainted by the overlay pass). Per-row horizontal cull skips segment
    # computation for rows whose keyframe content lies fully outside the
    # damage interval. Wash strengths resolve through theme tokens (see
    # _wash_alpha), never per-theme branches.
    lane_x0 = max(content_start_x, start_x)
    lane_x1 = min(float(width), end_x)
    lane_has_damage = lane_x1 > lane_x0
    sep_row = timeline_theme.row_separator_color(widget)
    center_line = timeline_theme.row_center_line_color(widget)
    tm = widget.theme_manager
    track_wash = _wash_alpha(tm, "timeline.group.wash.track.alpha")
    first_wash = _wash_alpha(tm, "timeline.group.wash.first.alpha")
    channel_wash = _wash_alpha(tm, "timeline.group.wash.channel.alpha")
    for kind, key, rect in timeline_layout.iter_row_rects(widget, rows_top, rows_bottom):
        y = rect.top()
        row_h = rect.height()
        if kind == "group":
            group = key[1]
            timeline_primitives.draw_group_header_label(widget, painter, QRectF(0, y, widget.LEFT_GUTTER, row_h), group, group.label, text_col, sep_soft)
            continue

        if kind == "track_single":
            _kind, group, track, channel = key
            line_col = timeline_theme.track_line_color(
                widget,
                track.id,
                track.kind,
                channel.kind,
                track_accent_color=getattr(track, "accent_color", None),
                channel_accent_color=getattr(channel, "accent_color", None),
            )
            gutter_track_bg = timeline_theme.group_content_bg(widget, track_bg, group, track_wash)
            painter.fillRect(QRectF(0, y, content_start_x, row_h), gutter_track_bg)
            if lane_has_damage:
                painter.fillRect(QRectF(lane_x0, y, lane_x1 - lane_x0, row_h), lane_bg)
            painter.setPen(QPen(sep_row, 1))
            painter.drawLine(0, y + row_h, width, y + row_h)
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(18, y, max(40, widget.LEFT_GUTTER - 30), row_h), track.label, text_col)
            if lane_has_damage:
                row_center_y = timeline_layout.row_center_y(y, row_h)
                if not _row_segments_culled(widget, track=track, channel=channel, duration=duration, logical_width=logical_width, start_x=start_x, end_x=end_x):
                    _draw_keyframe_segments(widget, painter, group=group, track=track, channel=channel, duration=duration, logical_width=logical_width, row_center_y=row_center_y, start_x=start_x, end_x=end_x, line_col=line_col, point_radius=4.0)
                # Center line last: the keyframe curve oscillates around it
                # and would otherwise bury it under 1.5px segments + dots.
                timeline_primitives.draw_center_line(painter, lane_x0, lane_x1, row_center_y, center_line)
            continue

        _kind, group, track, channel, is_first_channel = key
        line_col = timeline_theme.track_line_color(
            widget,
            track.id,
            track.kind,
            channel.kind,
            track_accent_color=getattr(track, "accent_color", None),
            channel_accent_color=getattr(channel, "accent_color", None),
        )
        if is_first_channel:
            painter.fillRect(QRectF(0, y, content_start_x, row_h), timeline_theme.group_content_bg(widget, track_bg, group, first_wash))
        else:
            painter.fillRect(QRectF(0, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, gutter_bg, group, channel_wash))
        if lane_has_damage:
            painter.fillRect(QRectF(lane_x0, y, lane_x1 - lane_x0, row_h), lane_bg)
        painter.setPen(QPen(sep_row, 1))
        painter.drawLine(0, y + row_h, width, y + row_h)
        if is_first_channel:
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(18, y, max(40, widget.LEFT_GUTTER * 0.44 - 22), row_h), track.label, text_col)
        channel_col = QColor(text_col)
        channel_col.setAlpha(215 if is_first_channel else 195)
        timeline_primitives.draw_channel_label(
            widget,
            painter,
            QRectF(max(42, widget.LEFT_GUTTER * 0.50), y, widget.LEFT_GUTTER - max(42, widget.LEFT_GUTTER * 0.50) - 12, row_h),
            channel.label,
            channel_col,
            line_col,
        )
        if lane_has_damage:
            row_center_y = timeline_layout.row_center_y(y, row_h)
            if not _row_segments_culled(widget, track=track, channel=channel, duration=duration, logical_width=logical_width, start_x=start_x, end_x=end_x):
                _draw_keyframe_segments(widget, painter, group=group, track=track, channel=channel, duration=duration, logical_width=logical_width, row_center_y=row_center_y, start_x=start_x, end_x=end_x, line_col=line_col, point_radius=3.5)
            # Center line last (see track_single branch above).
            timeline_primitives.draw_center_line(painter, lane_x0, lane_x1, row_center_y, center_line)

def draw_footer_and_ruler(widget, painter: QPainter, *, width: int, content_start_x: float, footer_height: int, footer_top: int, scrollbar_strip_top: int, ruler_top: int, ruler_bottom: int, scroll_offset: int, viewport_width: int, duration: float, logical_width: float, start_x: float, end_x: float, footer_bg: QColor, sep_strong: QColor, sep_soft: QColor, grid_col: QColor, text_col: QColor, sb_idle: QColor, sb_hover: QColor) -> None:
    foot_x0 = max(content_start_x, start_x)
    foot_x1 = min(float(width), end_x)
    if foot_x1 > foot_x0:
        painter.fillRect(QRectF(foot_x0, footer_top, foot_x1 - foot_x0, footer_height), footer_bg)
    painter.setPen(QPen(sep_strong, 1))
    painter.drawLine(0, int(footer_top), width, int(footer_top))
    timeline_primitives.draw_vertical_scrollbar_track(widget, painter, footer_bg)
    sb_rect = QRectF(scroll_offset + content_start_x, scrollbar_strip_top, max(0.0, viewport_width - content_start_x), widget.SCROLLBAR_STRIP_HEIGHT)
    timeline_viewport.draw_inner_scrollbar(widget, painter, sb_rect, sb_idle, sb_hover)
    painter.setPen(QPen(sep_soft, 1))
    painter.drawLine(0, int(ruler_top) - 1, width, int(ruler_top) - 1)
    painter.setPen(QPen(grid_col, 1))
    painter.drawLine(int(content_start_x), ruler_bottom - 1, width, ruler_bottom - 1)
    painter.setPen(QPen(sep_strong, 1))
    painter.drawLine(0, widget.height() - 1, width, widget.height() - 1)
    if duration <= 0:
        return
    step_sec = timeline_viewport.choose_ruler_step(duration, logical_width)
    minor_divisions = timeline_viewport.choose_ruler_subdivisions(step_sec, duration, logical_width)
    # The painter font is design-sized (the widget inherits the app font
    # unscaled); ui_font() applies the UiScale factor exactly once. Restore
    # afterwards: the ruler font must not leak into the sticky-gutter pass
    # that follows (it is already scale-resolved, and the label painters
    # would multiply the factor a second time).
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    ruler_font = ui_font(point_size=max(8, painter.font().pointSize() - 2))
    painter.save()
    painter.setFont(ruler_font)
    if minor_divisions > 1:
        minor_step = step_sec / minor_divisions
        minor_tick_col = QColor(grid_col)
        minor_tick_col.setAlpha(_wash_alpha(widget.theme_manager, "timeline.ruler.minor.tick.alpha"))
        painter.setPen(QPen(minor_tick_col, 1))
        minor_steps_count = int(math.floor(duration / minor_step + 1e-9))
        for minor_index in range(minor_steps_count + 1):
            if minor_index % minor_divisions == 0:
                continue
            t_minor = minor_index * minor_step
            x = content_start_x + (t_minor / duration) * logical_width
            if x >= start_x - 20 and x <= end_x + 20:
                is_mid_tick = minor_divisions % 2 == 0 and minor_index % (minor_divisions // 2) == 0
                tick_bottom = ruler_top + (7 if is_mid_tick else 5)
                painter.drawLine(int(x), ruler_top, int(x), tick_bottom)
    major_steps_count = int(math.floor(duration / step_sec + 1e-9))
    for major_index in range(major_steps_count + 1):
        t = major_index * step_sec
        x = content_start_x + (t / duration) * logical_width
        if x >= start_x - 50 and x <= end_x + 50:
            label_text = timeline_viewport.format_time(t, step_sec)
            painter.setPen(QPen(text_col, 1))
            painter.drawLine(int(x), ruler_top, int(x), ruler_top + 10)
            text_rect = QRectF(x + 4, ruler_top + 11, 52, max(18, ruler_bottom - ruler_top - 11 - 4))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label_text)
    painter.restore()

def draw_sticky_gutter_overlay(widget, painter: QPainter, *, scroll_offset: int, rows_top: int, rows_bottom: int, footer_top: int, gutter_bg: QColor, track_bg: QColor, text_col: QColor, sep_color: QColor | None = None, sep_soft: QColor | None = None, damage_top: float | None = None, damage_bottom: float | None = None) -> None:
    gx = scroll_offset
    # Same row-window virtualization as draw_rows: only gutter labels
    # intersecting the viewport are visited. The clip is additionally
    # intersected with the vertical damage band so a partial repaint does
    # not redo the whole gutter column.
    clip_top = max(0.0, damage_top) if damage_top is not None else 0.0
    clip_bottom = min(float(footer_top), damage_bottom) if damage_bottom is not None else float(footer_top)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.save()
    painter.setClipRect(QRectF(gx, clip_top, widget.LEFT_GUTTER + 2, max(0.0, clip_bottom - clip_top)))
    timeline_primitives.draw_gutter_background(widget, painter, QRectF(gx, 0, widget.LEFT_GUTTER, widget.height()), gutter_bg, sep_soft if sep_soft is not None else QColor(text_col))
    tm = widget.theme_manager
    track_wash = _wash_alpha(tm, "timeline.group.wash.track.alpha")
    first_wash = _wash_alpha(tm, "timeline.group.wash.first.alpha")
    channel_wash = _wash_alpha(tm, "timeline.group.wash.channel.alpha")
    for kind, key, rect in timeline_layout.iter_row_rects(widget, rows_top, rows_bottom):
        y = rect.top()
        row_h = rect.height()
        if kind == "group":
            group = key[1]
            timeline_primitives.draw_group_header_label(widget, painter, QRectF(gx, y, widget.LEFT_GUTTER, row_h), group, group.label, text_col, sep_soft if sep_soft is not None else QColor(text_col))
        elif kind == "track_single":
            _kind, group, track, _channel = key
            painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, track_bg, group, track_wash))
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(gx + 18, y, max(40.0, widget.LEFT_GUTTER - 30), row_h), track.label, text_col)
        else:
            _kind, group, track, channel, is_first_channel = key
            line_col = timeline_theme.track_color(
                widget,
                track.kind,
                channel.kind,
                track_accent_color=getattr(track, "accent_color", None),
                channel_accent_color=getattr(channel, "accent_color", None),
            )
            if is_first_channel:
                painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, track_bg, group, first_wash))
                timeline_primitives.draw_track_title_label(widget, painter, QRectF(gx + 18, y, max(40.0, widget.LEFT_GUTTER * 0.44 - 22), row_h), track.label, text_col)
            else:
                painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, gutter_bg, group, channel_wash))
            channel_col = QColor(text_col)
            channel_col.setAlpha(215 if is_first_channel else 195)
            ch_x = gx + max(42.0, widget.LEFT_GUTTER * 0.50)
            timeline_primitives.draw_channel_label(widget, painter, QRectF(ch_x, y, widget.LEFT_GUTTER - (ch_x - gx) - 12, row_h), channel.label, channel_col, line_col)
    line_color = sep_color if sep_color is not None else text_col
    painter.setPen(QPen(line_color, 1))
    painter.drawLine(int(gx + widget.LEFT_GUTTER), 0, int(gx + widget.LEFT_GUTTER), widget.height())
    painter.restore()

def draw_sticky_right_gutter_overlay(widget, painter: QPainter, *, gutter_x: float, footer_bg: QColor, sep_soft: QColor) -> None:
    gutter_width = timeline_viewport.right_inset(widget)
    if gutter_width <= 0:
        return
    painter.save()
    painter.setClipRect(QRectF(gutter_x, 0, gutter_width, widget.height()))
    timeline_primitives.draw_right_gutter_background(
        widget,
        painter,
        QRectF(gutter_x, 0, gutter_width, widget.height()),
        footer_bg,
        sep_soft,
    )
    painter.restore()

def paint_timeline(widget, painter: QPainter, event) -> None:
    """Paint entry for ``TimelineWidget.paintEvent``.

    Paint contract (Phase A):

    - Damage/clip: ``event.rect()`` is the damage rect. It is converted to
      content coordinates once (``start_x``/``end_x``, clamped to the
      visible content span) and every pass below culls against it:
      the thumbnail strip computes its first/last frame from the damage,
      ``draw_rows`` paints only the ``layout.visible_row_window`` slice with
      lane fills clipped to the damage and per-row segment culling via
      ``layout.row_time_x_range``, the ruler skips off-damage ticks/labels,
      the sticky gutter overlay clips to the vertical damage band, and the
      selection/playhead passes are skipped when fully outside the damage.
    - No geometry mutation: this function — and everything it calls — must
      never call ``setGeometry``/``setVisible``/``setFixedWidth``/
      ``setMinimum*``/``updateGeometry``/``update``/``repaint`` on the
      widget or its scrollbars. Vertical-scrollbar sync lives outside paint
      (``resizeEvent``/``_onViewportGeometryChanged``/``_on_layout_settle``/
      ``_on_scale_changed``/``_on_host_scroll`` in ``widget.py``, via
      ``viewport.update_vertical_scrollbar``); the pure desired state is
      queryable through ``viewport.vertical_scrollbar_state``.
    - Scratch state: ``widget._hover_points`` is rebuilt every paint, but
      it is hit-test scratch, not geometry — and it is damage-scoped, since
      only the unculled segment passes append to it. All signals, slots,
      and public widget methods are untouched by this module.
    """
    if _timeline_debug_enabled():
        _sa = timeline_viewport.get_scroll_area(widget)
        _so = _sa.horizontalScrollBar().value() if _sa else -1
        _vpw = timeline_viewport.get_viewport_width(widget)
        _lw = timeline_viewport.get_logical_width(widget)
        _sw = timeline_viewport.get_slot_width(widget)
        _timeline_paint_debug("paint id=%s rect=%s width=%s logical=%s slot=%s scroll=%s vpw=%s right_inset=%s total=%s thumb_n=%s", id(widget), event.rect(), widget.width(), _lw, _sw, _so, _vpw, timeline_viewport.right_inset(widget), widget._total_frames, len(widget._thumbnails))
    # Paint contract: no geometry mutation here. Scrollbar sync happens in
    # the resize/settle/scroll paths (widget.py); see the docstring above.
    colors = timeline_theme.build_theme_colors(widget)
    accent = colors["accent"]
    text_col = colors["text_col"]
    canvas_bg = colors["canvas_bg"]
    gutter_bg = colors["gutter_bg"]
    track_bg = colors["track_bg"]
    lane_bg = colors["lane_bg"]
    grid_col = colors["grid_col"]
    footer_bg = colors["footer_bg"]
    sep_strong = colors["sep_strong"]
    sep_soft = colors["sep_soft"]
    sb_idle = colors["sb_idle"]
    sb_hover = colors["sb_hover"]

    widget._hover_points = []
    painter.fillRect(widget.rect(), canvas_bg)
    timeline_primitives.draw_gutter_background(widget, painter, QRectF(0, 0, widget.LEFT_GUTTER, widget.height()), gutter_bg, sep_soft)
    if widget._total_frames <= 0:
        return
    width = widget.width()
    logical_width = timeline_viewport.get_logical_width(widget)
    slot_width = timeline_viewport.get_slot_width(widget)
    content_scroll_y = timeline_viewport.vertical_scroll_value(widget)
    strip_top = -content_scroll_y
    footer_height_val = timeline_viewport.footer_height(widget)
    footer_top = widget.height() - footer_height_val
    scrollbar_strip_top = footer_top
    ruler_top = footer_top + widget.SCROLLBAR_STRIP_HEIGHT + 2
    ruler_bottom = widget.height() - 6
    content_start_x = widget.LEFT_GUTTER
    scroll_area = timeline_viewport.get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    viewport_width = timeline_viewport.get_viewport_width(widget)
    visible_right = scroll_offset + viewport_width
    content_right = visible_right - timeline_viewport.right_inset(widget)
    content_viewport_width = max(0, viewport_width - timeline_viewport.right_inset(widget))
    clip_rect = event.rect()
    start_x = max(content_start_x, clip_rect.left())
    end_x = min(clip_rect.right(), content_right)
    painter.save()
    painter.setClipRect(QRectF(0, 0, content_right, footer_top))
    draw_thumbnail_strip(widget, painter, canvas_bg=canvas_bg, content_start_x=content_start_x, strip_top=strip_top, width=content_right, start_x=start_x, end_x=end_x, logical_width=logical_width, slot_width=slot_width)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(text_col, 1))
    duration = timeline_layout.content_duration(widget)
    painter.setPen(QPen(sep_strong, 1))
    painter.drawLine(widget.LEFT_GUTTER, 0, widget.LEFT_GUTTER, widget.height())
    _content_top, rows_bottom = timeline_viewport.content_viewport_bounds(widget)
    rows_top = widget.STRIP_HEIGHT - content_scroll_y
    draw_rows(widget, painter, width=content_right, rows_top=rows_top, rows_bottom=rows_bottom, content_start_x=content_start_x, start_x=start_x, end_x=end_x, duration=duration, logical_width=logical_width, gutter_bg=gutter_bg, track_bg=track_bg, lane_bg=lane_bg, text_col=text_col, sep_soft=sep_soft)
    painter.restore()
    if widget._has_selection:
        x_anchor = timeline_viewport.frame_to_pos(widget, widget._anchor_index)
        x_drag = timeline_viewport.frame_to_pos(widget, widget._drag_index)
        x_start = min(x_anchor, x_drag)
        x_end = max(x_anchor, x_drag)
        sel_x0 = max(x_start, start_x)
        sel_x1 = min(x_end, content_right, end_x)
        if sel_x1 > sel_x0:
            fill = QColor(accent)
            fill.setAlpha(45)
            painter.fillRect(QRectF(sel_x0, 0, sel_x1 - sel_x0, footer_top), fill)
            # Edge handles so the range can be resized / moved after Shift+drag.
            handle = QColor(accent)
            handle.setAlpha(220)
            edge_w = 2.0
            for x_edge in (x_start, x_end):
                if x_edge < start_x - edge_w or x_edge > end_x + edge_w:
                    continue
                painter.fillRect(QRectF(x_edge - edge_w * 0.5, 0, edge_w, footer_top), handle)
            grip_h = 10.0
            grip_w = 6.0
            grip_y = max(2.0, (widget.STRIP_HEIGHT - grip_h) * 0.5)
            for x_edge in (x_start, x_end):
                if x_edge < start_x - grip_w or x_edge > end_x + grip_w:
                    continue
                painter.fillRect(QRectF(x_edge - grip_w * 0.5, grip_y, grip_w, grip_h), handle)
    draw_footer_and_ruler(widget, painter, width=content_right, content_start_x=content_start_x, footer_height=footer_height_val, footer_top=footer_top, scrollbar_strip_top=scrollbar_strip_top, ruler_top=ruler_top, ruler_bottom=ruler_bottom, scroll_offset=scroll_offset, viewport_width=content_viewport_width, duration=duration, logical_width=logical_width, start_x=start_x, end_x=end_x, footer_bg=footer_bg, sep_strong=sep_strong, sep_soft=sep_soft, grid_col=grid_col, text_col=text_col, sb_idle=sb_idle, sb_hover=sb_hover)
    x_head = timeline_viewport.visual_pos_from_index(widget, widget._scrub_visual_index if widget._scrub_visual_index is not None else widget._visual_index)
    if start_x - widget.HANDLE_WIDTH <= x_head <= end_x + widget.HANDLE_WIDTH:
        timeline_primitives.draw_playhead(widget, painter, x_head=x_head, footer_top=footer_top, width=content_right)
    draw_sticky_gutter_overlay(widget, painter, scroll_offset=scroll_offset, rows_top=rows_top, rows_bottom=rows_bottom, footer_top=footer_top, gutter_bg=gutter_bg, track_bg=track_bg, text_col=text_col, sep_color=sep_strong, sep_soft=sep_soft, damage_top=float(clip_rect.top()), damage_bottom=float(clip_rect.bottom()))
    draw_sticky_right_gutter_overlay(
        widget,
        painter,
        gutter_x=content_right,
        footer_bg=footer_bg,
        sep_soft=sep_soft,
    )
