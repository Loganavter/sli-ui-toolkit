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
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import TimelineWidget

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
