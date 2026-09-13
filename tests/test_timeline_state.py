"""Timeline Phase C: single-source state, settle coalescing, playhead animation.

Covers the tl-state-c cleanup in
``src/sli_ui_toolkit/ui/widgets/composite/timeline_widget/``:

* ``TimelineViewportState`` diff semantics (eps zoom, ``==`` geometry) and
  the ``with_zoom`` single-source funnel;
* ``_commitState`` emit semantics (first commit emits, identical re-commit
  is silent, zoom change emits ``zoomChanged`` and syncs live fields);
* ``set_data``/``__init__`` no longer ``singleShot(0, fit_view)`` — the fit
  is coalesced through ``_layout_settle`` (one fit per flush);
* playhead smoothing is a 150 ms ``OutCubic`` ``QPropertyAnimation``
  (snap on large jumps, ease on steps);
* ``inspect_spec.token_family`` references ``TIMELINE_TOKENS``;
* per-widget i18n bindings are isolated (global fallback intact).
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QApplication

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


# --- playhead animation (QPropertyAnimation 150 ms OutCubic) --------------------


def test_playhead_step_eases_with_out_cubic(qapp):
    w = TimelineWidget()
    w._total_frames = 50
    w._visual_index = 5.0
    w._current_index = 5
    anim = w._playhead_anim
    assert isinstance(anim, QPropertyAnimation)
    assert anim.duration() == 150
    assert anim.easingCurve().type() == QEasingCurve.Type.OutCubic
    w.set_current_frame(6)
    assert w._current_index == 6
    assert anim.state() == QPropertyAnimation.State.Running
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
    assert w._playhead_anim.state() != QPropertyAnimation.State.Running
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
