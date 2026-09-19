"""Phase 2B gutter unification: drag clamp, gutter window, band, hover.

- Drag clamps to [MIN, MAX] and travels through the frozen
  ``TimelineViewportState`` shape (``with_left_gutter``) while staying on
  the existing silent refresh path (CUTOVER-C converts it to a
  ``_commitState`` emit later) — zoom untouched, no zoom/viewport emits.
- ``viewport.visible_row_gutter_window`` mirrors
  ``layout.visible_row_window`` (start/end/y_at_start identical) with one
  ``(top, bottom)`` gutter pair per painted row.
- ``viewport.gutter_band_rect`` covers the chevron + wash/edge gradients +
  the 1px separator (same geometry as
  ``widget.gutter_band_rect_for_scroll``).
- ``viewport.hover_points_for_rows`` is damage-independent: points outside
  a narrow damage band still yield hit-rects + tooltips.
- ``viewport.damage_pad`` resolves the single ``layout.DAMAGE_PAD``
  (12.0 fallback until wave A lands it — never two live pads).
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QScrollArea

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    layout as timeline_layout,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
    TimelineWidget,
    gutter_band_rect_for_scroll,
)

_DURATION = 100.0


def _snaps():
    return [SimpleNamespace(timestamp=0.0), SimpleNamespace(timestamp=_DURATION)]


def _keyframe(timestamp: float, value: float):
    return SimpleNamespace(
        timestamp=float(timestamp), value=float(value), interpolation="linear"
    )


def _channel(label, keyframes, kind="scalar"):
    return SimpleNamespace(
        kind=kind, label=label, keyframes=list(keyframes), interpolate_values=True
    )


def _track(track_id, label, channels, kind="scalar"):
    return SimpleNamespace(
        id=track_id, kind=kind, label=label, channels=dict(channels)
    )


def _group(label, tracks):
    return SimpleNamespace(label=label, tracks=dict(tracks))


def _press(x: float, y: float = 100.0) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(float(x), float(y)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _move(x: float, y: float = 100.0) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(float(x), float(y)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release(x: float, y: float = 100.0) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(float(x), float(y)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_bare(qapp, **kwargs) -> TimelineWidget:
    widget = TimelineWidget(snapshots=_snaps(), **kwargs)
    widget.resize(800, 240)
    widget.show()
    qapp.processEvents()
    qapp.processEvents()
    widget._layout_settle.cancel()
    widget.fit_view()
    qapp.processEvents()
    return widget


def _drag(widget, target_x: float) -> None:
    widget.mousePressEvent(_press(float(widget.LEFT_GUTTER)))
    assert widget._is_resizing_gutter
    widget.mouseMoveEvent(_move(float(target_x)))
    widget.mouseReleaseEvent(_release(float(target_x)))
    assert not widget._is_resizing_gutter


# --- drag clamp -------------------------------------------------------------


def test_gutter_drag_clamps_to_max(qapp):
    widget = _make_bare(qapp)
    _drag(widget, float(widget.LEFT_GUTTER) + 10_000.0)
    assert widget.LEFT_GUTTER == widget.MAX_LEFT_GUTTER
    widget.close()


def test_gutter_drag_clamps_to_min(qapp):
    widget = _make_bare(qapp)
    _drag(widget, -10_000.0)
    assert widget.LEFT_GUTTER == widget.MIN_LEFT_GUTTER
    widget.close()


def test_gutter_clamp_bounds_are_140_320(qapp):
    widget = _make_bare(qapp)
    assert int(widget.MIN_LEFT_GUTTER) == 140
    assert int(widget.MAX_LEFT_GUTTER) == 320
    assert timeline_viewport.clamp_gutter_width(widget, 1e9) == widget.MAX_LEFT_GUTTER
    assert timeline_viewport.clamp_gutter_width(widget, -1e9) == widget.MIN_LEFT_GUTTER
    assert timeline_viewport.clamp_gutter_width(widget, 200.0) == 200.0
    widget.close()


def test_gutter_drag_keeps_state_shape_and_zoom_quiet(qapp):
    """Drag travels the frozen state shape, emits nothing, keeps pps."""
    widget = _make_bare(qapp)
    zoom_got: list[float] = []
    viewport_got: list[int] = []
    widget.zoomChanged.connect(lambda z: zoom_got.append(z))
    widget.viewportChanged.connect(lambda: viewport_got.append(1))
    zoom_before = widget._zoom_level
    pps_before = widget.get_pixels_per_second()
    widget.mousePressEvent(_press(float(widget.LEFT_GUTTER)))
    mid = (float(widget.MIN_LEFT_GUTTER) + float(widget.MAX_LEFT_GUTTER)) / 2.0
    widget.mouseMoveEvent(_move(mid))
    nxt = widget._current_state()
    assert nxt.left_gutter == int(widget.LEFT_GUTTER)
    assert nxt.left_gutter == int(mid)
    widget.mouseReleaseEvent(_release(mid))
    assert widget._zoom_level == zoom_before
    assert widget.get_pixels_per_second() == pps_before
    assert zoom_got == [] and viewport_got == []
    widget.close()


# --- gutter window ----------------------------------------------------------


def _make_rows_widget(qtbot):
    early = _track(
        "early", "Early", {"v": _channel("v", [_keyframe(t, float(t % 2)) for t in range(6)])}
    )
    full = _track(
        "full",
        "Full",
        {"v": _channel("v", [_keyframe(t, float((t // 5) % 2)) for t in range(0, 101, 5)])},
    )
    model = SimpleNamespace(
        groups={"g1": _group("G1", {"early": early}), "g2": _group("G2", {"full": full})},
        sample_timestamps=[0.0, _DURATION],
        get_duration=lambda: float(_DURATION),
    )
    tl = TimelineWidget()
    tl._fps = 10
    tl._duration = _DURATION
    tl._total_frames = 1001
    tl._timeline_model = model
    tl._rebuild_row_layout()
    qtbot.addWidget(tl)
    tl.resize(800, 400)
    tl.show()
    qtbot.waitExposed(tl)
    tl.fit_view()
    qtbot.wait(10)
    return tl


def test_gutter_window_mirrors_visible_row_window(qtbot):
    tl = _make_rows_widget(qtbot)
    _, rows_bottom = timeline_viewport.content_viewport_bounds(tl)
    for scroll in (0, 40, 200):
        rows_top = tl.STRIP_HEIGHT - scroll
        start, end, y0 = timeline_layout.visible_row_window(tl, rows_top, rows_bottom)
        win = timeline_viewport.visible_row_gutter_window(tl, rows_top, rows_bottom)
        assert (win.start, win.end, win.y_at_start) == (start, end, y0)
        assert len(win.gutter_rects) == end - start
        assert win.gutter_x == 0.0
        assert win.gutter_width == float(tl.LEFT_GUTTER)
        # Rects tile the painted rows contiguously from y_at_start.
        y = y0
        for idx, (top, bottom) in enumerate(win.gutter_rects):
            assert top == y
            assert bottom > top
            kind = tl._row_layout[start + idx][0]
            if kind == "group":
                assert bottom - top == tl.GROUP_HEADER_HEIGHT
            elif kind == "track_single":
                assert bottom - top == tl.TRACK_ROW_HEIGHT
            else:
                assert bottom - top == tl.CHANNEL_ROW_HEIGHT
            y = bottom


def test_gutter_window_carries_scroll_offset(qtbot):
    tl = _make_rows_widget(qtbot)
    _, rows_bottom = timeline_viewport.content_viewport_bounds(tl)
    rows_top = tl.STRIP_HEIGHT
    win = timeline_viewport.visible_row_gutter_window(
        tl, rows_top, rows_bottom, scroll_offset=137.0
    )
    assert win.gutter_x == 137.0
    assert win.gutter_width == float(tl.LEFT_GUTTER)


# --- band coverage ----------------------------------------------------------


def test_gutter_band_matches_widget_helper_and_covers_chevron(qapp):
    widget = _make_bare(qapp)
    area = QScrollArea()
    area.setWidget(widget)
    area.resize(800, 240)
    area.show()
    qapp.processEvents()
    for scroll in (0, 137):
        mine = timeline_viewport.gutter_band_rect(widget, scroll)
        theirs = gutter_band_rect_for_scroll(widget, scroll)
        assert mine == theirs
        assert mine.x() == scroll
        assert mine.width() == int(widget.LEFT_GUTTER) + 2
        # Chevron (gx+8 .. gx+26) and the 1px separator at gx+LEFT_GUTTER
        # both sit inside the band; wash/edge gradients span the gutter.
        header = widget._group_header_rect(scroll, widget.STRIP_HEIGHT)
        chevron = widget._group_chevron_rect(header)
        assert mine.contains(int(chevron.left()), int(chevron.center().y()))
        assert mine.contains(int(chevron.right()), int(chevron.center().y()))
        assert mine.contains(int(scroll + widget.LEFT_GUTTER), 10)
    widget.close()
    area.close()


# --- hover helper (damage-independent) --------------------------------------


def test_hover_points_for_rows_ignores_damage_cull(qtbot):
    tl = _make_rows_widget(qtbot)
    item = next(
        i for i in tl._row_layout if i[0] == "track_single" and i[2].id == "full"
    )
    _kind, group, track, channel = item
    duration = timeline_layout.content_duration(tl)
    logical = timeline_viewport.get_logical_width(tl)
    # Points at the far right edge: a narrow left damage band would cull
    # every one of them in the render segment loops.
    late = [kf for kf in channel.keyframes if kf.timestamp >= 90.0]
    assert late, "need late keyframes for the off-damage probe"
    points = [
        (timeline_layout.time_to_x(tl, kf.timestamp, duration, logical), 50.0, kf)
        for kf in late
    ]
    assert all(x > 700.0 for x, _, _ in points)
    got = timeline_viewport.hover_points_for_rows(tl, group, track, channel, points)
    assert len(got) == len(points)
    for (x, y, _kf), (rect, text) in zip(points, got):
        assert rect.contains(QPointF(x, y))
        assert rect.width() == 12.0 and rect.height() == 12.0
        assert isinstance(text, str) and text


def test_hover_points_empty_in_empty_out(qapp):
    widget = _make_bare(qapp)
    assert (
        timeline_viewport.hover_points_for_rows(widget, None, None, None, []) == []
    )
    widget.close()


# --- single pad -------------------------------------------------------------


def test_damage_pad_is_single_source():
    assert timeline_viewport.damage_pad() == 12.0
    assert timeline_viewport.damage_pad() == float(
        getattr(timeline_layout, "DAMAGE_PAD", 12.0)
    )
