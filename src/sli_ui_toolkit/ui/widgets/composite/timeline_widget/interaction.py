from __future__ import annotations

import math

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt

import shiboken6 as sip

from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from . import layout as timeline_layout
from . import viewport as timeline_viewport
from .debug import _timeline_debug

# --- named interaction tuning (Phase 2 T-life) --------------------------------
# Former hardcodes, one definition site each (i18n/timings/sizes/slop live
# here; wheel factor stays canonical in ``viewport.WHEEL_ZOOM_FACTOR`` and
# keyboard steps mirror it through the same import).

#: Hover tooltip delay (ms): cursor must rest on a keyframe this long.
TOOLTIP_DELAY_MS = 350

#: Playhead ease duration (ms): matches the OutCubic ``QVariantAnimation``
#: constructed in ``widget.__init__``.
PLAYHEAD_ANIM_MS = 150

#: Keyboard frame steps: plain arrows / PageUp-PageDown / Shift+arrows.
KEY_STEP_FRAMES = 1
KEY_PAGE_STEP_FRAMES = 10
KEY_SHIFT_STEP_FRAMES = 10

#: Inner footer-scrollbar track padding / minimum handle width (px).
INNER_SB_TRACK_PADDING_PX = 8.0
INNER_SB_HANDLE_MIN_W_PX = 20.0

#: Prune keep-window: fetch-equivalent base overscan plus the margin, both
#: in BLOCKS (frame margins are forbidden — I3). The total overscan below
#: reproduces the pre-block keep set exactly at 1:1 zoom.
_PRUNE_FETCH_OVERSCAN_BLOCKS = 2


def is_alive(widget) -> bool:
    """Teardown gate: ``False`` once closed or C++-deleted.

    Every commit/emit/update/animation entry funnels through this —
    ``commit_state`` (via ``widget._commitState``), ``set_current_frame``,
    ``playhead_frame``, ``ingest_data`` — exactly like ``layout_settle``
    and ``flush_wheel_zoom`` already do. No emits, no ``update()``, no
    animation start after teardown.
    """
    if getattr(widget, "_destroyed", False):
        return False
    try:
        # PySide6-stubs lags shiboken6.isValid — narrow ignore per AGENTS.md.
        return bool(sip.isValid(widget))  # type: ignore[attr-defined]
    except Exception:
        return False


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
            padding = INNER_SB_TRACK_PADDING_PX
            track_w = sb_rect.width() - padding * 2
            total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
            handle_w = max(INNER_SB_HANDLE_MIN_W_PX, (h_bar.pageStep() / total) * track_w) if total > 0 else INNER_SB_HANDLE_MIN_W_PX
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
    # Documented invariant: a hit zone implies an active selection, so
    # bounds cannot be None here — but the live mouse path fails open to
    # the plain-press path below instead of asserting.
    edit_bounds = _selection_bounds(widget) if edit_zone is not None else None
    if edit_zone is not None and edit_bounds is None:
        edit_zone = None
    if edit_zone is not None:
        lo, hi = edit_bounds
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
            padding = INNER_SB_TRACK_PADDING_PX
            track_w = sb_rect.width() - padding * 2
            total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
            handle_w = max(INNER_SB_HANDLE_MIN_W_PX, (h_bar.pageStep() / total) * track_w) if total > 0 else INNER_SB_HANDLE_MIN_W_PX
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
        # Live drag: direct width write + silent refresh + ONE synchronous
        # band repaint per move segment — no commit and no emit mid-gesture.
        # The single ``_commitState(source="gutterDrag")`` lands on mouse
        # release, so a whole press→release gesture costs exactly one
        # commit (one viewport-family emit, never zoomChanged).
        scroll_area = timeline_viewport.get_scroll_area(widget)
        try:
            scroll_offset = (
                int(scroll_area.horizontalScrollBar().value())
                if scroll_area is not None
                and scroll_area.horizontalScrollBar() is not None
                else 0
            )
        except Exception:
            scroll_offset = 0
        clamped = timeline_viewport.clamp_gutter_width(
            widget, event.pos().x() - scroll_offset
        )
        widget.LEFT_GUTTER = int(clamped)
        widget._last_min_zoom = timeline_viewport.calculate_min_zoom(widget)
        timeline_viewport.update_fixed_width(widget)
        # No commit and no silent refresh mid-gesture: ``_current_state()``
        # is built from the live fields above, while ``_state`` stays at
        # the pre-drag snapshot so the release commit diffs exactly the
        # gesture's geometry delta (one emit, never zero, never N).
        # Band covers chevron + wash/edge gradients + the 1px separator
        # (see viewport.gutter_band_rect); synchronous so the sticky gutter
        # never lags the cursor by a frame. The offset is read AFTER the
        # width sync above (post-commit layout position).
        try:
            area = timeline_viewport.get_scroll_area(widget)
            post_offset = (
                int(area.horizontalScrollBar().value())
                if area is not None and area.horizontalScrollBar() is not None
                else 0
            )
        except Exception:
            post_offset = 0
        try:
            widget.repaint(timeline_viewport.gutter_band_rect(widget, post_offset))
        except Exception:
            pass
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
            # Gesture-final commit: pure geometry (viewport family emits,
            # never zoomChanged); a silent no-op when press→release never
            # moved. ``widget._commitState`` itself gates teardown.
            widget._commitState(widget._current_state(), source="gutterDrag")
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


def _forget_filter_target(widget, obj) -> None:
    """Drop one ``install_filter_once`` target (remove + untrack)."""
    if obj is None:
        return
    try:
        widget._filter_targets = [known for known in widget._filter_targets if known is not obj]
    except AttributeError:
        return
    try:
        obj.removeEventFilter(widget)
    except (RuntimeError, AttributeError):
        pass


def suspend_transient(widget) -> None:
    """Hide-time suspend: stop timers/animation, drop event filters.

    Symmetric to the ``show_event``/``bind_host_scrollbar`` installs.
    Signal connections are KEPT (hide is not teardown) so reshow needs no
    rebind; idempotent; safe to call from both hide and close paths.
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
    widget._host_viewport = None
    widget._filter_window = None


def unbind_host_scrollbar(widget) -> None:
    """Disconnect host scrollbar signals acquired by :func:`bind_host_scrollbar`.

    Also drops the stale host-viewport filter (a host change must not
    accumulate dead viewports) and clears the tracked pair.
    """
    scrollbar = widget._host_h_scrollbar
    widget._host_h_scrollbar = None
    if scrollbar is not None:
        for signal in (scrollbar.valueChanged, scrollbar.rangeChanged):
            try:
                signal.disconnect(widget._on_host_scroll)
            except (TypeError, RuntimeError):
                pass
    _forget_filter_target(widget, getattr(widget, "_host_viewport", None))
    widget._host_viewport = None


def _disconnect_transient_signals(widget) -> None:
    """Drop the four ``__init__`` signal connections (teardown half)."""
    from sli_ui_toolkit.ui.managers.ui_scale import UiScale

    try:
        UiScale.get_instance().scale_changed.disconnect(widget._on_scale_changed)
    except (TypeError, RuntimeError):
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
    widget._transient_bound = False


def ensure_transient_signals(widget) -> None:
    """Restore the four ``__init__`` signal connections (show half).

    No-op unless a teardown dropped them (``_transient_bound`` flag), so
    hide/show cycles never double-connect while close→reshow recovers
    tooltips, easing, inner-scrollbar paints, and scale response.
    """
    if getattr(widget, "_transient_bound", True):
        return
    from sli_ui_toolkit.ui.managers.ui_scale import UiScale

    try:
        UiScale.get_instance().scale_changed.connect(widget._on_scale_changed)
    except (TypeError, RuntimeError):
        pass
    try:
        widget._tooltip_timer.timeout.connect(widget._show_hover_tooltip)
    except (TypeError, RuntimeError):
        pass
    try:
        widget._playhead_anim.valueChanged.connect(widget._on_playhead_frame)
    except (TypeError, RuntimeError):
        pass
    try:
        widget._v_scrollbar.valueChanged.connect(lambda _value: widget.update())
    except (TypeError, RuntimeError):
        pass
    widget._transient_bound = True


def teardown_widget(widget) -> None:
    """Close-time teardown: no singleton may retain the widget after this.

    Disconnects the ``UiScale.scale_changed`` singleton connection and the
    host scrollbar signals, drops the     child signal connections whose
    Qt-held callables would otherwise keep the Python wrapper alive
    (tooltip timer, inner scrollbar lambda, playhead animation), suspends
    transient state, cancels the settle gate, and raises the ``_destroyed``
    gate so deferred callbacks never commit or emit afterwards. Idempotent.
    Reopening rebinds through ``show_event`` → ``ensure_transient_signals``.
    """
    if widget._destroyed:
        return
    widget._destroyed = True
    suspend_transient(widget)
    _disconnect_transient_signals(widget)
    unbind_host_scrollbar(widget)
    try:
        widget._layout_settle.cancel()
    except (RuntimeError, AttributeError):
        pass


def bind_host_scrollbar(widget) -> None:
    """Bind the host scroll area's scrollbar signals (wiring; owner calls).

    Reparent-safe: when the host scroll area changed, the old scrollbar
    signals disconnect AND the old viewport filter is forgotten before the
    new pair installs — dead viewports never accumulate in
    ``_filter_targets``.
    """
    scroll_area = timeline_viewport.get_scroll_area(widget)
    if scroll_area is None:
        unbind_host_scrollbar(widget)
        return
    scrollbar = scroll_area.horizontalScrollBar()
    if scrollbar is not None and scrollbar is not widget._host_h_scrollbar:
        unbind_host_scrollbar(widget)
        widget._host_h_scrollbar = scrollbar
        widget._host_h_scrollbar.valueChanged.connect(widget._on_host_scroll)
        widget._host_h_scrollbar.rangeChanged.connect(widget._on_host_scroll)
    viewport_obj = None
    try:
        viewport_obj = scroll_area.viewport()
    except (RuntimeError, AttributeError):
        viewport_obj = None
    if viewport_obj is not getattr(widget, "_host_viewport", None):
        _forget_filter_target(widget, getattr(widget, "_host_viewport", None))
        widget._host_viewport = viewport_obj
    try:
        install_filter_once(widget, viewport_obj)
    except Exception:
        pass


def show_event(widget) -> None:
    """Show-time wiring: host scrollbar + window/viewport filters + settle ping.

    Restores every teardown-dropped signal connection first (tooltips,
    easing, inner scrollbar, scale response) so a reopened widget behaves
    like a fresh one; filter installs stay exactly-once; stale window
    filters from a previous host are forgotten.

    Reopen revives the ``_destroyed`` gate (a reshown widget is alive
    again — deferred callbacks may commit); the next ``closeEvent``/
    ``teardown_widget`` re-arms it.
    """
    widget._destroyed = False
    ensure_transient_signals(widget)
    bind_host_scrollbar(widget)
    # Watch viewport and window for fullscreen resize where widget width stays fixed
    try:
        window = widget.window()
        if window is not getattr(widget, "_filter_window", None):
            _forget_filter_target(widget, getattr(widget, "_filter_window", None))
            widget._filter_window = window
        install_filter_once(widget, window)
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
    """Event-filter body; True when the geometry change was handled.

    Never commits synchronously: a resize observed inside someone else's
    event dispatch only pings the settle gate (the ``"settle"`` flush
    recomputes + commits later), so no re-entrant commit cascade can run
    through ``viewport_geometry_changed`` from inside the filter. The
    widget's ``eventFilter`` must return this verdict verbatim (True stops
    fall-through reprocessing).
    """
    if getattr(widget, "_destroyed", False):
        return False
    t = event.type()
    if t in (QEvent.Type.Resize, QEvent.Type.WindowStateChange):
        try:
            sa = timeline_viewport.get_scroll_area(widget)
            is_viewport = sa is not None and sa.viewport() is not None and obj is sa.viewport()
            is_window = obj is widget.window()
            if is_viewport or is_window:
                try:
                    widget._layout_settle.ping()
                except (RuntimeError, AttributeError):
                    pass
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


def freeze_thumb_aspect(widget) -> float:
    """Explicit ingest freeze for the tile aspect (HANDOFF-1, I1 anchor).

    Probes snapshot metadata ONCE per ingest and writes the frozen
    ``(key, aspect)`` tuple ``viewport.frozen_thumb_aspect`` reads — so a
    same-length in-place snapshot swap (identical freeze key, new content)
    still re-freezes instead of inheriting the stale best-effort cache.
    Snapshot-free ingests freeze the ``16/9`` fallback. The lazy
    first-computed-wins path in ``viewport`` only fills a MISSING entry;
    it never overrides an explicit freeze.
    """
    try:
        key = timeline_viewport._frozen_aspect_key(widget)
    except Exception:
        return timeline_viewport.THUMB_ASPECT_FALLBACK
    try:
        aspect = timeline_viewport._snapshot_thumb_aspect(widget)
    except Exception:
        aspect = timeline_viewport.THUMB_ASPECT_FALLBACK
    try:
        widget._frozen_thumb_aspect = (key, aspect)
    except Exception:
        pass
    return aspect


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

    No-op on a torn-down widget (same ``_destroyed``/``isValid`` gate as
    ``layout_settle``/``flush_wheel_zoom``): post-close data must never
    rebind, refit, or restart the playhead animation.
    """
    if not is_alive(widget):
        return
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
    # Explicit freeze (HANDOFF-1): aspect is fixed HERE, from ingest inputs
    # only — never from thumbnail arrivals. Also resets the prune keep-cache
    # (block layout moved with the new geometry).
    freeze_thumb_aspect(widget)
    widget._prune_keep_cache = None
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


def _prune_keep_interval(widget) -> tuple[int, int] | None:
    """Contiguous frame keep-interval from the block-unit window (I3).

    ``visible_strip_block_range`` with the fetch-equivalent base overscan
    PLUS the margin (both in blocks) selects the kept blocks; the interval
    spans the kept blocks' rep frames. Exact-match lookup makes eviction
    safe (a missing rep shows the theme placeholder, never a neighbor).
    ``None`` when the window is degenerate (fail-open: keep everything).
    """
    try:
        overscan = _PRUNE_FETCH_OVERSCAN_BLOCKS + _THUMBNAIL_KEEP_MARGIN_BLOCKS
        first_blk, last_excl = timeline_viewport.visible_strip_block_range(
            widget, overscan_blocks=overscan
        )
    except Exception:
        return None
    if last_excl <= first_blk:
        return None
    try:
        reps = widget.get_visible_thumbnail_frame_indices(overscan_blocks=overscan)
    except Exception:
        return None
    if not reps:
        return None
    return (min(reps), max(reps))


def _prune_window_token(widget):
    """O(1) identity for the keep-window inputs (value-based, not id-based).

    ``refresh_viewport_state`` assigns a FRESH state object per thumbnail
    insert, so ``id(_state)`` can never hit twice in a streaming loop — the
    token instead hashes the values the block window derives from (committed
    geometry + frame count + tile metrics). Any real geometry change
    (scroll, zoom, gutter, scale, refreeze) retires the cache; a pure
    insert stream keeps it. ``None`` when unreadable (fail-open: full pass).
    """
    try:
        st = widget._state
        return (
            float(st.zoom),
            float(st.min_zoom),
            int(st.left_gutter),
            int(st.content_width),
            int(st.viewport_width),
            int(st.scroll_x),
            int(widget._total_frames),
            float(widget.STRIP_HEIGHT),
            float(timeline_viewport.frozen_thumb_aspect(widget)),
        )
    except Exception:
        return None


def _prune_enforce_hard_cap(widget, lo: int, hi: int) -> None:
    """Fail-stop backstop: keep at most ``_THUMBNAIL_HARD_CAP`` entries."""
    if len(widget._thumbnails) <= _THUMBNAIL_HARD_CAP:
        return
    mid = (lo + hi) / 2.0
    ordered = sorted(widget._thumbnails, key=lambda i: (abs(i - mid), i))
    for idx in ordered[_THUMBNAIL_HARD_CAP:]:
        del widget._thumbnails[idx]


def prune_thumbnails(widget, *, _hint_index: int | None = None) -> None:
    """Enforce the thumbnail store bound (fail-open; keeps pre-fit loads).

    Full pass: evict every entry outside the block-derived keep-interval,
    then apply the hard-cap backstop. Index-addressed shape
    (``_thumbnails`` + sorted ``_thumb_indices``) is preserved.

    Batched inserts stay linear: ``add_thumbnail`` passes its index as
    ``_hint_index``; when the cached keep-interval is still valid (same
    committed state + frame count — the common streaming case) the insert
    is kept-or-dropped in O(1) with no store scan. Any geometry change
    invalidates the cache and the next insert takes one full pass.
    Bulk ``set_thumbnails`` replaces the store and prunes exactly once.
    """
    if not widget._thumbnails:
        return
    if getattr(widget, "_state", None) is None or widget._total_frames <= 0:
        return
    cache = getattr(widget, "_prune_keep_cache", None)
    token = _prune_window_token(widget)
    if (
        _hint_index is not None
        and token is not None
        and isinstance(cache, tuple)
        and len(cache) == 3
        and cache[0] == token
    ):
        _token, lo, hi = cache
        idx = int(_hint_index)
        if lo <= idx <= hi:
            _prune_enforce_hard_cap(widget, lo, hi)
            widget._thumb_indices = sorted(widget._thumbnails.keys())
        else:
            widget._thumbnails.pop(idx, None)
            try:
                widget._thumb_indices.remove(idx)
            except ValueError:
                pass
        return
    interval = _prune_keep_interval(widget)
    if interval is None:
        return
    lo, hi = interval
    for idx in [i for i in widget._thumbnails if i < lo or i > hi]:
        del widget._thumbnails[idx]
    _prune_enforce_hard_cap(widget, lo, hi)
    widget._thumb_indices = sorted(widget._thumbnails.keys())
    if token is None:
        token = _prune_window_token(widget)
    try:
        widget._prune_keep_cache = (token, lo, hi)
    except Exception:
        pass


def set_current_frame(widget, index) -> None:
    """Move the playhead: snap on large jumps, ease on steps (150 ms OutCubic).

    No-op on a torn-down widget: never moves state, never starts the
    animation, never repaints after close.
    """
    if not is_alive(widget):
        return
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


def rebuild_hover_points(widget) -> None:
    """Damage-independent hover rebuild (post-paint pass).

    ``render.paint_timeline`` resets ``_hover_points`` per paint and the
    scalar segment pass appends only damage-visible dots, so a narrow
    repaint starves tooltips while a full repaint populates them. The
    widget calls this at the end of ``paintEvent`` (after paint returns):
    the SAME points are rebuilt over the full visible row window, so full
    and partial repaints leave identical hit-sets and color/enum/scalar
    paths stay consistent (one builder, same 12 px shapes, same
    ``tooltip_for_keyframe`` texts the paint passes use).
    """
    from . import segments as timeline_segments  # read-only: span builders only

    points: list[tuple[QRectF, str]] = []
    try:
        if widget._total_frames <= 0:
            widget._hover_points = points
            return
        duration = timeline_layout.content_duration(widget)
        logical_width = timeline_viewport.get_logical_width(widget)
        if duration <= 0 or logical_width <= 0:
            widget._hover_points = points
            return
        _content_top, rows_bottom = timeline_viewport.content_viewport_bounds(widget)
        rows_top = widget.STRIP_HEIGHT - timeline_viewport.vertical_scroll_value(widget)
        row_items = list(timeline_layout.iter_row_rects(widget, rows_top, rows_bottom))
    except Exception:
        widget._hover_points = points
        return
    for kind, key, rect in row_items:
        try:
            if kind == "group":
                continue
            if kind == "track_single":
                _kind, group, track, channel = key
            else:
                _kind, group, track, channel, _is_first = key
            row_center_y = timeline_layout.row_center_y(rect.top(), rect.height())
            if track.kind == "color":
                try:
                    first_channel = next(iter(track.channels.values()))
                except StopIteration:
                    continue
                spans = timeline_segments._color_state_spans(
                    widget, track, duration, logical_width
                )
                for index, (timestamp, end_timestamp, x1, x2, color) in enumerate(spans):
                    direction = -1.0 if index % 2 == 0 else 1.0
                    y = row_center_y + direction * 7.0
                    start_ref = SimpleNamespace(timestamp=timestamp, value=color)
                    end_ref = SimpleNamespace(timestamp=end_timestamp, value=color)
                    points.extend(
                        timeline_viewport.hover_points_for_rows(
                            widget,
                            group,
                            track,
                            first_channel,
                            [(x1, y, start_ref), (x2, y, end_ref)],
                        )
                    )
            elif track.kind == "enum":
                spans = timeline_segments._enum_state_spans(
                    widget, track, channel, duration, logical_width
                )
                for active_index, (timestamp, end_timestamp, x1, x2, value) in enumerate(
                    spans
                ):
                    direction = -1.0 if active_index % 2 == 0 else 1.0
                    y = row_center_y + direction * 7.0
                    hover_pts = [(x1, y, SimpleNamespace(timestamp=timestamp, value=value))]
                    if not math.isclose(
                        float(end_timestamp), float(duration), abs_tol=1e-9
                    ):
                        hover_pts.append(
                            (x2, y, SimpleNamespace(timestamp=end_timestamp, value=value))
                        )
                    points.extend(
                        timeline_viewport.hover_points_for_rows(
                            widget, group, track, channel, hover_pts
                        )
                    )
            else:
                # Unbounded window: ``visible_keyframe_segments`` only culls
                # by bounds, so ``(-inf, +inf)`` yields every segment with
                # the exact curve endpoints the bounded paint draws.
                segments = timeline_layout.visible_keyframe_segments(
                    widget,
                    track,
                    channel,
                    duration,
                    logical_width,
                    row_center_y,
                    float("-inf"),
                    float("inf"),
                )
                seen: set[tuple[float, float]] = set()
                for segment in segments:
                    curve_points = segment.get("curve_points") or [
                        (segment["x1"], segment["y"]),
                        (segment["x2"], segment["y"]),
                    ]
                    x1, y1 = curve_points[0]
                    x2, y2 = curve_points[-1]
                    for x, y, keyframe in (
                        (x1, y1, segment["start_kf"]),
                        (x2, y2, segment["end_kf"]),
                    ):
                        dedup = (round(float(x), 2), round(float(y), 2))
                        if dedup in seen:
                            continue
                        seen.add(dedup)
                        points.append(
                            (
                                QRectF(float(x) - 6.0, float(y) - 6.0, 12.0, 12.0),
                                timeline_viewport.tooltip_for_keyframe(
                                    widget, group, track, channel, keyframe
                                ),
                            )
                        )
        except Exception:
            continue
    widget._hover_points = points


def playhead_frame(widget, value) -> None:
    """Animation tick: advance the eased on-screen position and repaint.

    No-op on a torn-down widget: a stray tick after close neither moves
    state nor repaints.
    """
    if not is_alive(widget):
        return
    try:
        widget._visual_index = float(value)
    except (TypeError, ValueError):
        return
    widget.update()
