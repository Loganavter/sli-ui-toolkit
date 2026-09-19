from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QScrollArea, QWidget

from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
    MINIMAL_SCROLLBAR_WIDTH,
    overlay_scrollbar_max_inset,
)
from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from .debug import _timeline_debug, _timeline_debug_enabled, _next_tick, gutter_debug
from . import theme as timeline_theme
from .i18n import localize_token_for, localize_value_for
from .state import TimelineViewportState
from .theme import resolve_accent_color

def footer_height(widget) -> int:
    return scaled_px(42) + widget.SCROLLBAR_STRIP_HEIGHT

def vertical_scrollbar_width(widget) -> int:
    return MINIMAL_SCROLLBAR_WIDTH

def vertical_scrollbar_gutter_width(widget) -> int:
    # Same "max bar width + margin" footprint the rest of the toolkit uses —
    # the bar is centered inside this lane, content leaves it clear.
    return overlay_scrollbar_max_inset()

# Zoom model (Z1): ``widget._zoom_level`` is the single zoom scalar and
# pixels-per-second (pps) derives from it as ``pps = zoom * base_pps``
# where ``base_pps = frame_span * base_tile_width / duration`` (the pps at
# zoom 1.0). Every zoom path must go through ``_commitState``; the wheel
# path commits coalesced steps (see ``TimelineWidget._flush_wheel_zoom``)
# with a cursor anchor so the time under the cursor stays fixed:
# ``scroll = cursor_time * new_pps + LEFT_GUTTER - cursor_viewport_x``.
WHEEL_ZOOM_FACTOR = 1.25
"""Per-tick Ctrl+wheel zoom multiplier (single site; pinned by test)."""

# Metrics for the timeline's own drawn footer scrollbar. The values mirror
# the MinimalistScrollBar's visual language (track padding / hover thumb
# thickness) but are this widget's own, so they stay local.
_INNER_SB_TRACK_PADDING = 8.0
_INNER_SB_THICKNESS = 6.0

def right_inset(widget) -> int:
    return vertical_scrollbar_gutter_width(widget) if widget._v_scrollbar.isVisible() else 0

def content_viewport_bounds(widget) -> tuple[int, int]:
    content_top = 0
    content_bottom = widget.height() - footer_height(widget) - 2
    return content_top, content_bottom

def vertical_scroll_value(widget) -> int:
    return widget._v_scrollbar.value() if widget._v_scrollbar.isVisible() else 0

def vertical_scrollbar_state(widget) -> tuple[bool, QRect | None, int, int]:
    """Pure scrollbar sync computation — reads widget state, mutates nothing.

    Returns ``(should_be_visible, geometry_or_None, max_scroll, viewport_h)``.
    This is the paint-safe half of :func:`update_vertical_scrollbar`: the
    paint path (``render.paint_timeline``) must never apply scrollbar
    geometry — see the paint contract there — but tests and non-paint
    callers can query the desired state through this function without
    touching ``setVisible``/``setGeometry``.
    """
    from . import layout as timeline_layout  # function-level: layout owns the top-level edge (I3)

    content_top, content_bottom = content_viewport_bounds(widget)
    viewport_h = max(0, content_bottom - content_top)
    content_h = max(0, widget.STRIP_HEIGHT + timeline_layout.rows_height(widget))
    max_scroll = max(0, content_h - viewport_h)
    if max_scroll <= 0:
        return False, None, max_scroll, viewport_h
    width = vertical_scrollbar_width(widget)
    gutter_width = vertical_scrollbar_gutter_width(widget)
    scroll_area = get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    viewport_width = get_viewport_width(widget)
    geometry = QRect(
        max(0, scroll_offset + viewport_width - gutter_width + (gutter_width - width) // 2),
        content_top,
        width,
        viewport_h,
    )
    return True, geometry, max_scroll, viewport_h


def update_vertical_scrollbar(widget) -> None:
    """Sync the vertical scrollbar to content height (non-paint paths only).

    Applies :func:`vertical_scrollbar_state`: range/steps/value, visibility,
    and geometry. Must never be called from the paint path — scrollbar sync
    lives in ``resizeEvent``/``_onViewportGeometryChanged``/``_on_layout_settle``/
    ``_on_scale_changed``/``_on_host_scroll`` (``widget.py``); the paint
    contract in ``render.paint_timeline`` forbids geometry mutation.
    """
    old_geometry = widget._v_scrollbar.geometry()
    was_visible = widget._v_scrollbar.isVisible()
    should_be_visible, geometry, max_scroll, viewport_h = vertical_scrollbar_state(widget)
    widget._v_scrollbar.blockSignals(True)
    widget._v_scrollbar.setRange(0, max_scroll)
    widget._v_scrollbar.setPageStep(max(1, viewport_h))
    widget._v_scrollbar.setSingleStep(max(scaled_px(12), widget.CHANNEL_ROW_HEIGHT))
    widget._v_scrollbar.setValue(min(widget._v_scrollbar.value(), max_scroll))
    widget._v_scrollbar.blockSignals(False)
    widget._v_scrollbar.setVisible(should_be_visible)
    if should_be_visible and geometry is not None:
        widget._v_scrollbar.setGeometry(geometry)
        widget._v_scrollbar.raise_()
    new_geometry = widget._v_scrollbar.geometry()
    if was_visible or widget._v_scrollbar.isVisible():
        dirty = QRect(old_geometry)
        if not dirty.isNull():
            dirty = dirty.united(new_geometry)
        else:
            dirty = QRect(new_geometry)
        if not dirty.isNull():
            widget.update(dirty.adjusted(-4, -4, 4, 4))

def get_thumb_aspect_ratio(widget) -> float:
    if widget._thumb_indices:
        first = widget._thumb_indices[0]
        pm = widget._thumbnails.get(first)
        if pm and pm.height() > 0:
            return pm.width() / pm.height()
    return 16 / 9

def get_base_tile_width(widget) -> float:
    return max(1.0, widget.STRIP_HEIGHT * get_thumb_aspect_ratio(widget))

def frame_span(widget) -> int:
    return max(1, widget._total_frames - 1)

def get_logical_width(widget) -> float:
    base = get_base_tile_width(widget)
    return max(1.0, frame_span(widget) * base * widget._zoom_level)

def get_slot_width(widget) -> float:
    if widget._total_frames <= 1:
        return 1.0
    return get_logical_width(widget) / frame_span(widget)

def strip_block_layout(
    widget,
    *,
    content_start_x: float,
    start_x: float,
    end_x: float,
    overscan_blocks: int = 0,
) -> list[tuple[float, float, int]]:
    """Fixed-width thumbnail block layout — one source of truth for paint
    (``render.draw_thumbnail_strip``) and generation priority
    (``get_visible_thumbnail_frame_indices``).

    Returns ``[(block_x, draw_w, rep_frame)]`` for blocks intersecting
    ``[start_x, end_x)``. ``draw_w`` is CONSTANT (NLE-style): ``base_tile``
    while collapsed (``slot_width < base_tile``), else ``slot_width``
    (zoomed-in 1:1, one frame per block) — zoom changes frames-per-block,
    never block width. ``rep_frame`` is the block's representative frame
    (floor of its start position), clamped to ``[0, total-1]``; thumbnail
    lookup stays nearest-available via ``bisect`` on the widget side.
    """
    total = widget._total_frames
    if total <= 0:
        return []
    logical_width = get_logical_width(widget)
    slot_width = get_slot_width(widget)
    base_tile = get_base_tile_width(widget)
    if logical_width <= 0 or slot_width <= 0 or base_tile <= 0:
        return []
    draw_w = base_tile if slot_width < base_tile else slot_width
    frames_per_block = draw_w / slot_width  # >= 1 by construction
    overscan_w = max(0, int(overscan_blocks)) * draw_w
    start_x = max(content_start_x, start_x - overscan_w)
    end_x = min(content_start_x + logical_width, end_x + overscan_w)
    if end_x <= start_x:
        return []
    first_block = max(0, int((start_x - content_start_x) / draw_w))
    last_block_excl = int(math.ceil((end_x - content_start_x) / draw_w))
    blocks: list[tuple[float, float, int]] = []
    for i in range(first_block, last_block_excl):
        rep = min(total - 1, int(i * frames_per_block))
        blocks.append((content_start_x + i * draw_w, draw_w, rep))
    return blocks

def get_base_pixels_per_second(widget) -> float:
    """pps at zoom 1.0 — the ``base_pps`` of the ``pps = zoom * base_pps`` invariant."""
    duration = widget.get_total_duration()
    if duration <= 0 or widget._total_frames <= 1:
        return 50.0
    return (float(frame_span(widget)) * get_base_tile_width(widget)) / float(duration)

def pixels_per_second_for_zoom(widget, zoom: float) -> float:
    """pps for an arbitrary zoom without touching widget state."""
    return float(zoom) * get_base_pixels_per_second(widget)

def clamp_zoom(widget, zoom: float) -> float:
    """Clamp *zoom* to ``[min_zoom, 1.0]``, snapping to min within 1%.

    Single clamping site for the wheel path so the range can never drift
    between call sites (mirrors the pre-coalescing wheel clamp).
    """
    min_zoom = calculate_min_zoom(widget)
    clamped = max(min_zoom, min(float(zoom), 1.0))
    if math.isclose(clamped, min_zoom, rel_tol=0.01):
        clamped = min_zoom
    return clamped

def cursor_time_at_x(widget, content_x: float) -> float:
    """Time under a content-x cursor via the ``pos_to_float_index`` mapping.

    *content_x* is in widget (content) coordinates, e.g.
    ``event.position().x()`` of a wheel event delivered to the widget.
    """
    if widget._total_frames <= 0:
        return 0.0
    fps = max(1, int(getattr(widget, "_fps", 60)))
    return float(pos_to_float_index(widget, float(content_x))) / float(fps)

def anchor_scroll_for_zoom(
    widget,
    cursor_viewport_x: float,
    cursor_time: float,
    new_pps: float,
) -> int:
    """Scrollbar value keeping *cursor_time* under the cursor after zoom.

    Anchor math: ``scroll = cursor_time * new_pps + LEFT_GUTTER -
    cursor_viewport_x``. Lower-clamped at 0; the caller clamps the upper
    end to the live scrollbar range.
    """
    target = float(cursor_time) * float(new_pps) + float(widget.LEFT_GUTTER) - float(cursor_viewport_x)
    return max(0, int(round(target)))


def _snapshot_with_zoom(widget, zoom: float) -> TimelineViewportState:
    """Pure viewport snapshot identical to :func:`current_state` but at *zoom*.

    Single construction site for zoomed snapshots: ``current_state``,
    ``recompute_fitted_state`` and ``commit_zoom`` all build through here,
    so the zoomed geometry (``content_width`` at the new zoom) can never
    drift between call sites. Reads the live scrollbar *after* any
    programmatic ``setValue`` so the snapshot carries the post-commit
    scroll position.
    """
    try:
        right = right_inset(widget)
    except Exception:
        right = 0
    if widget._total_frames > 0:
        logical = max(
            1.0,
            float(frame_span(widget)) * float(get_base_tile_width(widget)) * float(zoom),
        )
        content_width = int(
            math.ceil(float(widget.LEFT_GUTTER) + float(logical) + float(right))
        )
    else:
        content_width = 0
    viewport_width = get_viewport_width(widget)
    scroll_area = get_scroll_area(widget)
    try:
        scroll_x = (
            int(scroll_area.horizontalScrollBar().value())
            if scroll_area is not None and scroll_area.horizontalScrollBar() is not None
            else 0
        )
    except Exception:
        scroll_x = 0
    return TimelineViewportState(
        zoom=float(zoom),
        min_zoom=float(calculate_min_zoom(widget)),
        left_gutter=int(widget.LEFT_GUTTER),
        content_width=int(content_width),
        viewport_width=int(viewport_width),
        scroll_x=int(scroll_x),
    )


def current_state(widget) -> TimelineViewportState:
    """Snapshot current viewport state from widget fields and helpers."""
    return _snapshot_with_zoom(widget, float(widget._zoom_level))


def recompute_fitted_state(widget) -> TimelineViewportState:
    """Return current state with zoom clamped to min_zoom if fitted."""
    cur = current_state(widget)
    if cur.is_fitted() and abs(cur.zoom - cur.min_zoom) > 1e-4:
        return _snapshot_with_zoom(widget, cur.min_zoom)
    return cur


def commit_state(widget, nxt: TimelineViewportState, source: str = "") -> bool:
    """Diff ``nxt`` against ``widget._state`` and emit typed signals.

    ``eps 1e-4`` for zoom/min_zoom, ``==`` for px geometry. Calls
    ``updateGeometry`` + ``update`` and emits ``zoomChanged(float)`` only
    when zoom changed, ``viewportChanged`` /
    ``viewportChangedState(object)`` when zoom or geometry changed
    (``"gutterDrag"`` included: a gutter-width change is pure geometry,
    so it emits the viewport family and never ``zoomChanged``).
    Returns ``True`` if any emit happened. This is the only
    ``widget._zoom_level`` write site besides ``__init__``.
    """
    old: TimelineViewportState | None = getattr(widget, "_state", None)
    eps = 1e-4
    has_zoom = nxt.has_zoom_changed(old, eps=eps)
    has_geometry = nxt.has_geometry_changed(old)
    min_zoom_changed = old is not None and abs(nxt.min_zoom - old.min_zoom) > eps
    if min_zoom_changed:
        has_geometry = True
    widget._zoom_level = float(nxt.zoom)
    widget._last_min_zoom = float(nxt.min_zoom)
    if old is not None and not has_zoom and not has_geometry:
        widget._state = nxt
        return False
    if int(widget.LEFT_GUTTER) != int(nxt.left_gutter):
        widget.LEFT_GUTTER = int(nxt.left_gutter)
    widget._state = nxt
    _timeline_debug("_commitState source=%s zoom %s->%s min %s eps %s has_zoom=%s has_geom=%s", source, getattr(old, "zoom", None), nxt.zoom, nxt.min_zoom, eps, has_zoom, has_geometry)
    try:
        widget.updateGeometry()
    except Exception:
        pass
    widget.update()
    emitted = False
    if has_zoom:
        try:
            widget.zoomChanged.emit(float(nxt.zoom))
        except Exception:
            pass
        emitted = True
    if has_zoom or has_geometry:
        try:
            widget.viewportChanged.emit()
        except Exception:
            pass
        try:
            widget.viewportChangedState.emit(nxt)
        except Exception:
            pass
        emitted = True
    return emitted


def refresh_viewport_state(widget) -> None:
    """Silently re-snapshot ``widget._state`` from live fields (no emits).

    Write-through cache for paths that mutate geometry without a
    viewport notification today (gutter drag, thumbnail updates,
    fit_view): keeps ``TimelineViewportState`` authoritative for readers
    like ``_on_host_scroll`` while ``commit_state`` remains the only emit
    path. Deliberately a no-op while ``_state`` is ``None`` so the first
    ``commit_state(old=None)`` still emits.
    """
    if widget._state is None:
        return
    try:
        nxt = current_state(widget)
    except Exception:
        return
    widget._state = nxt
    widget._last_min_zoom = float(nxt.min_zoom)


def commit_zoom(
    widget, new_zoom: float, *, cursor_x: float | None, source: str
) -> None:
    """Single zoom-commit sequence shared by the API and wheel paths.

    ``cursor_x`` selects the cursor policy: a content-coords x (the wheel
    path passes the event position) anchors the time under that x, while
    ``None`` (the event-less API path) anchors the viewport-center time.
    Either way the time under the anchor stays fixed via
    :func:`anchor_scroll_for_zoom`.

    Sequence (the unified E1 body): pps for the new zoom, live scrollbar
    read, cursor-time at the anchor, anchor target, synchronous scrollbar
    ``setValue`` (signals blocked, clamped to the live range), pure
    zoomed snapshot, one :func:`commit_state` (the ``_zoom_level`` write
    plus the only emit), ``update_fixed_width`` at the new zoom, one
    synchronous gutter-band repaint covering the scroll correction.
    Callers own clamping (``clamp_zoom``) and the silent no-change
    early-out (``<=1e-4`` eps); coalescing (tick accumulation, one flush
    per window, ``"wheelZoom"`` vs ``"wheelZoomCoalesced"`` source) stays
    in the wheel path.
    """
    new_zoom = float(new_zoom)
    new_pps = pixels_per_second_for_zoom(widget, new_zoom)
    scroll_area = get_scroll_area(widget)
    scrollbar = None
    scroll_old = 0
    if _timeline_debug_enabled():
        try:
            _old_zoom = float(getattr(widget, "_zoom_level", -1.0))
        except Exception:
            _old_zoom = -1.0
        _ztick = _next_tick()
        gutter_debug(
            "tick=%s zoom-commit source=%s zoom %s->%s cursor_x=%s",
            _ztick, source, _old_zoom, new_zoom, cursor_x,
        )
    if scroll_area is not None:
        scrollbar = scroll_area.horizontalScrollBar()
        try:
            scroll_old = int(scrollbar.value())
        except Exception:
            scroll_old = 0
    if cursor_x is None:
        try:
            viewport_width = int(get_viewport_width(widget))
        except Exception:
            viewport_width = 0
        cursor_viewport_x = float(viewport_width) / 2.0
        cursor_time = cursor_time_at_x(widget, float(scroll_old) + cursor_viewport_x)
    else:
        cursor_time = cursor_time_at_x(widget, float(cursor_x))
        cursor_viewport_x = float(cursor_x) - float(scroll_old)
    target = anchor_scroll_for_zoom(widget, cursor_viewport_x, cursor_time, new_pps)
    if scrollbar is not None:
        try:
            lo = int(scrollbar.minimum())
            hi = int(scrollbar.maximum())
        except Exception:
            lo, hi = 0, int(target)
        target = max(lo, min(int(target), hi))
        scrollbar.blockSignals(True)
        try:
            scrollbar.setValue(int(target))
        finally:
            scrollbar.blockSignals(False)
        try:
            sync_scroll = int(scrollbar.value())
        except Exception:
            sync_scroll = int(target)
        if _timeline_debug_enabled():
            gutter_debug(
                "tick=%s zoom-scroll source=%s scroll_old=%s target=%s clamped=%s",
                _next_tick(), source, scroll_old, target, sync_scroll,
            )
    else:
        sync_scroll = int(target)
    try:
        nxt = _snapshot_with_zoom(widget, new_zoom)
    except Exception:
        return
    # Through the widget's named entry (not commit_state directly): tests
    # and subclasses reach into / override _commitState, and the method
    # stays the single observable commit funnel.
    widget._commitState(nxt, source)
    update_fixed_width(widget)
    # Synchronous correction paint: setValue moved the content widget
    # window synchronously while every correction paint below
    # (_commitState -> update, update_fixed_width -> update) is async,
    # leaving ~1 frame of gutter displaced per step. repaint() paints
    # the gutter band now, in the same call stack. Band-only (not a
    # full repaint) to keep the coalesced budget: one commit + one
    # sync band repaint per window. Correction-only: no state change.
    if _timeline_debug_enabled():
        try:
            _band = gutter_band_rect(widget, sync_scroll)
        except Exception:
            _band = None
        try:
            _live = int(scrollbar.value()) if scrollbar is not None else sync_scroll
        except Exception:
            _live = sync_scroll
        gutter_debug(
            "tick=%s zoom-band source=%s scroll_old=%s target=%s live=%s drift=%s band=%s",
            _next_tick(), source, scroll_old, sync_scroll, _live,
            (_live != sync_scroll), _band,
        )
    try:
        widget.repaint(gutter_band_rect(widget, sync_scroll))
    except Exception:
        pass


def get_visible_thumbnail_frame_indices(
    widget,
    *,
    overscan_blocks: int = 1,
) -> list[int]:
    if widget._total_frames <= 0:
        return []

    logical_width = get_logical_width(widget)
    slot_width = get_slot_width(widget)
    base_tile = get_base_tile_width(widget)
    if logical_width <= 0 or slot_width <= 0 or base_tile <= 0:
        return []

    content_start_x = float(widget.LEFT_GUTTER)
    scroll_area = get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    viewport_width = get_viewport_width(widget)
    visible_right = scroll_offset + viewport_width
    content_right = visible_right - right_inset(widget)
    start_x = max(content_start_x, float(scroll_offset))
    end_x = min(float(content_right), content_start_x + logical_width)
    if end_x <= start_x:
        return []

    blocks = strip_block_layout(
        widget,
        content_start_x=content_start_x,
        start_x=start_x,
        end_x=end_x,
        overscan_blocks=overscan_blocks,
    )
    seen: set[int] = set()
    out: list[int] = []
    for _, _, rep in blocks:
        if rep not in seen:
            seen.add(rep)
            out.append(rep)
    return out

def compute_total_frames(widget) -> int:
    duration = widget.get_total_duration()
    if duration <= 0:
        return 0
    return max(1, int(math.ceil(duration * widget._fps)) + 1)

def get_viewport_width(widget) -> int:
    viewport_width = 800
    parent = widget.parent()
    if parent:
        if isinstance(parent, QScrollArea):
            viewport_width = parent.viewport().width()
        elif isinstance(parent, QWidget):
            grandparent = parent.parent()
            if isinstance(grandparent, QScrollArea):
                viewport_width = grandparent.viewport().width()
            else:
                viewport_width = parent.width()
    return viewport_width

def calculate_min_zoom(widget) -> float:
    if widget._total_frames <= 0:
        return 0.1
    viewport_width = max(
        1,
        get_viewport_width(widget) - widget.LEFT_GUTTER - right_inset(widget),
    )
    content_at_zoom1 = widget._total_frames * get_base_tile_width(widget)
    if content_at_zoom1 <= 0:
        return 1.0
    return viewport_width / content_at_zoom1

def fit_view(widget) -> None:
    """Fit the whole recording: commit min zoom, then sync width/paint.

    The zoom write travels the single commit path (``commit_state`` owns
    ``widget._zoom_level``) with ``source="fitView"``; callers that need
    a silent follow-up (``widget.fit_view``'s write-through,
    ``_on_layout_settle``'s ``"settleFit"`` commit) stay silent
    no-change re-commits.
    """
    nxt = _snapshot_with_zoom(widget, calculate_min_zoom(widget))
    # Through the widget's named entry (see commit_zoom): keeps
    # _commitState overrides / spies observable.
    widget._commitState(nxt, "fitView")
    update_fixed_width(widget)
    widget.update()

def update_fixed_width(widget) -> None:
    if widget._total_frames <= 0:
        return
    content_width = int(
        math.ceil(widget.LEFT_GUTTER + get_logical_width(widget) + right_inset(widget))
    )
    viewport_width = max(1, get_viewport_width(widget) - right_inset(widget))
    final_width = max(content_width, viewport_width + right_inset(widget))
    if widget.width() != final_width:
        widget._suppress_resize_recalc = True
        try:
            if _timeline_debug_enabled():
                gutter_debug(
                    "tick=%s fixed-width %s->%s gutter=%s logical=%.1f",
                    _next_tick(), widget.width(), final_width,
                    widget.LEFT_GUTTER, get_logical_width(widget),
                )
            widget.setFixedWidth(final_width)
        finally:
            widget._suppress_resize_recalc = False
    widget.update()

def format_time(seconds: float, step: float | None = None) -> str:
    seconds = round(float(seconds), 6)
    m = int(seconds // 60)
    s = int(seconds % 60)
    frac = max(0.0, seconds - math.floor(seconds))

    decimals = 1
    if step is not None and step > 0:
        if step >= 1.0:
            decimals = 0
        else:
            decimals = max(1, min(3, int(math.ceil(-math.log10(step) - 1e-9))))

    if decimals <= 0:
        return f"{m}:{s:02d}" if m > 0 else f"{s}"

    frac_text = f"{frac:.{decimals}f}".split(".")[1]
    if m > 0:
        return f"{m}:{s:02d}.{frac_text}"
    return f"{s}.{frac_text}"

def choose_ruler_step(duration: float, logical_width: float) -> float:
    if duration <= 0 or logical_width <= 0:
        return 1.0
    min_label_spacing_px = scaled_px(72.0)
    for step in (
        0.001,
        0.002,
        0.005,
        0.01,
        0.02,
        0.05,
        0.1,
        0.2,
        0.25,
        0.5,
        1.0,
        2.0,
        5.0,
        10.0,
        15.0,
        30.0,
        60.0,
    ):
        if (step / duration) * logical_width >= min_label_spacing_px:
            return step
    return 60.0

def choose_ruler_subdivisions(
    major_step: float,
    duration: float,
    logical_width: float,
) -> int:
    if major_step <= 0 or duration <= 0 or logical_width <= 0:
        return 1
    major_px = (major_step / duration) * logical_width
    if major_px >= 360:
        return 10
    if major_px >= 180:
        return 5
    if major_px >= 96:
        return 4
    if major_px >= 64:
        return 2
    return 1

def pos_to_frame(widget, x: float) -> int:
    if widget._total_frames <= 0:
        return 0
    logical_width = get_logical_width(widget)
    if logical_width <= 0:
        return 0
    ratio = (x - widget.LEFT_GUTTER) / logical_width
    frame = int(round(ratio * frame_span(widget)))
    return max(0, min(frame, widget._total_frames - 1))

def pos_to_float_index(widget, x: float) -> float:
    if widget._total_frames <= 0:
        return 0.0
    logical_width = get_logical_width(widget)
    if logical_width <= 0:
        return 0.0
    ratio = (float(x) - widget.LEFT_GUTTER) / logical_width
    index = ratio * frame_span(widget)
    return max(0.0, min(index, float(widget._total_frames - 1)))

def frame_to_pos(widget, frame: int) -> int:
    if widget._total_frames <= 0:
        return widget.LEFT_GUTTER
    return int(widget.LEFT_GUTTER + frame * get_slot_width(widget))

def visual_pos_from_index(widget, float_index: float) -> float:
    if widget._total_frames <= 0:
        return float(widget.LEFT_GUTTER)
    return widget.LEFT_GUTTER + float_index * get_slot_width(widget)

def get_scroll_area(widget):
    parent = widget.parent()
    while parent:
        if isinstance(parent, QScrollArea):
            return parent
        parent = parent.parent()
    return None

def get_inner_sb_handle_rect(widget, sb_rect: QRectF) -> QRectF:
    scroll_area = get_scroll_area(widget)
    if scroll_area is None:
        return QRectF()
    h_bar = scroll_area.horizontalScrollBar()
    if h_bar.maximum() <= h_bar.minimum():
        return QRectF()
    total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
    if total <= 0:
        return QRectF()
    padding = _INNER_SB_TRACK_PADDING
    track_w = sb_rect.width() - padding * 2
    if track_w <= 0:
        return QRectF()
    handle_w = max(20.0, (h_bar.pageStep() / total) * track_w)
    scroll_range = h_bar.maximum() - h_bar.minimum()
    ratio = (h_bar.value() - h_bar.minimum()) / scroll_range
    handle_x = sb_rect.left() + padding + ratio * (track_w - handle_w)
    thickness = _INNER_SB_THICKNESS
    handle_y = sb_rect.top() + (sb_rect.height() - thickness) / 2.0
    return QRectF(handle_x, handle_y, handle_w, thickness)

def draw_inner_scrollbar(
    widget,
    painter: QPainter,
    sb_rect: QRectF,
    idle_color: QColor | None = None,
    hover_color: QColor | None = None,
) -> None:
    if sb_rect.height() < 4:
        return
    handle_rect = get_inner_sb_handle_rect(widget, sb_rect)
    if handle_rect.isEmpty():
        return
    if idle_color is None:
        idle_color = timeline_theme.scrollbar_idle_color(widget)
    if hover_color is None:
        hover_color = timeline_theme.scrollbar_hover_color(widget)
    if widget._sb_dragging:
        color = resolve_accent_color(widget)
    elif sb_rect.contains(QPointF(widget.mapFromGlobal(widget.cursor().pos()))):
        color = hover_color
    else:
        color = idle_color
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    radius = handle_rect.height() / 2.0
    painter.drawRoundedRect(handle_rect, radius, radius)
    painter.restore()

def sb_strip_rect(widget) -> QRectF:
    scroll_area = get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    viewport_width = max(0, get_viewport_width(widget) - right_inset(widget))
    footer_top = widget.height() - footer_height(widget)
    return QRectF(
        scroll_offset + widget.LEFT_GUTTER,
        footer_top,
        max(0.0, viewport_width - widget.LEFT_GUTTER),
        widget.SCROLLBAR_STRIP_HEIGHT,
    )

def update_hover_tooltip(widget, pos) -> None:
    point = QPointF(pos)
    for rect, text in widget._hover_points:
        if rect.contains(point):
            widget._hover_tooltip_text = text
            widget._hover_tooltip_pos = widget.mapToGlobal(pos)
            if not widget._tooltip_timer.isActive():
                widget._tooltip_timer.start()
            return
    widget._tooltip_timer.stop()
    widget._hover_tooltip_text = None
    widget._hover_tooltip_pos = None
    PathTooltip.get_instance().hide_tooltip()

def show_hover_tooltip(widget) -> None:
    if widget._hover_tooltip_text and widget._hover_tooltip_pos is not None:
        PathTooltip.get_instance().show_tooltip(
            widget._hover_tooltip_pos,
            widget._hover_tooltip_text,
        )

def is_on_gutter_handle(widget, x: int) -> bool:
    scroll_area = get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    return abs(x - (scroll_offset + widget.LEFT_GUTTER)) <= widget.GUTTER_RESIZE_MARGIN


def damage_pad() -> float:
    """Single cull-pad constant, owned by ``layout`` (wave A).

    SUPERVISOR-DEDUP: resolves ``layout.DAMAGE_PAD`` when wave A lands it;
    until then falls back to the identical value 12.0 — never two live
    pads, never a second definition site.
    """
    from . import layout as timeline_layout  # function-level: layout owns the top-level edge (I3)

    return float(getattr(timeline_layout, "DAMAGE_PAD", 12.0))


def clamp_gutter_width(widget, raw_x: float) -> float:
    """Clamp a gutter-drag x to ``[MIN_LEFT_GUTTER, MAX_LEFT_GUTTER]``.

    Single clamping site for the gutter-drag path (mirrors
    ``clamp_zoom``): design range 140–320 px, read off the live widget
    fields so the UiScale-applied values stay authoritative.
    """
    lo = float(getattr(widget, "MIN_LEFT_GUTTER", 140))
    hi = float(getattr(widget, "MAX_LEFT_GUTTER", 320))
    return max(lo, min(float(raw_x), hi))


@dataclass(frozen=True, slots=True)
class RowGutterWindow:
    """One-pass lane+gutter row window (Phase 2B seam, wave C consumes).

    ``start``/``end``/``y_at_start`` mirror
    ``layout.visible_row_window`` exactly (``widget._row_layout[start:end]``
    holds the rows intersecting the viewport; ``y_at_start`` is the
    widget-space y of row ``start``). ``gutter_rects`` holds one
    ``(top, bottom)`` widget-space-y pair per row in ``[start:end]``,
    aligned to the same rows the lane pass paints. The gutter x-band is
    implicit: ``[gutter_x, gutter_x + gutter_width]`` where ``gutter_x``
    is the sticky offset (== horizontal scroll) and ``gutter_width`` is
    the live ``LEFT_GUTTER``.
    """

    start: int
    end: int
    y_at_start: float
    gutter_x: float
    gutter_width: float
    gutter_rects: tuple[tuple[float, float], ...]


def _row_height_for_kind(widget, kind: str) -> float:
    if kind == "group":
        return float(widget.GROUP_HEADER_HEIGHT)
    if kind == "track_single":
        return float(widget.TRACK_ROW_HEIGHT)
    return float(widget.CHANNEL_ROW_HEIGHT)


def visible_row_gutter_window(
    widget,
    rows_top: float,
    rows_bottom: float,
    *,
    content_top: float = 0.0,
    scroll_offset: float = 0.0,
) -> RowGutterWindow:
    """Wrap ``layout.visible_row_window`` with aligned gutter rects.

    Consumes (never reimplements) the frozen ``visible_row_window``
    geometry: ``(start, end, y_at_start)`` come straight from layout, and
    the ``(top, bottom)`` pairs are accumulated from ``y_at_start`` with
    the widget's own row-height constants — the same constants the lane
    and sticky-gutter paint passes step with, so gutter rect ``i`` always
    covers lane row ``start + i``.
    """
    from . import layout as timeline_layout  # function-level: layout owns the top-level edge (I3)

    start, end, y_at_start = timeline_layout.visible_row_window(
        widget, rows_top, rows_bottom, content_top=content_top
    )
    rects: list[tuple[float, float]] = []
    y = float(y_at_start)
    for item in widget._row_layout[start:end]:
        row_h = _row_height_for_kind(widget, item[0])
        rects.append((y, y + row_h))
        y += row_h
    return RowGutterWindow(
        start=int(start),
        end=int(end),
        y_at_start=float(y_at_start),
        gutter_x=float(scroll_offset),
        gutter_width=float(widget.LEFT_GUTTER),
        gutter_rects=tuple(rects),
    )


def gutter_band_rect(widget, scroll: int) -> QRect:
    """Gutter damage band in content coords, chevron/gradient-covering.

    ``[scroll, scroll + LEFT_GUTTER + 2] x [0, footer_top]``: the sticky
    overlay paints the gutter at ``gx = scroll`` with a ``LEFT_GUTTER + 2``
    clip, the group chevron lives at ``gx + 8 .. gx + 26`` (inside), the
    wash/edge gradients span the full gutter rect, and the ``+ 2`` covers
    the 1 px separator drawn at ``gx + LEFT_GUTTER``. Same geometry as
    ``widget.gutter_band_rect_for_scroll`` (which wave C may unify with
    this helper); kept here so the drag path can band-repaint without
    touching ``widget.py``.
    """
    try:
        footer_top = int(widget.height() - footer_height(widget))
    except Exception:
        try:
            footer_top = int(widget.height())
        except Exception:
            footer_top = 0
    footer_top = max(0, footer_top)
    try:
        gutter_w = int(widget.LEFT_GUTTER) + 2
    except Exception:
        gutter_w = 2
    return QRect(int(scroll), 0, max(0, gutter_w), footer_top)


def hover_points_for_rows(
    widget,
    group,
    track,
    channel,
    points: list[tuple[float, float, Any]],
) -> list[tuple[QRectF, str]]:
    """Build hover hit-rects + tooltips for explicit points (no damage cull).

    ``points`` is ``[(x, y, keyframe)]`` in widget-space px; returns one
    ``(QRectF(x - 6, y - 6, 12, 12), tooltip)`` pair per point — the same
    12 px hit shape the segment passes use. Pure w.r.t. damage: unlike the
    ``render`` segment loops (which only append points inside
    ``[start_x, end_x]``), this helper covers every row passed in, so
    tooltips stay populated under narrow ``event.rect()`` repaints.
    RENDER-INTEGRATION (one line, supervisor wires at merge — render.py is
    wave A's file): in ``segments._draw_keyframe_segments`` replace the
    damage-gated ``widget._hover_points.append(...)`` calls with
    ``widget._hover_points.extend(hover_points_for_rows(widget, group,
    track, channel, all_points))`` computed over the full row window.
    """
    out: list[tuple[QRectF, str]] = []
    for x, y, keyframe in points:
        out.append(
            (
                QRectF(float(x) - 6.0, float(y) - 6.0, 12.0, 12.0),
                tooltip_for_keyframe(widget, group, track, channel, keyframe),
            )
        )
    return out

def tooltip_for_keyframe(widget, group, track, channel, keyframe) -> str:
    from . import layout as timeline_layout  # function-level: layout owns the top-level edge (I3)

    if track.kind == "color":
        # Fail-open: missing comps (e.g. no alpha "a") evaluate to None via
        # the guarded helper instead of crashing on .get() misses.
        r = timeline_layout._channel_value_at_timestamp(track.channels.get("r"), keyframe.timestamp)
        g = timeline_layout._channel_value_at_timestamp(track.channels.get("g"), keyframe.timestamp)
        b = timeline_layout._channel_value_at_timestamp(track.channels.get("b"), keyframe.timestamp)
        a = timeline_layout._channel_value_at_timestamp(track.channels.get("a"), keyframe.timestamp)
        if None not in {r, g, b}:
            value_text = f"rgba({int(r)}, {int(g)}, {int(b)}, {int(a if a is not None else 255)})"
            return (
                f"{group.label} / {track.label}"
                f"\nTime: {format_time(keyframe.timestamp)}"
                f"\nColor: {value_text}"
            )
    return (
        f"{group.label} / {track.label}"
        f"\nTime: {format_time(keyframe.timestamp)}"
        f"\n{localize_token_for(widget, channel.label)}: {localize_value_for(widget, keyframe.value)}"
    )
