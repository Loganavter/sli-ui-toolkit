"""Z1/Z2/Z3: pps zoom model, cursor anchor, coalesced Ctrl+wheel zoom.

- Z1: px/sec is the single zoom scalar (``pps = zoom * base_pps``);
  cursor anchor keeps the time under the cursor fixed across zoom;
  per-tick factor is 1.25; ``fit_view`` semantics unchanged.
- Z2: wheel ticks accumulate inside one frame window; a 10-tick burst
  commits exactly once (1 ``_commitState`` with emits, 1
  ``updateGeometry``+``update``, <=2 paints); the scrollbar is set
  synchronously from the anchor math. No-change ticks stay silent.
- Z3: layout-only zoom — the ``zoomChanged`` / ``viewportChanged`` /
  ``viewportChangedState`` emit contract is unchanged.

No timing asserts: singleShot(0) windows are drained with
``processEvents`` and only offscreen counters are asserted.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QScrollArea

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.state import (
    TimelineViewportState,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
    TimelineWidget,
    gutter_band_rect_for_scroll,
)

DURATION = 100.0


class ProbeTimeline(TimelineWidget):
    """TimelineWidget counting commits / geometry / paints (Z2 asserts)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commit_calls = 0
        self.commit_emitted = 0
        self.commit_sources: list[str] = []
        self.geometry_calls = 0
        self.paint_calls = 0

    def _commitState(self, nxt, source=""):
        self.commit_calls += 1
        self.commit_sources.append(source)
        emitted = super()._commitState(nxt, source=source)
        if emitted:
            self.commit_emitted += 1
        return emitted

    def updateGeometry(self):
        self.geometry_calls += 1
        super().updateGeometry()

    def paintEvent(self, event):
        self.paint_calls += 1
        super().paintEvent(event)


def _snapshots():
    return [SimpleNamespace(timestamp=0.0), SimpleNamespace(timestamp=DURATION)]


def _settle(qapp, widget) -> None:
    """Drain pending fit_view/settle singles and cancel the settle gate."""
    qapp.processEvents()
    qapp.processEvents()
    widget._layout_settle.cancel()
    widget.fit_view()
    qapp.processEvents()


def _make_bare(qapp) -> ProbeTimeline:
    widget = ProbeTimeline(snapshots=_snapshots())
    widget.resize(800, 240)
    widget.show()
    _settle(qapp, widget)
    return widget


def _make_hosted(qapp) -> tuple[ProbeTimeline, QScrollArea]:
    widget = ProbeTimeline(snapshots=_snapshots())
    area = QScrollArea()
    area.setWidget(widget)
    area.resize(800, 240)
    area.show()
    _settle(qapp, widget)
    return widget, area


def _ctrl_wheel(widget, delta_y: int, x: float = 400.0) -> None:
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


def _reset_probe(widget) -> None:
    widget.commit_calls = 0
    widget.commit_emitted = 0
    widget.commit_sources.clear()
    widget.geometry_calls = 0
    widget.paint_calls = 0


# --- Z1: pps model ---------------------------------------------------------


def test_pps_is_zoom_times_base_pps(qapp):
    widget = _make_bare(qapp)
    base = timeline_viewport.get_base_pixels_per_second(widget)
    assert base > 0
    for zoom in (widget._zoom_level, 0.05, 0.25, 1.0):
        assert timeline_viewport.pixels_per_second_for_zoom(widget, zoom) == pytest.approx(zoom * base)
    assert widget.get_pixels_per_second() == pytest.approx(
        timeline_viewport.pixels_per_second_for_zoom(widget, widget._zoom_level)
    )


def test_wheel_factor_is_1_25(qapp):
    assert timeline_viewport.WHEEL_ZOOM_FACTOR == 1.25
    widget = _make_bare(qapp)
    _reset_probe(widget)  # drop setup commits (show/resize) before measuring
    got: list[float] = []
    widget.zoomChanged.connect(lambda z: got.append(z))
    start = widget._zoom_level
    _ctrl_wheel(widget, 120)
    qapp.processEvents()
    expected = start * 1.25
    assert got == [pytest.approx(expected)]
    assert widget._zoom_level == pytest.approx(expected)
    assert widget.commit_sources == ["wheelZoom"]


def test_fit_view_semantics_unchanged(qapp):
    widget = _make_bare(qapp)
    widget.fit_view()
    assert widget._zoom_level == pytest.approx(timeline_viewport.calculate_min_zoom(widget))
    assert widget._last_min_zoom == pytest.approx(widget._zoom_level)


def test_wheel_never_sets_needs_fit_view(qapp):
    widget, _area = _make_hosted(qapp)
    widget._needs_fit_view = False  # simulate settled; wheel must not arm it
    _ctrl_wheel(widget, 120)
    qapp.processEvents()
    assert widget._needs_fit_view is False


# --- Z1: cursor anchor ------------------------------------------------------


def test_cursor_anchor_roundtrip_across_x8(qapp):
    """Pure anchor math: scroll keeps cursor time fixed over an x8 zoom range."""
    widget = _make_bare(qapp)
    widget.fit_view()
    z0 = widget._zoom_level
    assert timeline_viewport.anchor_scroll_for_zoom(widget, 10_000.0, 0.0, 100.0) == 0
    cursor_viewport_x = 400.0
    scroll = 0
    zoom = z0
    while zoom < 8 * z0:
        old_pps = timeline_viewport.pixels_per_second_for_zoom(widget, zoom)
        cursor_time = timeline_viewport.cursor_time_at_x(widget, scroll + cursor_viewport_x)
        zoom = timeline_viewport.clamp_zoom(widget, zoom * 1.25)
        new_pps = timeline_viewport.pixels_per_second_for_zoom(widget, zoom)
        target = timeline_viewport.anchor_scroll_for_zoom(
            widget, cursor_viewport_x, cursor_time, new_pps
        )
        back = (target + cursor_viewport_x - widget.LEFT_GUTTER) / new_pps
        assert abs(back - cursor_time) <= 1.0 / new_pps + 1e-9
        scroll = target
    assert zoom >= 8 * z0


def test_wheel_keeps_time_under_cursor(qapp):
    """Integration: a wheel step preserves time-under-cursor via the scrollbar."""
    widget, area = _make_hosted(qapp)
    bar = area.horizontalScrollBar()
    for _ in range(3):  # warm-up: zoom in so scrolling is live
        _ctrl_wheel(widget, 120, x=500.0)
    qapp.processEvents()
    qapp.processEvents()
    scroll_old = int(bar.value())
    cursor_viewport_x = 500.0 - scroll_old
    t0 = timeline_viewport.cursor_time_at_x(widget, 500.0)
    for _ in range(2):
        _ctrl_wheel(widget, 120, x=500.0)
    qapp.processEvents()
    qapp.processEvents()
    scroll_new = int(bar.value())
    t1 = timeline_viewport.cursor_time_at_x(widget, cursor_viewport_x + scroll_new)
    new_pps = timeline_viewport.pixels_per_second_for_zoom(widget, widget._zoom_level)
    assert abs(t1 - t0) <= 1.0 / new_pps + 1e-6


# --- Z2: coalescing ---------------------------------------------------------


def test_ten_ticks_coalesce_into_one_commit(qapp):
    widget, area = _make_hosted(qapp)
    bar = area.horizontalScrollBar()
    _ctrl_wheel(widget, 120, x=400.0)  # warm-up: scrollbar present, layout settled
    qapp.processEvents()
    qapp.processEvents()
    zoom_got: list[float] = []
    viewport_got: list[int] = []
    state_got: list[object] = []
    widget.zoomChanged.connect(lambda z: zoom_got.append(z))
    widget.viewportChanged.connect(lambda: viewport_got.append(1))
    widget.viewportChangedState.connect(lambda s: state_got.append(s))
    _reset_probe(widget)
    for _ in range(10):
        _ctrl_wheel(widget, 120, x=400.0)
    assert widget._wheel_flush_scheduled  # one window, not one flush per tick
    qapp.processEvents()
    qapp.processEvents()
    assert widget.commit_calls == 1
    assert widget.commit_emitted == 1
    assert widget.commit_sources == ["wheelZoomCoalesced"]
    assert len(zoom_got) == 1
    assert len(viewport_got) == 1
    assert len(state_got) == 1
    assert isinstance(state_got[0], TimelineViewportState)
    assert widget.geometry_calls == 1
    assert widget.paint_calls <= 2
    assert int(bar.value()) == widget._state.scroll_x  # set synchronously
    assert widget._wheel_pending_ticks == 0
    assert not widget._wheel_flush_scheduled


def test_no_change_ticks_stay_silent(qapp):
    widget, _area = _make_hosted(qapp)  # fit_view -> already at min zoom
    zoom_got: list[float] = []
    viewport_got: list[int] = []
    state_got: list[object] = []
    widget.zoomChanged.connect(lambda z: zoom_got.append(z))
    widget.viewportChanged.connect(lambda: viewport_got.append(1))
    widget.viewportChangedState.connect(lambda s: state_got.append(s))
    _reset_probe(widget)
    qapp.processEvents()
    _reset_probe(widget)  # clear stale setup paints delivered above
    for _ in range(3):
        _ctrl_wheel(widget, -120, x=400.0)
    qapp.processEvents()
    qapp.processEvents()
    assert widget.commit_calls == 0
    assert widget.commit_emitted == 0
    assert zoom_got == [] and viewport_got == [] and state_got == []
    # No paint assert: offscreen delivers stray expose repaints with zero
    # wheel input (verified with a no-tick baseline), so paints cannot
    # prove wheel silence — the commit/emit counters above do.
    assert not widget._wheel_flush_scheduled


# --- Gutter sync correction -------------------------------------------------
#
# The sticky gutter is painted in content coords at gx=scroll_offset while
# every horizontal setValue moves the content widget window synchronously
# (Qt scrollContentsBy) and all correction paints are async update() — ~1
# frame of displaced gutter per step. The fix adds a synchronous band
# repaint after the programmatic setValue plus a band union in the
# signals-live scroll path. No timing asserts: synchronicity is proven by
# calling _flush_wheel_zoom directly (no processEvents) and observing the
# paint before return.


def test_gutter_band_rect_geometry(qapp):
    widget, area = _make_hosted(qapp)
    bar = area.horizontalScrollBar()
    scroll = int(bar.value())
    rect = gutter_band_rect_for_scroll(widget, scroll)
    assert rect.x() == scroll
    assert rect.y() == 0
    assert rect.width() == int(widget.LEFT_GUTTER) + 2
    assert rect.height() == max(
        0, int(widget.height() - timeline_viewport.footer_height(widget))
    )


def test_flush_wheel_zoom_repaints_gutter_band_synchronously(qapp):
    """One direct _flush_wheel_zoom call: 1 commit + 1 sync band repaint."""
    widget, area = _make_hosted(qapp)
    bar = area.horizontalScrollBar()
    _ctrl_wheel(widget, 120, x=400.0)  # warm-up: scrollbar live, layout settled
    qapp.processEvents()
    qapp.processEvents()
    _reset_probe(widget)
    qapp.processEvents()
    _reset_probe(widget)  # clear stale setup paints delivered above

    repaint_rects: list = []
    orig_repaint = widget.repaint

    def _spy_repaint(*args, **kwargs):
        repaint_rects.append(args[0] if args else None)
        return orig_repaint(*args, **kwargs)

    widget.repaint = _spy_repaint  # type: ignore[method-assign]
    try:
        # Prime one coalesced window and flush synchronously — no event
        # loop: any paint observed afterwards happened before return.
        widget._wheel_pending_y = 120.0
        widget._wheel_pending_x = 400.0
        widget._wheel_pending_ticks = 1
        widget._wheel_flush_scheduled = True
        paints_before = widget.paint_calls
        widget._flush_wheel_zoom()
    finally:
        widget.repaint = orig_repaint  # type: ignore[method-assign]

    # Coalesced budget unchanged: still exactly one commit per window.
    assert widget.commit_calls == 1
    assert widget.commit_sources == ["wheelZoom"]
    # Synchronous: the band repaint ran inside the flush call, so the
    # paint it triggers is already counted with no processEvents.
    assert len(repaint_rects) == 1
    expected = gutter_band_rect_for_scroll(widget, int(bar.value()))
    assert repaint_rects[0] == expected
    assert widget.paint_calls > paints_before


def test_coalesced_burst_keeps_one_commit_plus_one_sync_repaint(qapp):
    """10-tick burst: still 1 _commitState, plus exactly 1 sync repaint."""
    widget, area = _make_hosted(qapp)
    bar = area.horizontalScrollBar()
    _ctrl_wheel(widget, 120, x=400.0)  # warm-up: scrollbar present, layout settled
    qapp.processEvents()
    qapp.processEvents()
    _reset_probe(widget)
    qapp.processEvents()
    _reset_probe(widget)  # clear stale setup paints delivered above

    repaint_rects: list = []
    orig_repaint = widget.repaint

    def _spy_repaint(*args, **kwargs):
        repaint_rects.append(args[0] if args else None)
        return orig_repaint(*args, **kwargs)

    widget.repaint = _spy_repaint  # type: ignore[method-assign]
    try:
        for _ in range(10):
            _ctrl_wheel(widget, 120, x=400.0)
        assert widget._wheel_flush_scheduled
        # Drain the singleShot(0) window; the flush (commit + sync band
        # repaint) runs inside processEvents.
        qapp.processEvents()
        qapp.processEvents()
    finally:
        widget.repaint = orig_repaint  # type: ignore[method-assign]

    assert widget.commit_calls == 1
    assert widget.commit_sources == ["wheelZoomCoalesced"]
    assert len(repaint_rects) == 1
    assert repaint_rects[0] == gutter_band_rect_for_scroll(widget, int(bar.value()))
    assert widget._wheel_pending_ticks == 0
    assert not widget._wheel_flush_scheduled


def test_host_scroll_unions_gutter_band_synchronously(qapp):
    """Signals-live setValue: gutter band damage registered before return."""
    widget, area = _make_hosted(qapp)
    bar = area.horizontalScrollBar()
    for _ in range(3):  # warm-up: zoom in so the scrollbar range is live
        _ctrl_wheel(widget, 120, x=500.0)
    qapp.processEvents()
    qapp.processEvents()
    assert bar.maximum() > bar.minimum()

    update_rects: list = []
    orig_update = widget.update

    def _spy_update(*args, **kwargs):
        update_rects.append(args[0] if args else None)
        return orig_update(*args, **kwargs)

    widget.update = _spy_update  # type: ignore[method-assign]
    try:
        target = min(int(bar.maximum()), int(bar.value()) + 50)
        if target == int(bar.value()):
            target = max(int(bar.minimum()), int(bar.value()) - 50)
        assert target != int(bar.value())
        bar.setValue(target)  # signals live: slot runs synchronously
    finally:
        widget.update = orig_update  # type: ignore[method-assign]

    band = gutter_band_rect_for_scroll(widget, int(bar.value()))
    assert any(r == band for r in update_rects if r is not None)


def test_gutter_drag_leaves_coalesced_zoom_accounting_quiet(qapp):
    """Gutter drag commits via _commitState (CUTOVER-C): exactly one
    viewport-family emit, zero zoomChanged, zoom scalar untouched.

    The drag travels the frozen ``TimelineViewportState`` shape via
    ``with_left_gutter`` — so the Z2 zoom counters stay quiet while the
    viewport counters record the single geometry commit.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    widget, _area = _make_hosted(qapp)
    _ctrl_wheel(widget, 120, x=400.0)  # warm-up: scrollbar live, layout settled
    qapp.processEvents()
    qapp.processEvents()
    zoom_before = widget._zoom_level
    zoom_got: list[float] = []
    viewport_got: list[int] = []
    widget.zoomChanged.connect(lambda z: zoom_got.append(z))
    widget.viewportChanged.connect(lambda: viewport_got.append(1))
    _reset_probe(widget)
    qapp.processEvents()
    _reset_probe(widget)  # clear stale setup paints delivered above

    scroll_now = float(_area.horizontalScrollBar().value())
    gutter_x = scroll_now + float(widget.LEFT_GUTTER)
    widget.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(gutter_x, 100.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert widget._is_resizing_gutter
    mid = (float(widget.MIN_LEFT_GUTTER) + float(widget.MAX_LEFT_GUTTER)) / 2.0
    widget.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(scroll_now + mid, 100.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert widget.LEFT_GUTTER == mid
    widget.mouseReleaseEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(scroll_now + mid, 100.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qapp.processEvents()

    assert widget.commit_calls == 1
    assert widget.commit_sources == ["gutterDrag"]
    assert widget.commit_emitted == 1
    assert zoom_got == [] and len(viewport_got) == 1
    assert widget._zoom_level == zoom_before
