"""Timeline Phase C: single-source state, settle coalescing, playhead animation.

Covers the tl-state-c cleanup in
``src/sli_ui_toolkit/ui/widgets/composite/timeline_widget/``:

* ``TimelineViewportState`` diff semantics (eps zoom, ``==`` geometry) and
  the ``with_zoom`` single-source funnel;
* ``_commitState`` emit semantics (first commit emits, identical re-commit
  is silent, zoom change emits ``zoomChanged`` and syncs live fields);
* ``set_data``/``__init__`` no longer ``singleShot(0, fit_view)`` — the fit
  is coalesced through ``_layout_settle`` (one fit per flush);
* playhead smoothing is a 150 ms ``OutCubic`` ``QVariantAnimation``
  (value interpolator, no target — a target-less ``QPropertyAnimation``
  spams "Changing state of an animation without target"; snap on large
  jumps, ease on steps);
* ``inspect_spec.token_family`` references ``TIMELINE_TOKENS``;
* per-widget i18n bindings are isolated (global fallback intact), and
  constructing a widget never overwrites the process-global hooks;
* Phase 3C lifecycle: teardown disconnects (``UiScale.scale_changed``,
  host scrollbar signals, event filters), deferred callbacks
  (``_flush_wheel_zoom``, ``_on_layout_settle``) never commit/emit after
  close, the thumbnail store is bounded to the visible window plus
  margin, ``source="gutterDrag"`` travels the generic emit path, and the
  deprecated ``resized`` / ``layoutSettled`` signals are gone.
"""

from __future__ import annotations

import gc
import math
import warnings
import weakref
from types import SimpleNamespace

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QScrollArea

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    TIMELINE_TOKENS,
    TimelineCallbacks,
    TimelineViewportState,
    TimelineWidget,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import i18n as timeline_i18n


def _snaps(n: int = 5):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def _state(**overrides):
    base = {
        "zoom": 0.5,
        "min_zoom": 0.25,
        "left_gutter": 180,
        "content_width": 1200,
        "viewport_width": 800,
        "scroll_x": 0,
    }
    base.update(overrides)
    return TimelineViewportState(**base)


# --- pure state diff semantics ------------------------------------------------


def test_state_zoom_eps():
    assert not _state().has_zoom_changed(_state())
    assert not _state().has_zoom_changed(_state(zoom=0.5 + 1e-5))
    assert _state().has_zoom_changed(_state(zoom=0.5 + 1e-3))
    assert _state().has_zoom_changed(None)


def test_state_geometry_equality():
    assert not _state().has_geometry_changed(_state())
    assert _state().has_geometry_changed(_state(scroll_x=10))
    assert _state().has_geometry_changed(_state(viewport_width=801))
    assert _state().has_geometry_changed(_state(content_width=1201))
    assert _state().has_geometry_changed(_state(left_gutter=181))
    assert _state().has_geometry_changed(None)


def test_state_fitted_and_with_zoom():
    assert _state(zoom=0.25).is_fitted()
    assert not _state().is_fitted()
    nxt = _state().with_zoom(0.75)
    assert nxt.zoom == 0.75
    assert nxt.min_zoom == 0.25
    assert not nxt.has_geometry_changed(_state())
    assert nxt.has_zoom_changed(_state())


# --- _commitState emit semantics (behavior frozen) -----------------------------


def test_commit_first_emits_all_typed_signals(qapp):
    w = TimelineWidget()
    w._total_frames = 50
    zoom, viewport, states = [], [], []
    w.zoomChanged.connect(lambda v: zoom.append(v))
    w.viewportChanged.connect(lambda: viewport.append(1))
    w.viewportChangedState.connect(states.append)
    assert w._commitState(w._current_state(), source="test") is True
    assert len(zoom) == 1
    assert len(viewport) == 1
    assert len(states) == 1
    assert isinstance(states[0], TimelineViewportState)
    assert w._zoom_level == states[0].zoom
    w.close()


def test_commit_identical_is_silent(qapp):
    w = TimelineWidget()
    w._total_frames = 50
    w._commitState(w._current_state(), source="test")
    fired = []
    w.zoomChanged.connect(lambda v: fired.append(v))
    w.viewportChanged.connect(lambda: fired.append(None))
    w.viewportChangedState.connect(fired.append)
    assert w._commitState(w._current_state(), source="test") is False
    assert fired == []
    w.close()


def test_commit_zoom_change_emits_and_syncs(qapp):
    w = TimelineWidget()
    w._total_frames = 50
    w._commitState(w._current_state(), source="test")
    zoom = []
    w.zoomChanged.connect(lambda v: zoom.append(v))
    nxt = w._current_state().with_zoom(w._zoom_level * 1.1 + 0.01)
    assert w._commitState(nxt, source="test") is True
    assert zoom == [nxt.zoom]
    assert w._zoom_level == nxt.zoom
    assert w._last_min_zoom == nxt.min_zoom
    w.close()


# --- settle coalescing (no more singleShot(0, fit_view)) -----------------------


def test_set_data_coalesces_fit_through_settle(qapp):
    w = TimelineWidget()
    calls: list[str] = []
    w.fit_view = lambda: calls.append("fit")  # type: ignore[method-assign]
    w.set_data(_snaps())
    w.set_data(_snaps())
    assert calls == [], "fit_view must not run synchronously from set_data"
    assert w._needs_fit_view is True
    w._layout_settle.flush()
    assert calls == ["fit"], "coalesced double set_data into one fit"
    assert w._needs_fit_view is False
    w.close()


def test_init_with_snapshots_coalesces_fit(qapp):
    w = TimelineWidget(snapshots=_snaps())
    assert w._needs_fit_view is True
    assert w._layout_settle._timer.isActive()
    w._layout_settle.flush()
    assert w._needs_fit_view is False
    # Settle path fits: zoom clamped to min_zoom like the old singleShot did.
    assert abs(w._zoom_level - w._last_min_zoom) < 1e-4
    w.close()


# --- playhead animation (QVariantAnimation 150 ms OutCubic) --------------------


def test_playhead_step_eases_with_out_cubic(qapp):
    w = TimelineWidget()
    w._total_frames = 50
    w._visual_index = 5.0
    w._current_index = 5
    anim = w._playhead_anim
    assert isinstance(anim, QVariantAnimation)
    assert anim.duration() == 150
    assert anim.easingCurve().type() == QEasingCurve.Type.OutCubic
    w.set_current_frame(6)
    assert w._current_index == 6
    assert anim.state() == QVariantAnimation.State.Running
    assert float(anim.endValue()) == 6.0
    anim.setCurrentTime(anim.duration())
    QApplication.processEvents()
    assert abs(w._visual_index - 6.0) < 1e-3
    w.close()


def test_playhead_large_jump_snaps_without_animation(qapp):
    w = TimelineWidget()
    w._total_frames = 100
    w._visual_index = 5.0
    w._current_index = 5
    w.set_current_frame(40)
    assert w._current_index == 40
    assert w._visual_index == 40.0
    assert w._playhead_anim.state() != QVariantAnimation.State.Running
    w.close()


def test_lerp_timer_gone(qapp):
    w = TimelineWidget()
    assert not hasattr(w, "_lerp_timer")
    assert not hasattr(w, "_process_lerp")
    w.close()


# --- token_family coverage ------------------------------------------------------


def test_token_family_references_timeline_tokens():
    # Integration: token_family is the canonical theme.TIMELINE_TOKENS
    # (timeline.* tokens + wash alphas), not the 6 legacy shared keys.
    assert len(TIMELINE_TOKENS) >= 20
    assert set(TIMELINE_TOKENS) >= {
        "timeline.gutter.background",
        "timeline.separator.row",
        "timeline.center.line",
        "timeline.keyframe.outline",
        "timeline.playhead.outline",
        "timeline.scrollbar.idle",
    }
    spec = TimelineWidget.inspect_spec
    assert tuple(spec.token_family) == tuple(TIMELINE_TOKENS)
    descriptor_tokens = TimelineWidget.widget_descriptor.inspect.token_family
    assert tuple(descriptor_tokens) == tuple(TIMELINE_TOKENS)


# --- per-widget i18n scope --------------------------------------------------------


def test_i18n_per_widget_isolation(qapp):
    old_token, old_value = (
        timeline_i18n._localize_token_fn,
        timeline_i18n._localize_value_fn,
    )
    try:
        w1 = TimelineWidget(
            callbacks=TimelineCallbacks(localize_token=lambda t: f"A:{t}")
        )
        w2 = TimelineWidget(
            callbacks=TimelineCallbacks(localize_token=lambda t: f"B:{t}")
        )
        assert timeline_i18n.localize_token_for(w1, "x") == "A:x"
        assert timeline_i18n.localize_token_for(w2, "x") == "B:x"
        # Unbound widget falls back to the process-global hook.
        timeline_i18n.set_localize_token(lambda t: f"G:{t}")
        assert timeline_i18n.localize_token_for(object(), "x") == "G:x"
        assert timeline_i18n.localize_token_for(None, "plain") == "G:plain"
        w1.close()
        w2.close()
    finally:
        timeline_i18n.set_localize_token(old_token)
        timeline_i18n.set_localize_value(old_value)


def test_construct_never_overwrites_process_global_i18n(qapp):
    old_token, old_value = (
        timeline_i18n._localize_token_fn,
        timeline_i18n._localize_value_fn,
    )
    try:
        timeline_i18n.set_localize_token(None)
        timeline_i18n.set_localize_value(None)
        w = TimelineWidget(
            callbacks=TimelineCallbacks(
                localize_token=lambda t: f"A:{t}",
                localize_value=lambda v: f"A:{v}",
            )
        )
        # Construction binds per-instance hooks only — globals untouched.
        assert timeline_i18n._localize_token_fn is None
        assert timeline_i18n._localize_value_fn is None
        assert timeline_i18n.localize_token_for(w, "x") == "A:x"
        assert timeline_i18n.localize_value_for(w, 1) == "A:1"
        # The host can still set the process-global explicitly for the
        # widget-less viewport/primitives paths; per-widget hooks win.
        timeline_i18n.set_localize_token(lambda t: f"G:{t}")
        assert timeline_i18n.localize_token_for(object(), "x") == "G:x"
        assert timeline_i18n.localize_token_for(w, "x") == "A:x"
        w.close()
    finally:
        timeline_i18n.set_localize_token(old_token)
        timeline_i18n.set_localize_value(old_value)


# --- Phase 3C lifecycle: teardown ----------------------------------------------


def test_close_disconnects_scale_singleton_and_releases(qapp):
    """No global singleton retains the widget after close (weakref proof)."""
    w = TimelineWidget()
    ref = weakref.ref(w)
    w.close()
    qapp.processEvents()
    del w
    gc.collect()
    gc.collect()
    assert ref() is None


def test_closed_widget_ignores_scale_changes(qapp, monkeypatch):
    """Post-close ``scale_changed`` never reaches the torn-down widget."""
    from sli_ui_toolkit.ui.managers.ui_scale import UiScale

    seen: list = []
    monkeypatch.setattr(
        TimelineWidget, "_on_scale_changed", lambda self, f: seen.append(f)
    )
    w = TimelineWidget()
    w.close()
    UiScale.get_instance().scale_changed.emit(1.0)
    qapp.processEvents()
    assert seen == []
    w.close()


def test_close_unbinds_host_scrollbar(qapp, monkeypatch):
    """Host scrollbar signals stop reaching the widget after close."""
    area = QScrollArea()
    area.resize(800, 240)
    w = TimelineWidget(snapshots=_snaps())
    area.setWidget(w)
    w.resize(1200, 240)
    calls: list = []
    monkeypatch.setattr(
        TimelineWidget, "_on_host_scroll", lambda self, *a: calls.append(1)
    )
    area.show()
    qapp.processEvents()
    qapp.processEvents()
    assert w._host_h_scrollbar is not None
    scrollbar = w._host_h_scrollbar
    scrollbar.setValue(scrollbar.maximum())
    qapp.processEvents()
    assert calls, "expected at least one host-scroll delivery while bound"
    w.close()
    qapp.processEvents()
    assert w._host_h_scrollbar is None
    before = len(calls)
    scrollbar.setValue(scrollbar.minimum())
    qapp.processEvents()
    assert len(calls) == before
    area.close()


def test_hide_suspends_timers_and_animation(qapp):
    """hideEvent stops the tooltip timer + playhead anim; reshow works."""
    w = TimelineWidget()
    w._total_frames = 50
    w.resize(800, 240)
    w.show()
    qapp.processEvents()
    w._tooltip_timer.start()
    w._visual_index = 5.0
    w._current_index = 5
    w.set_current_frame(6)
    assert w._playhead_anim.state() == QVariantAnimation.State.Running
    w.hide()
    qapp.processEvents()
    assert not w._tooltip_timer.isActive()
    assert w._playhead_anim.state() != QVariantAnimation.State.Running
    # Reshow reinstalls the symmetric event filters without crashing.
    w.show()
    qapp.processEvents()
    w.close()


def test_flush_wheel_zoom_noop_after_close(qapp):
    """A pending singleShot flush never commits/emits on a closed widget."""
    w = TimelineWidget()
    w._total_frames = 50
    w._commitState(w._current_state(), source="test")
    fired: list = []
    w.zoomChanged.connect(lambda v: fired.append(v))
    w.viewportChanged.connect(lambda: fired.append(None))
    w.viewportChangedState.connect(fired.append)
    w._wheel_pending_y = 120.0
    w._wheel_pending_x = 400.0
    w._wheel_pending_ticks = 1
    w._wheel_flush_scheduled = True
    w.close()
    w._flush_wheel_zoom()
    assert fired == []
    assert w._wheel_flush_scheduled is False


def test_layout_settle_noop_after_close(qapp):
    """A pending settle fit never commits/emits on a closed widget."""
    w = TimelineWidget(snapshots=_snaps())
    w._layout_settle.cancel()
    fired: list = []
    w.viewportChanged.connect(lambda: fired.append(1))
    w.viewportChangedState.connect(fired.append)
    w._needs_fit_view = True
    zoom_before = w._zoom_level
    w.close()
    w._on_layout_settle()
    assert fired == []
    assert w._zoom_level == zoom_before
    assert w._needs_fit_view is True


# --- Phase 3C lifecycle: thumbnail LRU bound ------------------------------------


def _long_snaps(n: int = 101):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def test_thumbnails_pruned_to_visible_window_plus_margin(qapp):
    """The store keeps the visible window + margin, evicts the far rest."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        widget as timeline_widget_mod,
    )

    w = TimelineWidget(snapshots=_long_snaps())
    w.resize(800, 240)
    w.show()
    qapp.processEvents()
    w._layout_settle.cancel()
    w.fit_view()
    w._commitState(w._current_state(), source="test")
    # Zoom in: the visible window shrinks to a handful of blocks so the
    # bound has something to evict.
    w._commitState(w._current_state().with_zoom(1.0), source="test")
    visible = w.get_visible_thumbnail_frame_indices(overscan_blocks=1)
    assert visible and len(visible) <= 12
    px = QPixmap(16, 9)
    inserted = list(range(0, w._total_frames, 37))
    inserted += [v for v in visible if v not in inserted]
    for i in inserted:
        w.add_thumbnail(i, px)
    slot = timeline_viewport.get_slot_width(w)
    base = timeline_viewport.get_base_tile_width(w)
    draw_w = base if slot < base else slot
    margin = int(math.ceil(max(1.0, draw_w / slot) * timeline_widget_mod._THUMBNAIL_KEEP_MARGIN_BLOCKS))
    lo = max(0, min(visible) - margin)
    hi = min(w._total_frames - 1, max(visible) + margin)
    assert set(w._thumbnails) == {i for i in inserted if lo <= i <= hi}
    assert w._thumb_indices == sorted(w._thumbnails.keys())
    # Every visible rep survived; far frames are gone.
    for v in visible:
        assert v in w._thumbnails
    far = [i for i in inserted if i > max(visible) + 100]
    assert far, "need off-window inserts for the eviction probe"
    assert all(i not in w._thumbnails for i in far)
    assert len(w._thumbnails) <= timeline_widget_mod._THUMBNAIL_HARD_CAP
    w.close()


def test_thumbnails_prefit_bulk_load_kept(qapp):
    """Fail-open: no committed geometry yet (pre-fit) keeps everything."""
    px = QPixmap(16, 9)
    w = TimelineWidget(snapshots=_long_snaps())
    w._layout_settle.cancel()
    bulk = {i: px for i in range(0, 200, 7)}
    w.set_thumbnails(bulk)
    assert set(w._thumbnails) == set(bulk)
    assert w._thumb_indices == sorted(bulk)
    w.close()


# --- Phase 3C lifecycle: gutterDrag commit source ---------------------------------


def test_commit_gutter_drag_emits_viewport_family_not_zoom(qapp):
    """CUTOVER-C contract: ``source="gutterDrag"`` is pure geometry — the
    viewport family emits, ``zoomChanged`` stays silent, and the commit
    syncs ``LEFT_GUTTER`` itself (so the drag path can drop its direct
    write)."""
    w = TimelineWidget()
    w._total_frames = 50
    w._commitState(w._current_state(), source="test")
    zoom, viewport, states = [], [], []
    w.zoomChanged.connect(lambda v: zoom.append(v))
    w.viewportChanged.connect(lambda: viewport.append(1))
    w.viewportChangedState.connect(states.append)
    nxt = w._current_state().with_left_gutter(int(w.LEFT_GUTTER) + 20)
    assert w._commitState(nxt, source="gutterDrag") is True
    assert zoom == []
    assert len(viewport) == 1
    assert len(states) == 1
    assert states[0].left_gutter == nxt.left_gutter
    assert w.LEFT_GUTTER == nxt.left_gutter
    w.close()


# --- Phase 3C lifecycle: deprecated signals deleted -------------------------------


def test_deprecated_viewport_signals_removed(qapp):
    assert not hasattr(TimelineWidget, "resized")
    assert not hasattr(TimelineWidget, "layoutSettled")
    w = TimelineWidget()
    w._total_frames = 50
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        w._commitState(w._current_state(), source="test")
    assert [
        r
        for r in records
        if "resized" in str(r.message) or "layoutSettled" in str(r.message)
    ] == []
    w.close()
