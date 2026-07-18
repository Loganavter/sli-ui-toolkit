from __future__ import annotations

from PySide6.QtCore import QPointF, Qt

from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from . import layout as timeline_layout
from . import viewport as timeline_viewport


def _clamp_frame(widget, frame: int) -> int:
    last = max(0, int(widget._total_frames) - 1)
    return max(0, min(int(frame), last))


def _selection_bounds(widget) -> tuple[int, int] | None:
    if not widget._has_selection:
        return None
    lo = min(int(widget._anchor_index), int(widget._drag_index))
    hi = max(int(widget._anchor_index), int(widget._drag_index))
    return lo, hi


def selection_hit_zone(widget, x: float) -> str | None:
    """Return ``resize_lo``, ``resize_hi``, ``move``, or ``None`` for *x*."""
    bounds = _selection_bounds(widget)
    if bounds is None:
        return None
    lo, hi = bounds
    x_lo = float(timeline_viewport.frame_to_pos(widget, lo))
    x_hi = float(timeline_viewport.frame_to_pos(widget, hi))
    if x_lo > x_hi:
        x_lo, x_hi = x_hi, x_lo
    hit = float(getattr(widget, "SELECTION_EDGE_HIT_PX", 8))
    # Degenerate / tiny ranges: prefer edge hits over body move.
    if abs(x_hi - x_lo) <= hit * 2:
        mid = (x_lo + x_hi) * 0.5
        return "resize_lo" if float(x) <= mid else "resize_hi"
    if abs(float(x) - x_lo) <= hit:
        return "resize_lo"
    if abs(float(x) - x_hi) <= hit:
        return "resize_hi"
    if x_lo < float(x) < x_hi:
        return "move"
    return None


def _apply_selection_edit(widget, frame: int) -> None:
    mode = widget._selection_edit_mode
    if mode is None:
        return
    frame = _clamp_frame(widget, frame)
    lo0 = int(widget._selection_edit_lo0)
    hi0 = int(widget._selection_edit_hi0)
    last = max(0, int(widget._total_frames) - 1)

    if mode == "resize_lo":
        lo = min(frame, hi0)
        hi = hi0
    elif mode == "resize_hi":
        lo = lo0
        hi = max(frame, lo0)
    elif mode == "move":
        delta = frame - int(widget._selection_edit_origin_frame)
        width = hi0 - lo0
        lo = lo0 + delta
        hi = hi0 + delta
        if lo < 0:
            hi -= lo
            lo = 0
        if hi > last:
            lo -= hi - last
            hi = last
        lo = max(0, lo)
        hi = min(last, max(lo, lo + width if width > 0 else lo))
    else:
        return

    widget._anchor_index = int(lo)
    widget._drag_index = int(hi)
    widget._has_selection = True


def mouse_press_event(widget, event):
    if event.button() != Qt.MouseButton.LeftButton:
        return

    toggle_group = timeline_layout.group_toggle_hit(widget, event.pos())
    if toggle_group is not None:
        widget._tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        widget._mouse_down = False
        widget._press_pos = None
        widget._toggle_group_collapsed(toggle_group)
        event.accept()
        return

    if timeline_viewport.is_on_gutter_handle(widget, event.pos().x()):
        widget._is_resizing_gutter = True
        widget._tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        widget.setCursor(Qt.CursorShape.SplitHCursor)
        event.accept()
        return

    sb_rect = timeline_viewport.sb_strip_rect(widget)
    if sb_rect.contains(QPointF(event.pos())):
        scroll_area = timeline_viewport.get_scroll_area(widget)
        if scroll_area is not None:
            h_bar = scroll_area.horizontalScrollBar()
            handle_rect = timeline_viewport.get_inner_sb_handle_rect(widget, sb_rect)
            padding = 8.0
            track_w = sb_rect.width() - padding * 2
            total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
            handle_w = max(20.0, (h_bar.pageStep() / total) * track_w) if total > 0 else 20.0
            if handle_rect.isEmpty() or not handle_rect.contains(QPointF(event.pos())):
                scroll_range = h_bar.maximum() - h_bar.minimum()
                viewport_x = event.pos().x() - h_bar.value()
                rel_x = viewport_x - widget.LEFT_GUTTER - padding - handle_w / 2.0
                if track_w - handle_w > 0 and scroll_range > 0:
                    new_val = h_bar.minimum() + int(rel_x / (track_w - handle_w) * scroll_range)
                    h_bar.setValue(max(h_bar.minimum(), min(new_val, h_bar.maximum())))
            widget._sb_dragging = True
            widget._sb_drag_start_x = event.pos().x() - h_bar.value()
            widget._sb_drag_start_value = h_bar.value()
            widget.update()
        event.accept()
        return

    x = max(widget.LEFT_GUTTER, event.pos().x())
    frame = timeline_viewport.pos_to_frame(widget, x)
    widget._scrub_visual_index = timeline_viewport.pos_to_float_index(widget, x)
    widget._mouse_down = True
    widget._press_pos = event.pos()
    widget._press_frame = frame
    widget._selection_edit_mode = None

    shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
    edit_zone = None if shift_pressed else selection_hit_zone(widget, x)
    if edit_zone is not None:
        bounds = _selection_bounds(widget)
        assert bounds is not None
        lo, hi = bounds
        widget._selection_edit_mode = edit_zone
        widget._selection_edit_origin_frame = frame
        widget._selection_edit_lo0 = lo
        widget._selection_edit_hi0 = hi
        widget._is_selecting = False
        widget._has_selection = True
        if edit_zone == "resize_lo":
            widget.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edit_zone == "resize_hi":
            widget.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            widget.setCursor(Qt.CursorShape.SizeAllCursor)
        widget.set_current_frame(frame)
        widget.headMoved.emit(widget._current_index)
        widget.update()
        event.accept()
        return

    if shift_pressed:
        widget._is_selecting = True
        widget._has_selection = True
        widget._anchor_index = frame
        widget._drag_index = frame
    else:
        widget._is_selecting = False
        widget._has_selection = False
        widget._anchor_index = frame
        widget._drag_index = frame

    widget.set_current_frame(frame)
    widget.headMoved.emit(widget._current_index)
    widget.update()


def mouse_move_event(widget, event):
    if widget._sb_dragging:
        scroll_area = timeline_viewport.get_scroll_area(widget)
        if scroll_area is not None:
            sb_rect = timeline_viewport.sb_strip_rect(widget)
            h_bar = scroll_area.horizontalScrollBar()
            padding = 8.0
            track_w = sb_rect.width() - padding * 2
            total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
            handle_w = max(20.0, (h_bar.pageStep() / total) * track_w) if total > 0 else 20.0
            scroll_range = h_bar.maximum() - h_bar.minimum()
            if track_w - handle_w > 0 and scroll_range > 0:
                current_vp_x = event.pos().x() - h_bar.value()
                dx = current_vp_x - widget._sb_drag_start_x
                delta_val = int(dx / (track_w - handle_w) * scroll_range)
                h_bar.setValue(
                    max(h_bar.minimum(), min(widget._sb_drag_start_value + delta_val, h_bar.maximum()))
                )
        widget.update()
        event.accept()
        return

    if widget._is_resizing_gutter:
        scroll_area = timeline_viewport.get_scroll_area(widget)
        scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
        widget.LEFT_GUTTER = max(
            widget.MIN_LEFT_GUTTER,
            min(event.pos().x() - scroll_offset, widget.MAX_LEFT_GUTTER),
        )
        widget._last_min_zoom = timeline_viewport.calculate_min_zoom(widget)
        timeline_viewport.update_fixed_width(widget)
        widget.update()
        event.accept()
        return

    timeline_viewport.update_hover_tooltip(widget, event.pos())
    hover_x = max(widget.LEFT_GUTTER, event.pos().x())
    if timeline_layout.group_toggle_hit(widget, event.pos()) is not None:
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
    elif timeline_viewport.is_on_gutter_handle(widget, event.pos().x()):
        widget.setCursor(Qt.CursorShape.SplitHCursor)
    elif widget._selection_edit_mode in {"resize_lo", "resize_hi"}:
        widget.setCursor(Qt.CursorShape.SizeHorCursor)
    elif widget._selection_edit_mode == "move":
        widget.setCursor(Qt.CursorShape.SizeAllCursor)
    else:
        zone = selection_hit_zone(widget, hover_x)
        if zone in {"resize_lo", "resize_hi"}:
            widget.setCursor(Qt.CursorShape.SizeHorCursor)
        elif zone == "move":
            widget.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            widget.unsetCursor()

    if event.buttons() & Qt.MouseButton.LeftButton:
        scrub_x = max(widget.LEFT_GUTTER, event.pos().x())
        frame = timeline_viewport.pos_to_frame(widget, scrub_x)
        widget._scrub_visual_index = float(frame)

        if widget._selection_edit_mode is not None:
            _apply_selection_edit(widget, frame)
            widget.set_current_frame(frame)
            widget.headMoved.emit(widget._current_index)
            widget.update()
            return

        shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if (
            shift_pressed
            and not widget._is_selecting
            and widget._mouse_down
            and widget._press_pos is not None
        ):
            moved = (event.pos() - widget._press_pos).manhattanLength()
            if moved >= widget._drag_threshold_px:
                widget._is_selecting = True
                widget._has_selection = True
                widget._anchor_index = widget._press_frame
                widget._drag_index = frame

        if widget._is_selecting:
            widget._drag_index = frame

        widget.set_current_frame(frame)
        widget.headMoved.emit(widget._current_index)
        widget.update()


def leave_event(widget, event):
    widget.unsetCursor()
    widget._tooltip_timer.stop()
    widget._hover_tooltip_text = None
    widget._hover_tooltip_pos = None
    PathTooltip.get_instance().hide_tooltip()


def mouse_release_event(widget, event):
    if event.button() == Qt.MouseButton.LeftButton:
        if widget._sb_dragging:
            widget._sb_dragging = False
            widget.update()
            event.accept()
            return
        if widget._is_resizing_gutter:
            widget._is_resizing_gutter = False
            widget.unsetCursor()
            event.accept()
            return
        widget._scrub_visual_index = None
        widget._mouse_down = False
        widget._press_pos = None
        widget._selection_edit_mode = None
    if widget._has_selection and widget._anchor_index == widget._drag_index:
        widget._has_selection = False
    widget._is_selecting = False
    widget.update()
