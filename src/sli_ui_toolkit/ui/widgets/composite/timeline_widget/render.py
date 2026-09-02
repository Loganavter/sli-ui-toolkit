from __future__ import annotations

import bisect
import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from . import layout as timeline_layout
from . import primitives as timeline_primitives
from . import theme as timeline_theme
from . import viewport as timeline_viewport
from .segments import _draw_keyframe_segments

def draw_thumbnail_strip(widget, painter: QPainter, *, canvas_bg: QColor, content_start_x: float, strip_top: float, width: int, start_x: float, end_x: float, logical_width: float, slot_width: float) -> None:
    painter.fillRect(QRectF(content_start_x, strip_top, width - content_start_x, widget.STRIP_HEIGHT), canvas_bg)
    base_tile = timeline_viewport.get_base_tile_width(widget)
    frame_step = 1 if slot_width >= base_tile else math.ceil(base_tile / slot_width)
    draw_w = frame_step * slot_width
    first_frame = max(0, int((start_x - content_start_x) / draw_w) * frame_step)
    last_frame = min(widget._total_frames, int((end_x - content_start_x) / draw_w + 1) * frame_step + frame_step)
    try:
        import os, logging
        if os.getenv("IMGSLI_VIDEO_EDITOR_DEBUG") == "1" or os.getenv("IMGSLI_TIMELINE_DEBUG") == "1":
            # Check if strip is actually visible in widget
            logging.getLogger("ImproveImgSLI").warning("[timeline-paint] draw_strip id=%s vis=%s width=%s start_x=%s end_x=%s logical=%s slot=%s base=%s step=%s draw_w=%s first=%s last=%s total=%s thumb_n=%s thumb_ids=%s strip_top=%s height=%s isVisible=%s", id(widget), widget.isVisible(), width, start_x, end_x, logical_width, slot_width, base_tile, frame_step, draw_w, first_frame, last_frame, widget._total_frames, len(widget._thumbnails), sorted(list(widget._thumbnails.keys()))[:12], strip_top, widget.height(), widget.isVisible())
            # Log per-block pixmap validity
            for _fi in range(first_frame, min(last_frame, first_frame+3)):
                import bisect
                _ti = -1
                if widget._thumb_indices:
                    _pos = bisect.bisect_right(widget._thumb_indices, _fi)
                    _ti = widget._thumb_indices[_pos-1] if _pos>0 else widget._thumb_indices[0]
                _pix = widget._thumbnails.get(_ti) if _ti!=-1 else None
                logging.getLogger("ImproveImgSLI").warning("[timeline-paint] block fi=%s thumb_idx=%s pix_null=%s pix_size=%s", _fi, _ti, _pix.isNull() if _pix else True, (_pix.width(), _pix.height()) if _pix and not _pix.isNull() else None)
    except Exception:
        pass

    frame_idx = first_frame
    while frame_idx < last_frame:
        block_x = content_start_x + frame_idx * slot_width
        block_w = draw_w
        if block_x + block_w > content_start_x + logical_width:
            block_w = content_start_x + logical_width - block_x
        # Viewport edge: when at 100% zoom window lacks space, crop rightmost
        # visible block as if tape continues beyond viewport (not just logical end)
        if block_x + block_w > width:
            block_w = width - block_x
        if block_w <= 0:
            break
        thumb_idx = -1
        if widget._thumb_indices:
            pos = bisect.bisect_right(widget._thumb_indices, frame_idx)
            thumb_idx = widget._thumb_indices[pos - 1] if pos > 0 else widget._thumb_indices[0]
        if thumb_idx != -1:
            pix = widget._thumbnails.get(thumb_idx)
            if pix and pix.height() > 0:
                # Tail crop on every px: continuous base_tile not quantized draw_w
                if block_w + 0.5 < draw_w:
                    src_w = pix.width() * (block_w / base_tile) if base_tile > 0 else pix.width()
                    src_w = min(float(pix.width()), max(0.0, src_w))
                    src_rect = QRectF(0, 0, src_w, float(pix.height()))
                    painter.drawPixmap(QRectF(block_x, strip_top, block_w, float(widget.STRIP_HEIGHT)), pix, src_rect)
                else:
                    painter.drawPixmap(QRectF(block_x, strip_top, block_w, float(widget.STRIP_HEIGHT)), pix, QRectF(pix.rect()))
        frame_idx += frame_step

def draw_rows(widget, painter: QPainter, *, width: int, rows_top: int, rows_bottom: int, content_start_x: float, start_x: float, end_x: float, duration: float, logical_width: float, is_dark: bool, gutter_bg: QColor, track_bg: QColor, lane_bg: QColor, text_col: QColor, sep_soft: QColor) -> None:
    content_top = 0
    y = rows_top
    for item in widget._row_layout:
        if item[0] == "group":
            group = item[1]
            row_h = widget.GROUP_HEADER_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            timeline_primitives.draw_group_header_label(widget, painter, QRectF(0, y, widget.LEFT_GUTTER, row_h), group, group.label, text_col, sep_soft)
            y += row_h
            continue

        if item[0] == "track_single":
            _kind, group, track, channel = item
            row_h = widget.TRACK_ROW_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            line_col = timeline_theme.track_line_color(
                widget,
                track.id,
                track.kind,
                channel.kind,
                track_accent_color=getattr(track, "accent_color", None),
                channel_accent_color=getattr(channel, "accent_color", None),
            )
            gutter_track_bg = timeline_theme.group_content_bg(widget, track_bg, group, 46 if is_dark else 22)
            painter.fillRect(QRectF(0, y, width, row_h), gutter_track_bg)
            painter.fillRect(QRectF(content_start_x, y, width - content_start_x, row_h), lane_bg)
            painter.setPen(QPen(QColor(210, 210, 214), 1))
            painter.drawLine(0, y + row_h, width, y + row_h)
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(18, y, max(40, widget.LEFT_GUTTER - 30), row_h), track.label, text_col)
            row_center_y = y + row_h / 2.0
            painter.setPen(QPen(QColor(190, 190, 196), 1))
            painter.drawLine(int(content_start_x), int(row_center_y), width, int(row_center_y))
            _draw_keyframe_segments(widget, painter, group=group, track=track, channel=channel, duration=duration, logical_width=logical_width, row_center_y=row_center_y, start_x=start_x, end_x=end_x, line_col=line_col, point_radius=4.0)
            y += row_h
            continue

        _kind, group, track, channel, is_first_channel = item
        row_h = widget.CHANNEL_ROW_HEIGHT
        row_bottom = y + row_h
        if row_bottom <= content_top:
            y += row_h
            continue
        if y >= rows_bottom:
            break
        line_col = timeline_theme.track_line_color(
            widget,
            track.id,
            track.kind,
            channel.kind,
            track_accent_color=getattr(track, "accent_color", None),
            channel_accent_color=getattr(channel, "accent_color", None),
        )
        if is_first_channel:
            painter.fillRect(QRectF(0, y, width, row_h), timeline_theme.group_content_bg(widget, track_bg, group, 42 if is_dark else 18))
        else:
            painter.fillRect(QRectF(0, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, gutter_bg, group, 24 if is_dark else 10))
        painter.fillRect(QRectF(content_start_x, y, width - content_start_x, row_h), lane_bg)
        painter.setPen(QPen(QColor(210, 210, 214), 1))
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
        row_center_y = y + row_h / 2.0
        painter.setPen(QPen(QColor(190, 190, 196), 1))
        painter.drawLine(int(content_start_x), int(row_center_y), width, int(row_center_y))
        _draw_keyframe_segments(widget, painter, group=group, track=track, channel=channel, duration=duration, logical_width=logical_width, row_center_y=row_center_y, start_x=start_x, end_x=end_x, line_col=line_col, point_radius=3.5)
        y += row_h

def draw_footer_and_ruler(widget, painter: QPainter, *, width: int, content_start_x: float, footer_height: int, footer_top: int, scrollbar_strip_top: int, ruler_top: int, ruler_bottom: int, scroll_offset: int, viewport_width: int, duration: float, logical_width: float, start_x: float, end_x: float, is_dark: bool, footer_bg: QColor, sep_strong: QColor, sep_soft: QColor, grid_col: QColor, text_col: QColor, sb_idle: QColor, sb_hover: QColor) -> None:
    painter.fillRect(QRectF(content_start_x, footer_top, width - content_start_x, footer_height), footer_bg)
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
        minor_tick_col.setAlpha(150 if is_dark else 180)
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

def draw_sticky_gutter_overlay(widget, painter: QPainter, *, scroll_offset: int, rows_top: int, rows_bottom: int, footer_top: int, gutter_bg: QColor, track_bg: QColor, text_col: QColor, sep_color: QColor | None = None, sep_soft: QColor | None = None) -> None:
    gx = scroll_offset
    content_top = 0
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.save()
    painter.setClipRect(QRectF(gx, 0, widget.LEFT_GUTTER + 2, footer_top))
    timeline_primitives.draw_gutter_background(widget, painter, QRectF(gx, 0, widget.LEFT_GUTTER, widget.height()), gutter_bg, sep_soft if sep_soft is not None else QColor(text_col))
    y = rows_top
    for item in widget._row_layout:
        if item[0] == "group":
            group = item[1]
            row_h = widget.GROUP_HEADER_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            timeline_primitives.draw_group_header_label(widget, painter, QRectF(gx, y, widget.LEFT_GUTTER, row_h), group, group.label, text_col, sep_soft if sep_soft is not None else QColor(text_col))
            y += row_h
        elif item[0] == "track_single":
            _kind, group, track, _channel = item
            row_h = widget.TRACK_ROW_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, track_bg, group, 46 if widget.theme_manager.is_dark() else 22))
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(gx + 18, y, max(40.0, widget.LEFT_GUTTER - 30), row_h), track.label, text_col)
            y += row_h
        else:
            _kind, group, track, channel, is_first_channel = item
            row_h = widget.CHANNEL_ROW_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            line_col = timeline_theme.track_color(
                widget,
                track.kind,
                channel.kind,
                track_accent_color=getattr(track, "accent_color", None),
                channel_accent_color=getattr(channel, "accent_color", None),
            )
            if is_first_channel:
                painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, track_bg, group, 42 if widget.theme_manager.is_dark() else 18))
                timeline_primitives.draw_track_title_label(widget, painter, QRectF(gx + 18, y, max(40.0, widget.LEFT_GUTTER * 0.44 - 22), row_h), track.label, text_col)
            else:
                painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, gutter_bg, group, 24 if widget.theme_manager.is_dark() else 10))
            channel_col = QColor(text_col)
            channel_col.setAlpha(215 if is_first_channel else 195)
            ch_x = gx + max(42.0, widget.LEFT_GUTTER * 0.50)
            timeline_primitives.draw_channel_label(widget, painter, QRectF(ch_x, y, widget.LEFT_GUTTER - (ch_x - gx) - 12, row_h), channel.label, channel_col, line_col)
            y += row_h
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
    try:
        import os, logging
        if os.getenv("IMGSLI_VIDEO_EDITOR_DEBUG") == "1" or os.getenv("IMGSLI_TIMELINE_DEBUG") == "1":
            from sli_ui_toolkit.ui.widgets.composite.timeline_widget import viewport as _vp
            _sa = _vp.get_scroll_area(widget)
            _so = _sa.horizontalScrollBar().value() if _sa else -1
            _vpw = _vp.get_viewport_width(widget)
            _lw = _vp.get_logical_width(widget)
            _sw = _vp.get_slot_width(widget)
            logging.getLogger("ImproveImgSLI").warning("[timeline-paint] paint id=%s rect=%s width=%s logical=%s slot=%s scroll=%s vpw=%s right_inset=%s total=%s thumb_n=%s", id(widget), event.rect(), widget.width(), _lw, _sw, _so, _vpw, _vp.right_inset(widget), widget._total_frames, len(widget._thumbnails))
    except Exception:
        pass
    timeline_viewport.update_vertical_scrollbar(widget)
    colors = timeline_theme.build_theme_colors(widget)
    is_dark = colors["is_dark"]
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
    draw_rows(widget, painter, width=content_right, rows_top=rows_top, rows_bottom=rows_bottom, content_start_x=content_start_x, start_x=start_x, end_x=end_x, duration=duration, logical_width=logical_width, is_dark=is_dark, gutter_bg=gutter_bg, track_bg=track_bg, lane_bg=lane_bg, text_col=text_col, sep_soft=sep_soft)
    painter.restore()
    if widget._has_selection:
        x_anchor = timeline_viewport.frame_to_pos(widget, widget._anchor_index)
        x_drag = timeline_viewport.frame_to_pos(widget, widget._drag_index)
        x_start = min(x_anchor, x_drag)
        x_end = max(x_anchor, x_drag)
        fill = QColor(accent)
        fill.setAlpha(45)
        painter.fillRect(QRectF(x_start, 0, max(0.0, min(x_end, content_right) - x_start), footer_top), fill)
        # Edge handles so the range can be resized / moved after Shift+drag.
        handle = QColor(accent)
        handle.setAlpha(220)
        edge_w = 2.0
        painter.fillRect(QRectF(x_start - edge_w * 0.5, 0, edge_w, footer_top), handle)
        painter.fillRect(QRectF(x_end - edge_w * 0.5, 0, edge_w, footer_top), handle)
        grip_h = 10.0
        grip_w = 6.0
        grip_y = max(2.0, (widget.STRIP_HEIGHT - grip_h) * 0.5)
        painter.fillRect(QRectF(x_start - grip_w * 0.5, grip_y, grip_w, grip_h), handle)
        painter.fillRect(QRectF(x_end - grip_w * 0.5, grip_y, grip_w, grip_h), handle)
    draw_footer_and_ruler(widget, painter, width=content_right, content_start_x=content_start_x, footer_height=footer_height_val, footer_top=footer_top, scrollbar_strip_top=scrollbar_strip_top, ruler_top=ruler_top, ruler_bottom=ruler_bottom, scroll_offset=scroll_offset, viewport_width=content_viewport_width, duration=duration, logical_width=logical_width, start_x=start_x, end_x=end_x, is_dark=is_dark, footer_bg=footer_bg, sep_strong=sep_strong, sep_soft=sep_soft, grid_col=grid_col, text_col=text_col, sb_idle=sb_idle, sb_hover=sb_hover)
    x_head = timeline_viewport.visual_pos_from_index(widget, widget._scrub_visual_index if widget._scrub_visual_index is not None else widget._visual_index)
    timeline_primitives.draw_playhead(widget, painter, x_head=x_head, footer_top=footer_top, width=content_right)
    draw_sticky_gutter_overlay(widget, painter, scroll_offset=scroll_offset, rows_top=rows_top, rows_bottom=rows_bottom, footer_top=footer_top, gutter_bg=gutter_bg, track_bg=track_bg, text_col=text_col, sep_color=sep_strong, sep_soft=sep_soft)
    draw_sticky_right_gutter_overlay(
        widget,
        painter,
        gutter_x=content_right,
        footer_bg=footer_bg,
        sep_soft=sep_soft,
    )
