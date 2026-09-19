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
        interaction as timeline_interaction,
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
    margin = int(math.ceil(max(1.0, draw_w / slot) * timeline_interaction._THUMBNAIL_KEEP_MARGIN_BLOCKS))
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
    assert len(w._thumbnails) <= timeline_interaction._THUMBNAIL_HARD_CAP
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


# --- Wave T thin-facade: delegator paths -----------------------------------------


def _group(id="g1", **overrides):
    import types

    ns = {"id": id, "tracks": {}, "accent_color": None}
    ns.update(overrides)
    return types.SimpleNamespace(**ns)


def test_group_delegators_match_layout_functions(qapp):
    """Widget group methods are thin delegators over ``layout`` (same names)."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        layout as timeline_layout,
    )

    w = TimelineWidget()
    g = _group()
    assert w._group_key(g) == timeline_layout.group_key(g) == "g1"
    assert w._group_key(_group()) == timeline_layout.group_key(_group())
    assert w._is_group_collapsed(g) == timeline_layout.is_group_collapsed(w, g) is False
    assert w._group_header_rect(10.0, 20.0) == timeline_layout.group_header_rect(w, 10.0, 20.0)
    header = w._group_header_rect(10.0, 20.0)
    assert w._group_chevron_rect(header) == timeline_layout.group_chevron_rect(header)
    assert w._group_accent_color(g) == timeline_layout.group_accent_color(w, g)
    w.close()


def test_toggle_group_collapsed_delegates_and_flips(qapp):
    """``_toggle_group_collapsed`` flips the collapsed set via ``layout``."""
    w = TimelineWidget()
    g = _group()
    w._toggle_group_collapsed(g)
    assert w._group_key(g) in w._collapsed_group_ids
    assert w._is_group_collapsed(g) is True
    w._toggle_group_collapsed(g)
    assert w._group_key(g) not in w._collapsed_group_ids
    assert w._is_group_collapsed(g) is False
    w.close()


def test_gutter_alias_matches_viewport_canonical(qapp):
    """``widget.gutter_band_rect_for_scroll`` is the viewport canonical rect."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        gutter_band_rect_for_scroll,
    )

    w = TimelineWidget(snapshots=_snaps())
    for scroll in (0, 137):
        assert gutter_band_rect_for_scroll(w, scroll) == timeline_viewport.gutter_band_rect(w, scroll)
    w.close()


def test_ingest_data_matches_set_data(qapp):
    """``interaction.ingest_data`` is the real ``set_data`` path (same outcome)."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    snaps = _snaps(6)
    a = TimelineWidget()
    a.set_data(snaps, fps=30)
    b = TimelineWidget()
    timeline_interaction.ingest_data(b, snaps, fps=30)
    assert [s.timestamp for s in b._snapshots] == [s.timestamp for s in a._snapshots]
    assert b._duration == a._duration
    assert b._fps == a._fps == 30
    assert b._total_frames == a._total_frames
    assert b._row_layout == a._row_layout
    assert b._needs_fit_view is True
    a.close()
    b.close()


def test_ingest_data_source_precedence(qapp):
    """Explicit args win over ``source`` through the ingest function too."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    snaps = _snaps(4)
    source = SimpleNamespace(snapshots=_snaps(9), fps=12, timeline_model=None, duration=9.0)
    w = TimelineWidget()
    timeline_interaction.ingest_data(w, snaps, fps=10, source=source)
    # Explicit non-None args win; None duration falls back to the source.
    assert len(w._snapshots) == 4
    assert w._fps == 10
    assert w._duration == 9.0
    timeline_interaction.ingest_data(w, snaps, fps=10, duration=5.0, source=source)
    assert w._duration == 5.0
    w.close()


def test_prune_thumbnails_function_matches_method(qapp):
    """``interaction.prune_thumbnails`` is the real ``_prune_thumbnails`` path."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    px = QPixmap(16, 9)
    w = TimelineWidget(snapshots=_long_snaps())
    w.resize(800, 240)
    w.show()
    qapp.processEvents()
    w._layout_settle.cancel()
    w.fit_view()
    w._commitState(w._current_state(), source="test")
    w._commitState(w._current_state().with_zoom(1.0), source="test")
    visible = w.get_visible_thumbnail_frame_indices(overscan_blocks=2)
    assert visible
    for i in list(range(0, w._total_frames, 5)) + [v for v in visible]:
        w._thumbnails[i] = px
    w._thumb_indices = sorted(w._thumbnails.keys())
    timeline_interaction.prune_thumbnails(w)
    assert w._thumb_indices == sorted(w._thumbnails.keys())
    visible = w.get_visible_thumbnail_frame_indices(overscan_blocks=2)
    for v in visible:
        assert v in w._thumbnails
    w.close()


def test_playhead_function_matches_method(qapp):
    """``interaction.set_current_frame`` eases steps and snaps jumps like the method."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    w = TimelineWidget()
    w._total_frames = 50
    w._visual_index = 5.0
    w._current_index = 5
    timeline_interaction.set_current_frame(w, 6)
    assert w._current_index == 6
    assert w._playhead_anim.state() == QVariantAnimation.State.Running
    timeline_interaction.playhead_frame(w, 5.5)
    assert abs(w._visual_index - 5.5) < 1e-9
    timeline_interaction.set_current_frame(w, 40)
    assert w._current_index == 40
    assert w._visual_index == 40.0
    w.close()


def test_flush_function_commits_once_with_wheel_source(qapp, monkeypatch):
    """``interaction.flush_wheel_zoom`` commits one step with the wheel source."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    w = TimelineWidget()
    w._total_frames = 50
    w._commitState(w._current_state(), source="test")
    w._commitState(w._current_state().with_zoom(0.5), source="test")
    sources: list = []
    orig_commit = TimelineWidget._commitState

    def spy(self, nxt, source=""):
        sources.append(source)
        return orig_commit(self, nxt, source)

    monkeypatch.setattr(TimelineWidget, "_commitState", spy)
    w._wheel_pending_y = 120.0
    w._wheel_pending_x = 400.0
    w._wheel_pending_ticks = 1
    w._wheel_flush_scheduled = True
    timeline_interaction.flush_wheel_zoom(w)
    assert sources == ["wheelZoom"]
    assert w._wheel_flush_scheduled is False
    assert w._zoom_level > 0.5
    w.close()


# --- Phase 1 T-state: frozen base_tile (I1) --------------------------------------


def _tstate_widget(qapp, n=60, fps=30):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    w = TimelineWidget()
    w.set_data(_snaps(n), fps=fps)
    w._layout_settle.cancel()
    return w, timeline_viewport


def _geometry_snapshot(w, vp):
    return (
        vp.get_base_tile_width(w),
        vp.get_logical_width(w),
        w.get_pixels_per_second(),
        vp.calculate_min_zoom(w),
    )


def test_base_tile_frozen_under_thumbnail_arrivals(qapp):
    """Geometry never depends on thumbnail data or arrival order (I1).

    Arrivals with distinct pixmap aspects — including at index 0, which the
    old first-pixmap sizing read — must not move base_tile, logical_width,
    pps, or min_zoom.
    """
    w, vp = _tstate_widget(qapp)
    try:
        before = _geometry_snapshot(w, vp)
        assert before[0] == w.STRIP_HEIGHT * 16 / 9
        w.add_thumbnail(0, QPixmap(18, 64))
        assert _geometry_snapshot(w, vp) == before
        w.add_thumbnail(7, QPixmap(64, 18))
        w.add_thumbnail(23, QPixmap(200, 200))
        assert _geometry_snapshot(w, vp) == before
        w.set_thumbnails({3: QPixmap(32, 32), 41: QPixmap(96, 24)})
        assert _geometry_snapshot(w, vp) == before
    finally:
        w.close()


def test_base_tile_frozen_under_eviction_and_clear(qapp):
    """Evictions (prune) and clear_thumbnails keep geometry frozen (I1)."""
    w, vp = _tstate_widget(qapp, n=101)
    try:
        w.resize(800, 240)
        w.show()
        qapp.processEvents()
        w._layout_settle.cancel()
        w.fit_view()
        w._commitState(w._current_state(), source="test")
        w._commitState(w._current_state().with_zoom(1.0), source="test")
        before = _geometry_snapshot(w, vp)
        px = QPixmap(16, 9)
        for i in list(range(0, w._total_frames, 37)) + [0]:
            w.add_thumbnail(i, px)
        # Prune ran on every insert (committed state); far frames evicted.
        assert _geometry_snapshot(w, vp) == before
        w.clear_thumbnails()
        assert w._thumbnails == {}
        assert _geometry_snapshot(w, vp) == before
    finally:
        w.close()


def test_thumbnail_for_rep_exact_hit_and_miss(qapp):
    """I2: exact match only — hit returns the pixmap, any miss is None."""
    w, vp = _tstate_widget(qapp)
    try:
        assert vp.thumbnail_for_rep(w, 2) is None
        px_a = QPixmap(16, 9)
        px_b = QPixmap(16, 9)
        w.set_thumbnails({2: px_a, 5: px_b})
        assert vp.thumbnail_for_rep(w, 2) is px_a
        assert vp.thumbnail_for_rep(w, 5) is px_b
        # Neighbors exist but the rep itself is absent: no bisect, no idx[0].
        assert vp.thumbnail_for_rep(w, 3) is None
        assert vp.thumbnail_for_rep(w, 4) is None
        assert vp.thumbnail_for_rep(w, 0) is None
        assert vp.thumbnail_for_rep(w, 10**9) is None
    finally:
        w.close()


def test_min_zoom_equals_fitted_frame_span(qapp):
    """min_zoom uses frame_span (total-1) like get_logical_width: precisely fitted."""
    w, vp = _tstate_widget(qapp)
    try:
        assert vp.right_inset(w) == 0
        available = 800 - w.LEFT_GUTTER
        base = vp.get_base_tile_width(w)
        expected = available / ((w._total_frames - 1) * base)
        assert vp.calculate_min_zoom(w) == expected
        w._zoom_level = float(expected)
        assert vp.get_logical_width(w) == available
    finally:
        w.close()


def test_rep_set_stable_across_thumbnail_churn(qapp):
    """At fixed (total_frames, base_tile, zoom) the rep set is identical
    before and after arbitrary thumbnail arrivals/evictions (I1)."""
    w, vp = _tstate_widget(qapp)
    try:
        w.resize(800, 240)
        w.show()
        qapp.processEvents()
        w._layout_settle.cancel()
        w.fit_view()
        w._commitState(w._current_state(), source="test")
        w._commitState(w._current_state().with_zoom(1.0), source="test")
        csx = float(w.LEFT_GUTTER)
        logical = vp.get_logical_width(w)

        def reps():
            return [
                rep
                for _, _, rep in vp.strip_block_layout(
                    w, content_start_x=csx, start_x=csx, end_x=csx + logical
                )
            ]

        before = reps()
        assert before
        w.add_thumbnail(0, QPixmap(18, 64))
        for i in range(0, w._total_frames, 13):
            w.add_thumbnail(i, QPixmap(64, 18))
        w.clear_thumbnails()
        w.set_thumbnails({i: QPixmap(16, 9) for i in range(0, w._total_frames, 7)})
        assert reps() == before
    finally:
        w.close()


def test_snapshot_size_metadata_freezes_aspect(qapp):
    """Snapshots carrying frame size freeze the aspect; pixmaps never override."""
    from types import SimpleNamespace

    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    snaps = [SimpleNamespace(timestamp=float(i), width=640, height=480) for i in range(5)]
    w = TimelineWidget()
    try:
        w.set_data(snaps, fps=30)
        w._layout_settle.cancel()
        assert timeline_viewport.frozen_thumb_aspect(w) == 640 / 480
        assert timeline_viewport.get_base_tile_width(w) == w.STRIP_HEIGHT * 640 / 480
        w.add_thumbnail(0, QPixmap(18, 64))
        assert timeline_viewport.frozen_thumb_aspect(w) == 640 / 480
        assert timeline_viewport.get_base_tile_width(w) == w.STRIP_HEIGHT * 640 / 480
    finally:
        w.close()


def test_snapshot_without_size_falls_back_to_16_9(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    w, _vp = _tstate_widget(qapp)
    try:
        assert timeline_viewport.frozen_thumb_aspect(w) == 16 / 9
        # Second dataset re-freezes (fresh ingest key), same fallback value.
        w.set_data(_snaps(9), fps=30)
        w._layout_settle.cancel()
        assert timeline_viewport.frozen_thumb_aspect(w) == 16 / 9
    finally:
        w.close()


def test_zoom_diff_eps_single_source(qapp):
    """ZOOM_DIFF_EPS is the one diff epsilon (1e-4) for state + viewport."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        state as timeline_state,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    assert timeline_state.ZOOM_DIFF_EPS == 1e-4
    assert timeline_viewport.ZOOM_DIFF_EPS == 1e-4
    assert _state().has_zoom_changed(_state(), eps=timeline_state.ZOOM_DIFF_EPS) is False


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
