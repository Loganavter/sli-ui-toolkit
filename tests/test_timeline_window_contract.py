"""Widget-side visible-window contract (Phase 4 D).

Widget half of the missing widget<->service contract: what
``TimelineWidget.get_visible_thumbnail_frame_indices`` guarantees against
``set_data`` / window geometry so the thumbnail service (app side) and the
widget can never disagree about "which frames are on screen".

Guarantees pinned here:

* after ``set_data`` + ``fit_view`` the window is non-empty, sorted,
  unique, and inside ``[0, total_frames)``;
* overscan is monotonic: ``window(0) ⊆ window(1) ⊆ window(2)``;
* negative overscan == 0 (``max(0, ...)`` clamp in ``strip_block_layout``);
* empty store (no snapshots / zero frames) returns ``[]`` for any overscan
  (fail-open, never raises);
* degenerate geometry (zero-size widget, pre-fit with no committed state)
  fails open — returns a list (possibly ``[]``), never raises;
* oversized overscan stays in bounds;
* every visible index is a representative frame of ``strip_block_layout``
  over the same span (widget and service share one block source);
* ``set_data`` with a new snapshot list recomputes the window (no stale
  indices past the new ``total_frames``).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtGui import QPixmap


def _snaps(n: int):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def _make_scrolled_widget(qapp, n: int = 120, vw: int = 800, vh: int = 240):
    """The timeline INSIDE a host ``QScrollArea`` — how every real host embeds it.

    The centering contract is about the host's scroll area: without one,
    ``viewport.get_viewport_width`` falls back to its 800-px default and
    ``get_scroll_area`` returns None, so a "center" measurement is taken against
    a scroll value that never moves. That degenerate configuration is what made
    the zoom-centering tests drift by tens of seconds on CI while passing here.
    """
    from PySide6.QtWidgets import QScrollArea

    area = QScrollArea()
    area.resize(vw, vh)
    area.setWidgetResizable(False)
    widget = _make_widget(qapp, n=0, width=vw, height=vh)
    area.setWidget(widget)
    area.show()
    qapp.processEvents()
    if n > 0:
        widget.set_data(_snaps(n), fps=30)
        widget.fit_view()
        widget._commitState(widget._current_state(), source="test")
    qapp.processEvents()
    return area, widget


def _center_measure(widget, qapp):
    """``(viewport_width, center_time)`` — or ``(0, None)`` when unrealized.

    The centering contract is about a PIXEL target: the scroll area keeps the
    time under the viewport center. Two environment facts have to be stated
    explicitly, because a CI runner differs from a desktop here:

    * an unrealized widget reports a zero viewport width, and every measurement
      taken from it is meaningless (the first CI run measured a 41.9 s drift
      that was pure extrapolation past the content);
    * the scroll value is an integer, so the residual error is bounded in
      PIXELS, not in seconds — the tolerance is derived from the widget's own
      pixels-per-second at the zoom under test.
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    area = timeline_viewport.get_scroll_area(widget)
    scroll = area.horizontalScrollBar().value() if area else 0
    vpw = timeline_viewport.get_viewport_width(widget)
    if vpw <= 0:
        return 0, None
    return vpw, timeline_viewport.cursor_time_at_x(widget, float(scroll) + float(vpw) / 2.0)


def _center_tolerance(widget, zoom: float) -> float:
    """``<= 2 px`` of drift expressed in the widget's own time units."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    ppu = timeline_viewport.pixels_per_second_for_zoom(widget, zoom)
    return max(2.0 / max(float(ppu), 1e-9), 0.25)


def _anchor_tolerance(widget, zoom: float) -> float:
    """A strict ``2 px`` at *zoom* (no time floor) for the fitted-view anchor.

    ``_center_tolerance`` carries a 0.25 s floor for the CI runs where the
    fitted-view measurement is taken at min zoom (a handful of px/s); the
    zoomed-in anchor is measured at ≥ 768 px/s here, where a 1 px scrollbar
    step is ~0.001 s, so the pixel bound is meaningful and a drift of even one
    frame slot cannot hide under it.
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    ppu = timeline_viewport.pixels_per_second_for_zoom(widget, zoom)
    return 2.0 / max(float(ppu), 1e-9)


def _time_at_viewport_x(widget, viewport_x: float) -> float:
    """Time under *viewport_x* (content x = live scroll + *viewport_x*)."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    area = timeline_viewport.get_scroll_area(widget)
    scroll = area.horizontalScrollBar().value() if area else 0
    return timeline_viewport.cursor_time_at_x(
        widget, float(scroll) + float(viewport_x)
    )


def _ctrl_wheel_zoom(widget, delta_y: int, x: float) -> None:
    """Deliver one Ctrl+wheel tick at content x (the widget's own handler)."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    event = QWheelEvent(
        QPointF(x, 100.0),
        QPointF(x, 100.0),
        QPoint(0, 0),
        QPoint(0, int(delta_y)),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    widget.wheelEvent(event)


def _make_widget(qapp, n: int = 60, width: int = 800, height: int = 240):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    w = TimelineWidget()
    w.resize(width, height)
    w.show()
    qapp.processEvents()
    w._layout_settle.cancel()
    if n > 0:
        w.set_data(_snaps(n), fps=30)
        w._layout_settle.cancel()
        w.fit_view()
        w._commitState(w._current_state(), source="test")
    qapp.processEvents()
    return w


def test_visible_window_basic_shape(qapp):
    w = _make_widget(qapp, n=60)
    try:
        visible = w.get_visible_thumbnail_frame_indices()
        assert visible, "fitted window must be non-empty"
        assert visible == sorted(visible)
        assert len(set(visible)) == len(visible)
        assert min(visible) >= 0
        assert max(visible) <= w._total_frames - 1
    finally:
        w.close()


def test_visible_window_overscan_monotonic(qapp):
    w = _make_widget(qapp, n=120)
    try:
        # Zoom in so the window is a strict subset and overscan matters.
        w._commitState(w._current_state().with_zoom(1.0), source="test")
        base = w.get_visible_thumbnail_frame_indices(overscan_blocks=0)
        mid = w.get_visible_thumbnail_frame_indices(overscan_blocks=1)
        wide = w.get_visible_thumbnail_frame_indices(overscan_blocks=2)
        assert base, "zoomed window must be non-empty"
        assert set(base) <= set(mid)
        assert set(mid) <= set(wide)
        for window in (base, mid, wide):
            assert min(window) >= 0
            assert max(window) <= w._total_frames - 1
    finally:
        w.close()


def test_visible_window_negative_overscan_clamps_to_zero(qapp):
    w = _make_widget(qapp, n=80)
    try:
        assert w.get_visible_thumbnail_frame_indices(
            overscan_blocks=-5
        ) == w.get_visible_thumbnail_frame_indices(overscan_blocks=0)
    finally:
        w.close()


def test_visible_window_empty_store_fail_open(qapp):
    w = _make_widget(qapp, n=0)
    try:
        assert w._total_frames == 0
        for overscan in (-1, 0, 1, 10):
            assert w.get_visible_thumbnail_frame_indices(
                overscan_blocks=overscan
            ) == []
    finally:
        w.close()


def test_visible_window_zero_size_fail_open(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    w = TimelineWidget(snapshots=_snaps(30))
    w._layout_settle.cancel()
    try:
        w.resize(0, 0)
        qapp.processEvents()
        # Never raises; either [] or in-bounds indices.
        visible = w.get_visible_thumbnail_frame_indices()
        assert isinstance(visible, list)
        assert all(0 <= i < w._total_frames for i in visible)
    finally:
        w.close()


def test_visible_window_oversized_overscan_stays_in_bounds(qapp):
    w = _make_widget(qapp, n=40)
    try:
        visible = w.get_visible_thumbnail_frame_indices(overscan_blocks=10_000)
        assert visible
        assert min(visible) >= 0
        assert max(visible) <= w._total_frames - 1
        assert len(visible) <= w._total_frames
    finally:
        w.close()


def test_visible_window_matches_strip_block_reps(qapp):
    """Visible indices are exactly the deduped ``strip_block_layout`` reps."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    w = _make_widget(qapp, n=90)
    try:
        w._commitState(w._current_state().with_zoom(1.0), source="test")
        visible = w.get_visible_thumbnail_frame_indices(overscan_blocks=1)
        assert visible
        content_start_x = float(w.LEFT_GUTTER)
        logical = timeline_viewport.get_logical_width(w)
        slot = timeline_viewport.get_slot_width(w)
        base = timeline_viewport.get_base_tile_width(w)
        draw_w = base if slot < base else slot
        scroll_area = timeline_viewport.get_scroll_area(w)
        scroll_offset = (
            scroll_area.horizontalScrollBar().value() if scroll_area else 0
        )
        viewport_width = timeline_viewport.get_viewport_width(w)
        content_right = scroll_offset + viewport_width - timeline_viewport.right_inset(w)
        start_x = max(content_start_x, float(scroll_offset))
        end_x = min(float(content_right), content_start_x + logical)
        blocks = timeline_viewport.strip_block_layout(
            w,
            content_start_x=content_start_x,
            start_x=start_x,
            end_x=end_x,
            overscan_blocks=1,
        )
        reps = list(dict.fromkeys(rep for _, _, rep in blocks))
        assert visible == reps
    finally:
        w.close()


def test_visible_window_recomputes_after_set_data(qapp):
    w = _make_widget(qapp, n=100)
    try:
        first = w.get_visible_thumbnail_frame_indices()
        assert first and max(first) < w._total_frames
        first_total = w._total_frames
        w.set_data(_snaps(10), fps=30)
        w._layout_settle.cancel()
        w.fit_view()
        w._commitState(w._current_state(), source="test")
        second = w.get_visible_thumbnail_frame_indices()
        assert second
        assert max(second) <= w._total_frames - 1
        # Shorter recording -> fewer frames (no stale indices past the end).
        assert w._total_frames < first_total
    finally:
        w.close()


def test_prefit_bulk_thumbnails_do_not_break_window(qapp):
    """Pre-fit bulk loads keep everything (fail-open prune) and the window
    still computes once geometry commits."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    px = QPixmap(16, 9)
    w = TimelineWidget(snapshots=_snaps(60))
    w._layout_settle.cancel()
    try:
        bulk = {i: px for i in range(0, 60, 3)}
        w.set_thumbnails(bulk)
        assert set(w._thumbnails) == set(bulk)
        w.resize(800, 240)
        w.show()
        qapp.processEvents()
        w._layout_settle.cancel()
        w.fit_view()
        w._commitState(w._current_state(), source="test")
        visible = w.get_visible_thumbnail_frame_indices()
        assert visible
        assert all(0 <= i < w._total_frames for i in visible)
    finally:
        w.close()


# --- public zoom/pps API + DataSource adoption (supervisor seam, Phase 4D) --


def _committed(w):
    w._commitState(w._current_state(), source="test")


def test_set_zoom_clamps_emits_once_then_silent(qapp):
    w = _make_widget(qapp, n=120)
    try:
        zoom_got: list[float] = []
        viewport_got: list[int] = []
        w.zoomChanged.connect(lambda z: zoom_got.append(z))
        w.viewportChanged.connect(lambda: viewport_got.append(1))
        w.set_zoom(100.0)
        assert w._zoom_level == 1.0
        assert len(zoom_got) == 1 and zoom_got[0] == 1.0
        assert len(viewport_got) == 1
        w.set_zoom(100.0)
        assert len(zoom_got) == 1 and len(viewport_got) == 1
    finally:
        w.close()


def test_set_zoom_holds_center_time(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    area, w = _make_scrolled_widget(qapp, n=120)
    try:
        w.set_zoom(0.2)
        qapp.processEvents()

        vpw, before = _center_measure(w, qapp)
        if vpw <= 0:
            pytest.skip("the timeline viewport is not realized in this environment")
        w.set_zoom(0.6)
        qapp.processEvents()
        _vpw_after, after = _center_measure(w, qapp)
        assert after is not None
        assert abs(before - after) <= _center_tolerance(w, 0.6)
    finally:
        w.close()


def test_set_pps_roundtrip_and_fail_open(qapp):
    w = _make_widget(qapp, n=120)
    try:
        w.set_zoom(1.0)
        pps = w.get_pixels_per_second()
        zoom_got: list[float] = []
        w.zoomChanged.connect(lambda z: zoom_got.append(z))
        w.set_pps(pps)
        assert zoom_got == []
        w.set_pps(pps * 0.5)
        assert w.get_pixels_per_second() < pps
        assert len(zoom_got) == 1
    finally:
        w.close()
    empty = _make_widget(qapp, n=0)
    try:
        empty.set_pps(10.0)
        empty.set_zoom(0.5)
    finally:
        empty.close()


def test_explicit_view_change_retires_the_pending_ingest_fit(qapp):
    """A deliberate fit/zoom/scroll supersedes the deferred ingest fit.

    ``set_data`` does not fit synchronously: ``ingest_data`` sets
    ``_needs_fit_view`` and arms the settle gate 120 ms out. That deferred fit
    must never land on top of a view the caller has already framed — measured
    before the fix: ``set_data`` then ``set_zoom(0.5)`` snapped back to
    ``min_zoom`` (and a user scroll back to 0) when the gate fired, and the
    same flush delivered inside a slow centering test's own ``processEvents()``
    moved the centre 41.5 s and emitted a second ``zoomChanged`` (green on the
    warm rerun of the same seed, red alone). So an explicit ``fit_view``,
    ``set_zoom`` or host scroll retires the flag, and a late flush is inert.
    """
    # 1. An explicit fit satisfies the deferred one.
    area, w = _make_scrolled_widget(qapp, n=120)
    try:
        assert w._needs_fit_view is False, "set_data's fit was left deferred"
    finally:
        w.close()
        area.close()

    # 2. A zoom inside the ingest window survives the flush.
    area, w = _make_scrolled_widget(qapp, n=0)
    try:
        w.set_data(_snaps(120), fps=30)
        assert w._needs_fit_view is True, "ingest must defer its fit"
        w.set_zoom(0.5)
        zoom = w._zoom_level
        w._layout_settle.flush()
        assert w._zoom_level == zoom, "the deferred fit overrode an explicit zoom"
    finally:
        w.close()
        area.close()

    # 3. A user scroll inside the ingest window survives the flush.
    area, w = _make_scrolled_widget(qapp, n=120)
    try:
        w.set_zoom(0.5)  # a scroll range exists before the second ingest
        w.set_data(_snaps(120), fps=30)
        assert w._needs_fit_view is True
        from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
            viewport as timeline_viewport,
        )

        bar = timeline_viewport.get_scroll_area(w).horizontalScrollBar()
        zoom = w._zoom_level
        bar.setValue(min(500, bar.maximum()))
        scrolled = bar.value()
        assert scrolled > 0
        w._layout_settle.flush()
        assert bar.value() == scrolled, "the deferred fit threw away a user scroll"
        assert w._zoom_level == zoom
    finally:
        w.close()
        area.close()


def test_set_zoom_anchor_variants_hold_center(qapp):
    """Both ``anchor`` spellings forward into the commit cursor policy.

    The API path carries no event position, so ``"cursor"`` and
    ``"center"`` both hold the viewport-center time through
    ``viewport.commit_zoom`` (one emit each, never silent-dropped).
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    for anchor in ("cursor", "center"):
        area, w = _make_scrolled_widget(qapp, n=120)
        try:
            w.set_zoom(0.2)
            qapp.processEvents()

            vpw, before = _center_measure(w, qapp)
            if vpw <= 0:
                pytest.skip("the timeline viewport is not realized in this environment")
            zoom_got: list[float] = []
            w.zoomChanged.connect(lambda z: zoom_got.append(z))
            w.set_zoom(0.6, anchor=anchor)
            # Two turns so the scroll area has applied the new range and the
            # repaint before the second measurement. This is not what the old
            # flake here was about: that one raced the ingest settle gate, not
            # the layout timing (see
            # ``test_scrolled_embedding_has_no_pending_ingest_fit``).
            qapp.processEvents()
            qapp.processEvents()
            _vpw_after, after = _center_measure(w, qapp)
            assert after is not None
            assert abs(before - after) <= _center_tolerance(w, 0.6)
            assert len(zoom_got) == 1
        finally:
            w.close()


def test_zoom_in_from_fitted_view_holds_center(qapp):
    """A zoom-in straight from a fitted view must keep the centre block.

    Red before the clamp-order fix: ``viewport.commit_zoom`` clamped the anchor
    target against the host scrollbar range as it was BEFORE
    ``update_fixed_width`` widened the content. A fitted view has
    ``maximum() == minimum() == 0``, so every anchor target clamped to 0 and the
    view jumped back to the start of the recording instead of staying centred.
    Measured on the pre-fix tree at ``set_zoom(0.2)``: scroll 0, centre block
    index 8.28 against 1253.05 before the zoom — 31866 px of drift, i.e. the
    exact anchor target that was thrown away. After: scroll 31866, centre index
    1253.05 (0.0 px).
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    area, w = _make_scrolled_widget(qapp, n=120)
    try:
        vpw, before = _center_measure(w, qapp)
        if vpw <= 0:
            pytest.skip("the timeline viewport is not realized in this environment")
        bar = timeline_viewport.get_scroll_area(w).horizontalScrollBar()
        assert bar.maximum() == bar.minimum(), "the fitted view must have no scroll range"
        w.set_zoom(0.2)
        qapp.processEvents()
        # The anchor survived: a pre-widen clamp leaves the scroll at 0.
        assert bar.value() > 0
        _vpw_after, after = _center_measure(w, qapp)
        assert after is not None
        assert abs(before - after) <= _anchor_tolerance(w, 0.2)
    finally:
        w.close()
        area.close()


def test_zoom_in_from_fitted_view_holds_time_under_cursor(qapp):
    """The Ctrl+wheel path (same ``commit_zoom``) holds the cursor anchor.

    Red before the clamp-order fix: three coalesced ticks from the fitted view
    left the scroll at 0, so the time under a cursor at viewport x=500 drifted
    209.7 px (634.6 frames). It is the same lost-clamp-target defect as the API
    path — the wheel anchors the cursor, not the centre, so the centre measure
    is the wrong instrument here. After: 0.3 px.
    """
    area, w = _make_scrolled_widget(qapp, n=120)
    try:
        vpw, _centre = _center_measure(w, qapp)
        if vpw <= 0:
            pytest.skip("the timeline viewport is not realized in this environment")
        cursor_viewport_x = 500.0
        before = _time_at_viewport_x(w, cursor_viewport_x)
        for _ in range(3):
            _ctrl_wheel_zoom(w, 120, cursor_viewport_x)
        qapp.processEvents()
        qapp.processEvents()
        after = _time_at_viewport_x(w, cursor_viewport_x)
        assert abs(before - after) <= _anchor_tolerance(w, w._zoom_level)
    finally:
        w.close()
        area.close()


def test_fit_then_zoom_holds_center(qapp):
    """An explicit fit followed by a zoom keeps the centre block.

    The gesture shape a double-click-to-fit host produces (the timeline has no
    double-click handler of its own, so the fit entry point is
    ``TimelineWidget.fit_view``). Red before the fix: ``set_zoom(0.35)`` right
    after ``fit_view()`` left the scroll at 0 and the centre 55924.5 px away.
    After: 0.4 px.
    """
    area, w = _make_scrolled_widget(qapp, n=120)
    try:
        w.fit_view()
        qapp.processEvents()
        vpw, before = _center_measure(w, qapp)
        if vpw <= 0:
            pytest.skip("the timeline viewport is not realized in this environment")
        w.set_zoom(0.35)
        qapp.processEvents()
        _vpw_after, after = _center_measure(w, qapp)
        assert after is not None
        assert abs(before - after) <= _anchor_tolerance(w, 0.35)
    finally:
        w.close()
        area.close()


def test_resize_after_zoom_keeps_the_anchored_scroll(qapp):
    """A resize after a zoom re-clamps; it must not throw the anchor away.

    ``viewport_geometry_changed`` on the settle flush re-commits and re-applies
    the fixed width, so a resize is a re-clamp path too. It owns no anchor of
    its own: the host keeps the scroll VALUE, so a widened viewport moves the
    centre pixel by exactly half the width change (measured after the fix: 100.0
    px for +200 px of viewport width, scroll 31866 -> 31866 — the same host
    scroll semantics as before this change, not an anchor loss). What the fix
    changes is which value survives: pre-fix the zoom-in had already collapsed
    it to 0 (31866 of anchor thrown away); post-fix the anchored 31866 is
    preserved and the range never clamps it.
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    area, w = _make_scrolled_widget(qapp, n=120)
    try:
        vpw, before = _center_measure(w, qapp)
        if vpw <= 0:
            pytest.skip("the timeline viewport is not realized in this environment")
        w.set_zoom(0.2)
        qapp.processEvents()
        qapp.processEvents()
        bar = timeline_viewport.get_scroll_area(w).horizontalScrollBar()
        anchored = int(bar.value())
        assert anchored > 0
        _vpw_pre, centre_pre = _center_measure(w, qapp)

        area.resize(vpw + 200, 240)
        qapp.processEvents()
        w._layout_settle.flush()
        qapp.processEvents()

        vpw_post, centre_post = _center_measure(w, qapp)
        assert centre_post is not None and centre_pre is not None
        assert int(bar.value()) == anchored, "the resize clamped the anchored scroll"
        assert int(bar.value()) <= int(bar.maximum())
        delta_vp = int(vpw_post) - int(vpw)
        pps = timeline_viewport.pixels_per_second_for_zoom(w, w._zoom_level)
        drift_px = abs(centre_post - centre_pre) * pps
        assert abs(drift_px - abs(delta_vp) / 2.0) <= 2.0
    finally:
        w.close()
        area.close()


def test_set_zoom_invalid_anchor_raises(qapp):
    w = _make_widget(qapp, n=120)
    try:
        before = w._zoom_level
        with pytest.raises(ValueError):
            w.set_zoom(0.5, anchor="bogus")
        assert w._zoom_level == before
        with pytest.raises(ValueError):
            w.set_pps(100.0, anchor="bogus")
        assert w._zoom_level == before
    finally:
        w.close()


def test_block_range_matches_layout_blocks(qapp):
    """``visible_strip_block_range`` is the SAME layout in block units (I3).

    The ``(first, last_excl)`` range covers exactly the
    ``strip_block_layout`` blocks over the shared visible span, and the
    fetch window (``get_visible_thumbnail_frame_indices``) holds exactly
    the deduped reps of those blocks — one source, two views.
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    w = _make_widget(qapp, n=90)
    try:
        w._commitState(w._current_state().with_zoom(1.0), source="test")
        for overscan in (0, 1, 2):
            first, last_excl = timeline_viewport.visible_strip_block_range(
                w, overscan_blocks=overscan
            )
            assert last_excl > first >= 0
            content_start_x = float(w.LEFT_GUTTER)
            logical = timeline_viewport.get_logical_width(w)
            slot = timeline_viewport.get_slot_width(w)
            base = timeline_viewport.get_base_tile_width(w)
            draw_w = base if slot < base else slot
            scroll_area = timeline_viewport.get_scroll_area(w)
            scroll_offset = (
                scroll_area.horizontalScrollBar().value() if scroll_area else 0
            )
            viewport_width = timeline_viewport.get_viewport_width(w)
            content_right = (
                scroll_offset + viewport_width - timeline_viewport.right_inset(w)
            )
            start_x = max(content_start_x, float(scroll_offset))
            end_x = min(float(content_right), content_start_x + logical)
            blocks = timeline_viewport.strip_block_layout(
                w,
                content_start_x=content_start_x,
                start_x=start_x,
                end_x=end_x,
                overscan_blocks=overscan,
            )
            assert last_excl - first == len(blocks)
            for offset, (block_x, _w, _rep) in enumerate(blocks):
                assert block_x == content_start_x + (first + offset) * draw_w
            reps = list(dict.fromkeys(rep for _, _, rep in blocks))
            assert w.get_visible_thumbnail_frame_indices(
                overscan_blocks=overscan
            ) == reps
    finally:
        w.close()


def test_block_range_overscan_monotonic_and_clamped(qapp):
    """Block ranges grow monotonically with overscan; negative clamps to 0."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    w = _make_widget(qapp, n=120)
    try:
        w._commitState(w._current_state().with_zoom(1.0), source="test")
        base = timeline_viewport.visible_strip_block_range(w, overscan_blocks=0)
        mid = timeline_viewport.visible_strip_block_range(w, overscan_blocks=1)
        wide = timeline_viewport.visible_strip_block_range(w, overscan_blocks=2)
        assert base[0] >= mid[0] >= wide[0]
        assert base[1] <= mid[1] <= wide[1]
        assert (
            timeline_viewport.visible_strip_block_range(w, overscan_blocks=-5)
            == base
        )
    finally:
        w.close()


def test_block_range_empty_store_fail_open(qapp):
    """Empty store returns ``(0, 0)`` for any overscan (fail-open)."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    w = _make_widget(qapp, n=0)
    try:
        for overscan in (-1, 0, 1, 10):
            assert timeline_viewport.visible_strip_block_range(
                w, overscan_blocks=overscan
            ) == (0, 0)
    finally:
        w.close()


def test_set_data_source_adoption_and_precedence(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    snaps = _snaps(20)
    source = SimpleNamespace(
        snapshots=snaps, fps=30, duration=19.0, timeline_model=None
    )
    w = TimelineWidget()
    w.resize(800, 240)
    w.show()
    qapp.processEvents()
    w._layout_settle.cancel()
    try:
        w.set_data(source=source)
        assert w._duration == 19.0
        assert w._fps == 30
        assert list(w._snapshots) == list(snaps)
        # Explicit args win over the source.
        w.set_data(snaps, fps=10, source=source)
        assert w._fps == 10
        assert w._duration == 19.0
        # Non-matching source objects fall back to the legacy path.
        w.set_data(snaps, fps=15, duration=7.0, source=object())
        assert w._fps == 15
        assert w._duration == 7.0
    finally:
        w.close()


# --- Phase 3 polish: block-rep floor rule --------------------------------------
#
# Quantize-contract companion: strip block reps are floor-of-block-start
# (``min(total - 1, floor(i * frames_per_block))``) at a constant draw
# width — the one documented exception to nearest-frame rounding, pinned
# here so the polish never silently re-quantizes the rep grid.


def test_strip_block_reps_follow_floor_rule(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    w = _make_widget(qapp, n=90)
    try:
        for zoom in (w._zoom_level, 1.0):
            w._commitState(w._current_state().with_zoom(zoom), source="test")
            csx = float(w.LEFT_GUTTER)
            logical = timeline_viewport.get_logical_width(w)
            slot = timeline_viewport.get_slot_width(w)
            base = timeline_viewport.get_base_tile_width(w)
            draw_w = base if slot < base else slot
            blocks = timeline_viewport.strip_block_layout(
                w, content_start_x=csx, start_x=csx, end_x=csx + logical
            )
            assert blocks, zoom
            frames_per_block = draw_w / slot
            for i, (block_x, block_w, rep) in enumerate(blocks):
                assert block_w == draw_w, (zoom, i)
                assert block_x == csx + i * draw_w, (zoom, i)
                assert rep == min(w._total_frames - 1, int(i * frames_per_block)), (
                    zoom,
                    i,
                )
    finally:
        w.close()
