from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPointF, Qt

import shiboken6 as sip

from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from . import layout as timeline_layout
from . import viewport as timeline_viewport
from .debug import _timeline_debug, _timeline_debug_enabled, _next_tick, gutter_debug


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
        clamped = timeline_viewport.clamp_gutter_width(
            widget, event.pos().x() - scroll_offset
        )
        nxt = widget._current_state().with_left_gutter(int(clamped))
        # CUTOVER-C landed (Phase 3C): gutter drag commits through the
        # single emit path — _commitState syncs LEFT_GUTTER itself.
        widget._commitState(nxt, source="gutterDrag")
        assert nxt.left_gutter == int(widget.LEFT_GUTTER)
        if _timeline_debug_enabled():
            gutter_debug(
                "tick=%s gutter-drag width=%s scroll=%s",
                _next_tick(), int(widget.LEFT_GUTTER), int(scroll_offset),
            )
        widget._last_min_zoom = timeline_viewport.calculate_min_zoom(widget)
        timeline_viewport.update_fixed_width(widget)
        # Band repaint via existing entry points only (update with a damage
        # rect; update_fixed_width above already issued the full update):
        # the band covers chevron + wash/edge gradients + the 1px
        # separator (see viewport.gutter_band_rect).
        try:
            widget.update(timeline_viewport.gutter_band_rect(widget, int(scroll_offset)))
        except Exception:
            pass
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


# --- thin-owner concern functions (wave T) -----------------------------------
# Bodies moved out of ``TimelineWidget``; the widget keeps thin same-named
# delegators (tests reach into privates). Every function takes the widget
# explicitly per the thin-owner rule. No behavior change: statement order,
# guards, and emit paths are verbatim moves.

#: Thumbnail store bound: ``_thumbnails`` stays index-addressed
#: (``dict[int, QPixmap]`` + sorted ``_thumb_indices``), but every insert
#: prunes entries outside the visible strip window
#: (``get_visible_thumbnail_frame_indices``) plus
#: ``_THUMBNAIL_KEEP_MARGIN_BLOCKS`` blocks of margin on each side.
#: ``_THUMBNAIL_HARD_CAP`` is the fail-stop backstop for fully fitted
#: timelines where the whole recording is visible (farthest from the window
#: midpoint evicted first). Pruning is fail-open: it runs only once viewport
#: geometry has been committed (``_state is not None``) and a non-empty
#: window is computable — pre-fit bulk loads and zero-size widgets keep
#: everything.
_THUMBNAIL_KEEP_MARGIN_BLOCKS = 2
_THUMBNAIL_HARD_CAP = 512


def apply_metric_scale(widget) -> None:
    """Apply the live UI scale to the widget's design-px metrics."""
    for name, base in widget._metric_base.items():
        setattr(widget, name, scaled_px(base))


def install_filter_once(widget, obj) -> None:
    """Install ``widget`` as an event filter on *obj* exactly once."""
    if obj is None:
        return
    if any(known is obj for known in widget._filter_targets):
        return
    try:
        obj.installEventFilter(widget)
    except (RuntimeError, AttributeError):
        return
    widget._filter_targets.append(obj)


def remove_installed_filters(widget) -> None:
    """Remove every event filter installed via :func:`install_filter_once`."""
    targets, widget._filter_targets = list(widget._filter_targets), []
    for obj in targets:
        try:
            obj.removeEventFilter(widget)
        except (RuntimeError, AttributeError):
            pass


def suspend_transient(widget) -> None:
    """Hide-time suspend: stop timers/animation, drop event filters.

    Symmetric to the ``show_event``/``bind_host_scrollbar`` installs.
    Idempotent; safe to call from both hide and close paths.
    """
    try:
        widget._tooltip_timer.stop()
    except (RuntimeError, AttributeError):
        pass
    try:
        widget._playhead_anim.stop()
    except (RuntimeError, AttributeError):
        pass
    remove_installed_filters(widget)


def unbind_host_scrollbar(widget) -> None:
    """Disconnect host scrollbar signals acquired by :func:`bind_host_scrollbar`."""
    scrollbar = widget._host_h_scrollbar
    widget._host_h_scrollbar = None
    if scrollbar is None:
        return
    for signal in (scrollbar.valueChanged, scrollbar.rangeChanged):
        try:
            signal.disconnect(widget._on_host_scroll)
        except (TypeError, RuntimeError):
            pass


def teardown_widget(widget) -> None:
    """Close-time teardown: no singleton may retain the widget after this.

    Disconnects the ``UiScale.scale_changed`` singleton connection and the
    host scrollbar signals, drops the child signal connections whose
    Qt-held callables would otherwise keep the Python wrapper alive
    (tooltip timer, inner scrollbar lambda, playhead animation), suspends
    transient state, cancels the settle gate, and raises the ``_destroyed``
    gate so deferred callbacks never commit or emit afterwards. Idempotent.
    """
    from sli_ui_toolkit.ui.managers.ui_scale import UiScale

    if widget._destroyed:
        return
    widget._destroyed = True
    suspend_transient(widget)
    try:
        UiScale.get_instance().scale_changed.disconnect(widget._on_scale_changed)
    except (TypeError, RuntimeError):
        pass
    unbind_host_scrollbar(widget)
    try:
        widget._layout_settle.cancel()
    except (RuntimeError, AttributeError):
        pass
    for signal, slot in (
        (widget._tooltip_timer.timeout, widget._show_hover_tooltip),
        (widget._playhead_anim.valueChanged, widget._on_playhead_frame),
    ):
        try:
            signal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass
    try:
        # Lambda receiver — disconnect all slots on this one signal.
        widget._v_scrollbar.valueChanged.disconnect()
    except (TypeError, RuntimeError):
        pass


def bind_host_scrollbar(widget) -> None:
    """Bind the host scroll area's scrollbar signals (wiring; owner calls)."""
    scroll_area = timeline_viewport.get_scroll_area(widget)
    if scroll_area is None:
        return
    scrollbar = scroll_area.horizontalScrollBar()
    if scrollbar is not None and scrollbar is not widget._host_h_scrollbar:
        unbind_host_scrollbar(widget)
        widget._host_h_scrollbar = scrollbar
        widget._host_h_scrollbar.valueChanged.connect(widget._on_host_scroll)
        widget._host_h_scrollbar.rangeChanged.connect(widget._on_host_scroll)
    try:
        install_filter_once(widget, scroll_area.viewport())
    except Exception:
        pass


def show_event(widget) -> None:
    """Show-time wiring: host scrollbar + window/viewport filters + settle ping."""
    bind_host_scrollbar(widget)
    # Watch viewport and window for fullscreen resize where widget width stays fixed
    try:
        install_filter_once(widget, widget.window())
        sa = timeline_viewport.get_scroll_area(widget)
        if sa is not None:
            install_filter_once(widget, sa.viewport())
    except Exception:
        pass
    widget._needs_fit_view = True
    widget._layout_settle.ping()


def viewport_geometry_changed(widget, source: str = "") -> None:
    """Recompute fitted state, commit, and refresh fixed width (no emits here)."""
    if not widget.has_snapshots():
        return
    if widget._suppress_resize_recalc:
        return
    _timeline_debug("_onViewportGeometryChanged source=%s width=%s zoom=%s last_min=%s", source, widget.width(), widget._zoom_level, widget._last_min_zoom)
    timeline_viewport.update_vertical_scrollbar(widget)
    nxt = widget._recomputeFittedState()
    widget._commitState(nxt, source=source)
    try:
        timeline_viewport.update_fixed_width(widget)
    except Exception:
        pass
    _timeline_debug("_onViewportGeometryChanged done source=%s width=%s zoom=%s last_min=%s", source, widget.width(), widget._zoom_level, widget._last_min_zoom)


def resize_event(widget, event) -> None:
    """Resize body (the widget method owns the ``super()`` call)."""
    timeline_viewport.update_vertical_scrollbar(widget)
    _timeline_debug("resizeEvent old=%sx%s new=%sx%s suppress=%s has_snap=%s width=%s zoom=%s last_min=%s", event.oldSize().width(), event.oldSize().height(), event.size().width(), event.size().height(), widget._suppress_resize_recalc, widget.has_snapshots(), widget.width(), widget._zoom_level, widget._last_min_zoom)

    if not widget.has_snapshots():
        _timeline_debug("resizeEvent SKIP no snapshots")
        return

    if widget._suppress_resize_recalc:
        _timeline_debug("resizeEvent suppress SKIP")
        return

    old_size = event.oldSize()
    if old_size.isValid() and old_size.width() == event.size().width():
        _timeline_debug("resizeEvent width unchanged -> geometry check")
        viewport_geometry_changed(widget, "resizeEvent:widthUnchanged")
        return

    viewport_geometry_changed(widget, "resizeEvent")


def event_filter(widget, obj, event) -> bool:
    """Event-filter body; True when the geometry change was handled."""
    t = event.type()
    if t in (QEvent.Type.Resize, QEvent.Type.WindowStateChange):
        try:
            sa = timeline_viewport.get_scroll_area(widget)
            is_viewport = sa is not None and sa.viewport() is not None and obj is sa.viewport()
            is_window = obj is widget.window()
            if is_viewport or is_window:
                viewport_geometry_changed(widget, "eventFilter")
                return True
        except Exception:
            pass
    return False


def layout_settle(widget) -> None:
    """Settle-gate flush: deferred fit/commit; never runs on a closed widget."""
    # PySide6-stubs lags shiboken6.isValid — narrow ignore per AGENTS.md.
    if getattr(widget, "_destroyed", False) or not sip.isValid(widget):  # type: ignore[attr-defined]
        return
    _timeline_debug("_on_layout_settle needs_fit=%s width=%s zoom=%s last_min=%s", getattr(widget, "_needs_fit_view", False), widget.width(), widget._zoom_level, widget._last_min_zoom)
    if getattr(widget, "_needs_fit_view", False):
        widget._needs_fit_view = False
        widget.fit_view()
        _timeline_debug("_on_layout_settle after fit_view width=%s zoom=%s", widget.width(), widget._zoom_level)
        try:
            nxt = widget._recomputeFittedState()
            widget._commitState(nxt, source="settleFit")
            timeline_viewport.update_fixed_width(widget)
        except Exception:
            pass
        return
    viewport_geometry_changed(widget, "settle")
    _timeline_debug("_on_layout_settle after _onViewportGeometryChanged width=%s zoom=%s", widget.width(), widget._zoom_level)


def host_scroll(widget, *args) -> None:
    """Host-scrollbar step: sync the gutter band, then recompute geometry."""
    try:
        sa = timeline_viewport.get_scroll_area(widget)
        cur_x = int(sa.horizontalScrollBar().value()) if sa is not None and sa.horizontalScrollBar() is not None else 0
    except Exception:
        cur_x = 0
    _state = getattr(widget, "_state", None)
    prev_x = _state.scroll_x if _state is not None else None
    is_range = len(args) == 2
    if not is_range and prev_x is not None and cur_x == prev_x:
        timeline_viewport.update_vertical_scrollbar(widget)
        widget.update()
        return
    # Signals-live scroll step: the content widget window already moved
    # synchronously while the geometry-changed cycle below only posts async
    # paints. Union the gutter band into the damage synchronously so the
    # next paint pass already covers the sticky gutter at the new offset.
    if _timeline_debug_enabled():
        try:
            _band = timeline_viewport.gutter_band_rect(widget, cur_x)
        except Exception:
            _band = None
        gutter_debug(
            "tick=%s host-scroll cur=%s prev=%s band=%s",
            _next_tick(), cur_x, prev_x, _band,
        )
    try:
        widget.update(timeline_viewport.gutter_band_rect(widget, cur_x))
    except Exception:
        pass
    viewport_geometry_changed(widget, "hostScroll")


def flush_wheel_zoom(widget) -> None:
    """Apply accumulated Ctrl+wheel ticks as one cursor-anchored step.

    Exactly one commit per frame window through ``viewport.commit_zoom``
    with the event position as ``cursor_x``. No-change windows stay silent;
    never commits or emits after close.
    """
    # PySide6-stubs lags shiboken6.isValid — narrow ignore per AGENTS.md.
    if getattr(widget, "_destroyed", False) or not sip.isValid(widget):  # type: ignore[attr-defined]
        widget._wheel_flush_scheduled = False
        widget._wheel_pending_y = 0.0
        widget._wheel_pending_x = None
        widget._wheel_pending_ticks = 0
        return
    widget._wheel_flush_scheduled = False
    pending_y = float(widget._wheel_pending_y)
    cursor_x = widget._wheel_pending_x
    ticks = int(widget._wheel_pending_ticks)
    widget._wheel_pending_y = 0.0
    widget._wheel_pending_x = None
    widget._wheel_pending_ticks = 0
    if pending_y == 0.0 or cursor_x is None:
        return
    old_zoom = float(widget._zoom_level)
    steps = pending_y / 120.0
    new_zoom = timeline_viewport.clamp_zoom(
        widget, old_zoom * (timeline_viewport.WHEEL_ZOOM_FACTOR**steps)
    )
    if abs(new_zoom - old_zoom) <= 1e-4:
        return
    source = "wheelZoomCoalesced" if ticks > 1 else "wheelZoom"
    timeline_viewport.commit_zoom(
        widget, float(new_zoom), cursor_x=float(cursor_x), source=source
    )


def ingest_data(
    widget,
    snapshots=None,
    fps=None,
    timeline_model=None,
    duration=None,
    *,
    source=None,
) -> None:
    """Data-ingest orchestration for ``set_data`` (widget keeps wiring).

    Legacy positional inputs unchanged. ``source`` (a
    ``TimelineDataSource``) is the typed alternative: each ``None``/missing
    member falls back to the explicit argument, then to the legacy default.
    Explicit non-``None`` arguments win over ``source``. Non-matching
    ``source`` objects are ignored (fail-open: legacy path).
    """
    from .models import TimelineDataSource

    try:
        is_source = isinstance(source, TimelineDataSource)
    except TypeError:
        is_source = False
    if source is not None and is_source:
        if snapshots is None:
            snapshots = getattr(source, "snapshots", None)
        if fps is None:
            fps = getattr(source, "fps", None)
        if timeline_model is None:
            timeline_model = getattr(source, "timeline_model", None)
        if duration is None:
            duration = getattr(source, "duration", None)
    bind_host_scrollbar(widget)
    widget._snapshots = list(snapshots or [])
    widget._duration = (
        float(duration)
        if duration is not None
        else (float(widget._snapshots[-1].timestamp) if widget._snapshots else 0.0)
    )
    widget._timeline_model = timeline_model
    if fps is not None:
        widget._fps = max(1, int(fps))
    widget._total_frames = timeline_viewport.compute_total_frames(widget)
    widget._rebuild_row_layout()
    timeline_layout.ensure_preferred_height(widget)

    widget._anchor_index = 0
    widget._drag_index = 0
    widget._has_selection = False
    widget._is_selecting = False
    widget._selection_edit_mode = None
    widget._mouse_down = False
    widget._press_pos = None
    widget._press_frame = 0
    widget._visual_index = 0.0
    widget._playhead_anim.stop()
    widget._current_index = 0

    # Coalesced through the settle gate (same as __init__/showEvent).
    widget._needs_fit_view = True
    widget._layout_settle.ping()


def prune_thumbnails(widget) -> None:
    """Enforce the thumbnail store bound (fail-open; keeps pre-fit loads).

    Keeps entries whose index falls inside the visible strip window plus
    margin, evicts the rest, then applies the hard-cap backstop (farthest
    from the window midpoint first). Index-addressed shape
    (``_thumbnails`` + sorted ``_thumb_indices``) is preserved.
    """
    if not widget._thumbnails:
        return
    if getattr(widget, "_state", None) is None or widget._total_frames <= 0:
        return
    try:
        # Keep-window matches the coordinator fetch window
        # (presenter_parts/thumbnails get_visible_frame_indices margin=2):
        # pruning narrower than the fetch set caused perpetual
        # edge-block refetch. The frame margin below stays as backstop.
        visible = widget.get_visible_thumbnail_frame_indices(overscan_blocks=2)
    except Exception:
        return
    if not visible:
        return
    try:
        slot = timeline_viewport.get_slot_width(widget)
        base = timeline_viewport.get_base_tile_width(widget)
    except Exception:
        return
    if slot <= 0 or base <= 0:
        return
    draw_w = base if slot < base else slot
    frames_per_block = max(1.0, draw_w / slot)
    margin = int(math.ceil(frames_per_block * _THUMBNAIL_KEEP_MARGIN_BLOCKS))
    last = max(0, widget._total_frames - 1)
    lo = max(0, min(visible) - margin)
    hi = min(last, max(visible) + margin)
    for idx in [i for i in widget._thumbnails if i < lo or i > hi]:
        del widget._thumbnails[idx]
    if len(widget._thumbnails) > _THUMBNAIL_HARD_CAP:
        mid = (lo + hi) / 2.0
        ordered = sorted(widget._thumbnails, key=lambda i: (abs(i - mid), i))
        for idx in ordered[_THUMBNAIL_HARD_CAP:]:
            del widget._thumbnails[idx]
    widget._thumb_indices = sorted(widget._thumbnails.keys())


def set_current_frame(widget, index) -> None:
    """Move the playhead: snap on large jumps, ease on steps (150 ms OutCubic)."""
    widget._current_index = max(0, min(index, widget._total_frames - 1))
    target = float(widget._current_index)
    start = float(widget._visual_index)
    if abs(widget._current_index - start) > 2.0 or math.isclose(
        start, target, abs_tol=1e-9
    ):
        # Large jump: snap like the old lerp did; settled: nothing to do.
        widget._playhead_anim.stop()
        widget._visual_index = target
        widget.update()
        return
    widget._playhead_anim.stop()
    widget._playhead_anim.setStartValue(start)
    widget._playhead_anim.setEndValue(target)
    widget._playhead_anim.start()


def playhead_frame(widget, value) -> None:
    """Animation tick: advance the eased on-screen position and repaint."""
    try:
        widget._visual_index = float(value)
    except (TypeError, ValueError):
        return
    widget.update()
