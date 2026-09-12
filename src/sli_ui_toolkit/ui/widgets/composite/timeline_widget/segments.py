from __future__ import annotations

import math
from types import SimpleNamespace

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from . import layout as timeline_layout
from . import theme as timeline_theme
from . import viewport as timeline_viewport

def _segment_color(widget, track, channel, timestamp: float, fallback: QColor) -> QColor:
    if track.kind == "color":
        color = timeline_layout._color_track_value(track, timestamp)
        if color is not None:
            if color.alpha() <= 0:
                color.setAlpha(255)
            return color
    return timeline_theme.track_value_color(
        widget,
        track_id=track.id,
        track_kind=track.kind,
        channel_kind=channel.kind,
        value=timeline_layout._evaluate_channel_at_timestamp(channel, timestamp),
        fallback=fallback,
    )

def _draw_color_track_segments(
    widget,
    painter: QPainter,
    *,
    group,
    track,
    duration: float,
    logical_width: float,
    row_center_y: float,
    start_x: float,
    end_x: float,
    point_radius: float,
    stagger_px: float = 7.0,
) -> None:
    timestamps = sorted(
        {
            float(keyframe.timestamp)
            for channel in track.channels.values()
            for keyframe in channel.keyframes
        }
    )
    if not timestamps:
        return

    color_states: list[tuple[float, QColor]] = []
    for timestamp in timestamps:
        color = timeline_layout._color_track_value(track, timestamp)
        if color is None:
            continue
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        if color_states:
            prev_color = color_states[-1][1]
            prev_rgba = (
                prev_color.red(),
                prev_color.green(),
                prev_color.blue(),
                prev_color.alpha(),
            )
            if rgba == prev_rgba:
                continue
        color_states.append((timestamp, color))

    if not color_states:
        return

    left_bound = start_x - 12.0
    right_bound = end_x + 12.0
    segments: list[tuple[float, float, float, QColor, SimpleNamespace, SimpleNamespace]] = []

    for index, (timestamp, color) in enumerate(color_states):
        end_timestamp = (
            color_states[index + 1][0]
            if index + 1 < len(color_states)
            else duration
        )
        start_x_pos = timeline_layout.time_to_x(widget, timestamp, duration, logical_width)
        end_x_pos = timeline_layout.time_to_x(widget, end_timestamp, duration, logical_width)
        direction = -1.0 if index % 2 == 0 else 1.0
        y = row_center_y + direction * stagger_px
        start_keyframe_ref = SimpleNamespace(timestamp=timestamp, value=color)
        end_keyframe_ref = SimpleNamespace(timestamp=end_timestamp, value=color)
        segments.append(
            (start_x_pos, end_x_pos, y, color, start_keyframe_ref, end_keyframe_ref)
        )

    if not segments:
        return

    for x1, x2, y, color, _, _ in segments:
        if x2 < left_bound:
            continue
        if x1 > right_bound:
            break
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x1, y), QPointF(x2, y))

    painter.setPen(QPen(QColor(40, 40, 46), 1))
    for x1, x2, y, color, start_keyframe_ref, end_keyframe_ref in segments:
        painter.setBrush(QBrush(color))
        if left_bound <= x1 <= right_bound:
            painter.drawEllipse(QPointF(x1, y), point_radius, point_radius)
            widget._hover_points.append(
                (
                    QRectF(x1 - 6, y - 6, 12, 12),
                    timeline_viewport.tooltip_for_keyframe(
                        widget,
                        group,
                        track,
                        next(iter(track.channels.values())),
                        start_keyframe_ref,
                    ),
                )
            )
        if left_bound <= x2 <= right_bound:
            painter.drawEllipse(QPointF(x2, y), point_radius, point_radius)
            widget._hover_points.append(
                (
                    QRectF(x2 - 6, y - 6, 12, 12),
                    timeline_viewport.tooltip_for_keyframe(
                        widget,
                        group,
                        track,
                        next(iter(track.channels.values())),
                        end_keyframe_ref,
                    ),
                ),
            )

def _draw_enum_track_segments(
    widget,
    painter: QPainter,
    *,
    group,
    track,
    channel,
    duration: float,
    logical_width: float,
    row_center_y: float,
    start_x: float,
    end_x: float,
    point_radius: float,
    line_col: QColor,
    stagger_px: float = 7.0,
) -> None:
    keyframes = channel.keyframes
    if not keyframes:
        return

    states: list[tuple[float, object]] = []
    for keyframe in keyframes:
        timestamp = float(keyframe.timestamp)
        value = keyframe.value
        if states and states[-1][1] == value:
            continue
        states.append((timestamp, value))

    if not states:
        return

    left_bound = start_x - 12.0
    right_bound = end_x + 12.0
    segments: list[tuple[float, float, float, SimpleNamespace, SimpleNamespace]] = []
    active_index = 0

    for index, (timestamp, value) in enumerate(states):
        end_timestamp = states[index + 1][0] if index + 1 < len(states) else float(duration)
        if end_timestamp < timestamp:
            continue
        if not timeline_layout._is_track_active(widget, track, channel, timestamp):
            continue
        x1 = timeline_layout.time_to_x(widget, timestamp, duration, logical_width)
        x2 = timeline_layout.time_to_x(widget, end_timestamp, duration, logical_width)
        direction = -1.0 if active_index % 2 == 0 else 1.0
        y = row_center_y + direction * stagger_px
        start_ref = SimpleNamespace(timestamp=timestamp, value=value)
        end_ref = SimpleNamespace(timestamp=end_timestamp, value=value)
        segments.append((x1, x2, y, start_ref, end_ref))
        active_index += 1

    for x1, x2, y, _, _ in segments:
        if x2 < left_bound:
            continue
        if x1 > right_bound:
            break
        if abs(x2 - x1) <= 0.01:
            continue
        painter.setPen(QPen(line_col, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x1, y), QPointF(x2, y))

    painter.setPen(QPen(QColor(40, 40, 46), 1))
    point_positions: set[tuple[float, float]] = set()
    for x1, x2, y, start_ref, end_ref in segments:
        if left_bound <= x1 <= right_bound:
            point_key = (round(x1, 4), round(y, 4))
            if point_key not in point_positions:
                point_positions.add(point_key)
                painter.setBrush(QBrush(line_col))
                painter.drawEllipse(QPointF(x1, y), point_radius, point_radius)
                widget._hover_points.append(
                    (
                        QRectF(x1 - 6, y - 6, 12, 12),
                        timeline_viewport.tooltip_for_keyframe(
                            widget,
                            group,
                            track,
                            channel,
                            start_ref,
                        ),
                    )
                )
        if left_bound <= x2 <= right_bound and not math.isclose(
            float(end_ref.timestamp), float(duration), abs_tol=1e-9
        ):
            point_key = (round(x2, 4), round(y, 4))
            if point_key not in point_positions:
                point_positions.add(point_key)
                painter.setBrush(QBrush(line_col))
                painter.drawEllipse(QPointF(x2, y), point_radius, point_radius)
                widget._hover_points.append(
                    (
                        QRectF(x2 - 6, y - 6, 12, 12),
                        timeline_viewport.tooltip_for_keyframe(
                            widget,
                            group,
                            track,
                            channel,
                            end_ref,
                        ),
                    )
                )

def _curve_path(points: list[tuple[float, float]]) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(QPointF(points[0][0], points[0][1]))
    if len(points) == 1:
        return path
    if len(points) == 2:
        path.lineTo(QPointF(points[1][0], points[1][1]))
        return path

    for index in range(1, len(points) - 1):
        current_x, current_y = points[index]
        next_x, next_y = points[index + 1]
        mid_x = (current_x + next_x) * 0.5
        mid_y = (current_y + next_y) * 0.5
        path.quadTo(
            QPointF(current_x, current_y),
            QPointF(mid_x, mid_y),
        )
    last_x, last_y = points[-1]
    path.lineTo(QPointF(last_x, last_y))
    return path

def _draw_keyframe_segments(widget, painter: QPainter, *, group, track, channel, duration: float, logical_width: float, row_center_y: float, start_x: float, end_x: float, line_col: QColor, point_radius: float) -> None:
    if track.kind == "color":
        _draw_color_track_segments(
            widget,
            painter,
            group=group,
            track=track,
            duration=duration,
            logical_width=logical_width,
            row_center_y=row_center_y,
            start_x=start_x,
            end_x=end_x,
            point_radius=point_radius,
        )
        return
    if track.kind == "enum":
        _draw_enum_track_segments(
            widget,
            painter,
            group=group,
            track=track,
            channel=channel,
            duration=duration,
            logical_width=logical_width,
            row_center_y=row_center_y,
            start_x=start_x,
            end_x=end_x,
            point_radius=point_radius,
            line_col=line_col,
        )
        return
    segments = timeline_layout.visible_keyframe_segments(widget, track, channel, duration, logical_width, row_center_y, start_x, end_x)
    if segments:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for segment in segments:
            curve_points = segment.get("curve_points") or [
                (segment["x1"], segment["y"]),
                (segment["x2"], segment["y"]),
            ]
            segment_col = _segment_color(
                widget,
                track,
                channel,
                float(segment["start_kf"].timestamp),
                line_col,
            )
            painter.setPen(QPen(segment_col, 1.5))
            painter.drawPath(_curve_path(curve_points))

    drawn_points: set[tuple[float, float]] = set()

    def _draw_point_once(x: float, y: float, color: QColor, tooltip: str) -> None:
        key = (round(float(x), 2), round(float(y), 2))
        if key in drawn_points:
            return
        drawn_points.add(key)
        painter.setPen(QPen(QColor(40, 40, 46), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x, y), point_radius, point_radius)
        widget._hover_points.append((QRectF(x - 6, y - 6, 12, 12), tooltip))

    for segment in segments:
        curve_points = segment.get("curve_points") or [
            (segment["x1"], segment["y"]),
            (segment["x2"], segment["y"]),
        ]
        x1, y1 = curve_points[0]
        x2, y2 = curve_points[-1]
        start_kf = segment["start_kf"]
        end_kf = segment["end_kf"]
        start_col = _segment_color(
            widget,
            track,
            channel,
            float(start_kf.timestamp),
            line_col,
        )
        end_col = _segment_color(
            widget,
            track,
            channel,
            float(end_kf.timestamp),
            line_col,
        )
        _draw_point_once(
            x1,
            y1,
            start_col,
            timeline_viewport.tooltip_for_keyframe(widget, group, track, channel, start_kf),
        )
        _draw_point_once(
            x2,
            y2,
            end_col,
            timeline_viewport.tooltip_for_keyframe(widget, group, track, channel, end_kf),
        )
