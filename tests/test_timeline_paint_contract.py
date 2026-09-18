"""Phase A paint-contract regression tests for TimelineWidget.

Contract under test (see ``render.paint_timeline`` docstring):

1. The paint path performs NO geometry mutation: no scrollbar sync
   (``viewport.update_vertical_scrollbar``), no ``setGeometry`` /
   ``setVisible`` on the scrollbar, no ``setFixedWidth`` on the widget.
   Scrollbar sync lives in the resize/settle/scroll paths (``widget.py``).
2. Damage culling: a narrow ``event.rect()`` computes a subset of the
   segment work of a full repaint (per-row horizontal cull via
   ``layout.row_time_x_range``).
3. Row-window virtualization: ``layout.visible_row_window`` returns exactly
   the rows intersecting the viewport (checked against brute force).
4. Public surface unchanged: signals and host-facing methods still exist
   with compatible signatures.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPaintEvent

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    layout as timeline_layout,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    render as timeline_render,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.widgets import TimelineWidget

_DURATION = 100.0


def _keyframe(timestamp: float, value: float):
    return SimpleNamespace(
        timestamp=float(timestamp), value=float(value), interpolation="linear"
    )


def _channel(label: str, keyframes, kind: str = "scalar"):
    return SimpleNamespace(
        kind=kind,
        label=label,
        keyframes=list(keyframes),
        interpolate_values=True,
    )


def _track(track_id: str, label: str, channels, kind: str = "scalar"):
    return SimpleNamespace(
        id=track_id, kind=kind, label=label, channels=dict(channels)
    )


def _group(label: str, tracks):
    return SimpleNamespace(label=label, tracks=dict(tracks))


def _model(groups, duration: float = _DURATION):
    return SimpleNamespace(
        groups=dict(groups),
        sample_timestamps=[0.0, float(duration)],
        get_duration=lambda: float(duration),
    )


def _make_widget(qtbot, model=None):
    """TimelineWidget with two single-channel scalar tracks.

    Track ``early`` only has keyframes in [0, 5]s; track ``full`` spans the
    whole duration — so a narrow late damage rect culls ``early`` but not
    ``full``.
    """
    early = _track(
        "early",
        "Early",
        {"v": _channel("v", [_keyframe(t, float(t % 2)) for t in range(6)])},
    )
    full = _track(
        "full",
        "Full",
        {
            "v": _channel(
                "v",
                [_keyframe(t, float((t // 5) % 2)) for t in range(0, 101, 5)],
            )
        },
    )
    own_model = model or _model(
        {
            "g1": _group("G1", {"early": early}),
            "g2": _group("G2", {"full": full}),
        }
    )
    tl = TimelineWidget()
    tl._fps = 10
    tl._duration = _DURATION
    tl._total_frames = 1001
    tl._timeline_model = own_model
    tl._rebuild_row_layout()
    if model is None:
        assert len(tl._row_layout) == 4, tl._row_layout
    qtbot.addWidget(tl)
    tl.resize(800, 400)
    tl.show()
    qtbot.waitExposed(tl)
    tl.fit_view()
    qtbot.wait(10)
    return tl


def _paint(tl, rect: QRect):
    tl.paintEvent(QPaintEvent(rect))


def test_paint_does_not_sync_scrollbar(qtbot, monkeypatch):
    """Paint must never reach the scrollbar-sync path (used to be called
    directly from ``paint_timeline``)."""
    tl = _make_widget(qtbot)

    def _forbidden(_widget):
        raise AssertionError("paint path called update_vertical_scrollbar")

    monkeypatch.setattr(
        timeline_viewport, "update_vertical_scrollbar", _forbidden
    )
    _paint(tl, QRect(0, 0, tl.width(), tl.height()))
    _paint(tl, QRect(700, 0, 60, tl.height()))


def test_paint_performs_no_geometry_mutation(qtbot):
    """Spies on setGeometry/setVisible/setFixedWidth stay silent during
    paint (installed after show so setup noise is excluded)."""
    tl = _make_widget(qtbot)
    calls: list[tuple] = []

    scrollbar = tl._v_scrollbar
    orig_set_geometry = scrollbar.setGeometry
    orig_set_visible = scrollbar.setVisible
    orig_set_fixed_width = TimelineWidget.setFixedWidth

    def _spy_geometry(*args):
        calls.append(("setGeometry", args))
        return orig_set_geometry(*args)

    def _spy_visible(*args):
        calls.append(("setVisible", args))
        return orig_set_visible(*args)

    def _spy_fixed_width(*args):
        calls.append(("setFixedWidth", args))
        return orig_set_fixed_width(*args)

    scrollbar.setGeometry = _spy_geometry  # type: ignore[method-assign]
    scrollbar.setVisible = _spy_visible  # type: ignore[method-assign]
    TimelineWidget.setFixedWidth = _spy_fixed_width  # type: ignore[method-assign]
    try:
        _paint(tl, QRect(0, 0, tl.width(), tl.height()))
        _paint(tl, QRect(700, 0, 60, tl.height()))
    finally:
        scrollbar.setGeometry = orig_set_geometry  # type: ignore[method-assign]
        scrollbar.setVisible = orig_set_visible  # type: ignore[method-assign]
        TimelineWidget.setFixedWidth = orig_set_fixed_width  # type: ignore[method-assign]
    assert calls == [], calls


def test_narrow_damage_paints_segment_subset(qtbot, monkeypatch):
    """A narrow late damage rect must skip the early row's segment work."""
    tl = _make_widget(qtbot)
    seen: list[str] = []
    original = timeline_render._draw_keyframe_segments

    def _counting(widget, painter, **kwargs):
        seen.append(kwargs["track"].id)
        return original(widget, painter, **kwargs)

    monkeypatch.setattr(
        timeline_render, "_draw_keyframe_segments", _counting
    )

    _paint(tl, QRect(0, 0, tl.width(), tl.height()))
    full_calls = list(seen)
    assert sorted(full_calls) == ["early", "full"], full_calls

    seen.clear()
    # Late damage: x=700..760 maps to t≈84..94s at fit zoom — the ``early``
    # row (keyframes in [0, 5]s) must be culled, ``full`` must still paint.
    _paint(tl, QRect(700, 0, 60, tl.height()))
    assert seen == ["full"], seen


def test_visible_row_window_matches_brute_force(qtbot):
    """``visible_row_window`` must agree with a brute-force scan for a tall
    layout under several scroll positions."""
    tracks = {}
    for i in range(30):
        tracks[f"t{i}"] = _track(
            f"t{i}",
            f"T{i}",
            {"v": _channel("v", [_keyframe(0, 0.0), _keyframe(10, 1.0)])},
        )
    groups = {f"g{i}": _group(f"G{i}", {f"t{i}": tracks[f"t{i}"]}) for i in range(10)}
    tl = _make_widget(qtbot, model=_model(groups))
    n = len(tl._row_layout)
    assert n >= 20, n

    def _brute(rows_top: float, rows_bottom: float):
        y = rows_top
        start = end = None
        for idx, item in enumerate(tl._row_layout):
            kind = item[0]
            if kind == "group":
                h = tl.GROUP_HEADER_HEIGHT
            elif kind == "track_single":
                h = tl.TRACK_ROW_HEIGHT
            else:
                h = tl.CHANNEL_ROW_HEIGHT
            bottom = y + h
            if bottom > 0 and start is None:
                start = idx
            if y >= rows_bottom and end is None:
                end = idx
                break
            y = bottom
        if start is None:
            # Every row sits above the viewport — empty window at the end,
            # matching the old loop (which skipped every row).
            return n, n
        return start, n if end is None else end

    rows_bottom = tl.height() - timeline_viewport.footer_height(tl) - 2
    for scroll in (0, 40, 200, 900, 5000):
        rows_top = tl.STRIP_HEIGHT - scroll
        start, end, y0 = timeline_layout.visible_row_window(
            tl, rows_top, rows_bottom
        )
        exp_start, exp_end = _brute(rows_top, rows_bottom)
        assert (start, end) == (exp_start, exp_end), (
            scroll,
            (start, end),
            (exp_start, exp_end),
        )
        # y_at_start must equal rows_top plus the cached offset of start.
        if start < n:
            bottoms = timeline_layout._cached_row_bottoms(tl, tl._row_layout)
            expected_y = rows_top + (bottoms[start - 1] if start else 0.0)
            assert y0 == expected_y, (scroll, y0, expected_y)


def test_row_time_x_range_culls_off_damage_rows(qtbot):
    """The early row's x-range must sit left of late damage; the full row's
    must cover it."""
    tl = _make_widget(qtbot)
    duration = timeline_layout.content_duration(tl)
    logical = timeline_viewport.get_logical_width(tl)
    ranges = {}
    for item in tl._row_layout:
        if item[0] == "track_single":
            _kind, _group, track, channel = item
            ranges[track.id] = timeline_layout.row_time_x_range(
                tl, track, channel, duration, logical
            )
    assert set(ranges) == {"early", "full"}, ranges
    early_lo, early_hi = ranges["early"]
    full_lo, full_hi = ranges["full"]
    # Late damage band (same rect as the paint test above).
    assert early_hi < 700, (early_lo, early_hi)
    assert full_lo <= 700 and full_hi >= 760, (full_lo, full_hi)


def test_public_surface_unchanged(qtbot):
    """Signals, slots, and host-facing methods keep their names."""
    tl = _make_widget(qtbot)
    for signal in (
        "headMoved",
        "deletePressed",
        "zoomChanged",
        "viewportChanged",
        "viewportChangedState",
    ):
        assert hasattr(tl, signal), signal
    for method in (
        "get_visible_thumbnail_frame_indices",
        "fit_view",
        "update_layout_width",
        "set_data",
        "add_thumbnail",
        "clear_thumbnails",
    ):
        assert callable(getattr(tl, method, None)), method
    assert tl.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert isinstance(tl.get_visible_thumbnail_frame_indices(), list)


def _strip_blocks_full(tl):
    """All strip blocks over the full content range at current zoom."""
    base = timeline_viewport.get_base_tile_width(tl)
    logical = timeline_viewport.get_logical_width(tl)
    csx = float(tl.LEFT_GUTTER)
    blocks = timeline_viewport.strip_block_layout(
        tl, content_start_x=csx, start_x=csx, end_x=csx + logical
    )
    return base, logical, csx, blocks


def test_strip_block_width_constant_across_zooms(qtbot):
    """NLE-style fixed tiles: zoom changes frames-per-block, never width.

    Regression for the collapse-quantum sawtooth (draw_w oscillated
    ~base..base+slot as slot moved between ceil() steps). While collapsed
    every block is exactly base_tile wide; zoomed past 1:1 each block is
    exactly one slot wide.
    """
    tl = _make_widget(qtbot)
    base = timeline_viewport.get_base_tile_width(tl)
    assert base == 72 * 16 / 9, base
    for zoom in (tl._zoom_level, tl._zoom_level * 2, 0.5, 1.0, 2.0):
        tl._zoom_level = float(zoom)
        _base, _logical, _csx, blocks = _strip_blocks_full(tl)
        assert blocks, zoom
        slot = timeline_viewport.get_slot_width(tl)
        expected = base if slot < base else slot
        widths = {round(w, 6) for _, w, _ in blocks}
        assert widths == {round(expected, 6)}, (zoom, slot, widths)


def test_strip_blocks_tile_without_gaps(qtbot):
    """Consecutive blocks abut exactly; every frame sits inside a block
    whose rep frame does not overshoot it."""
    tl = _make_widget(qtbot)
    for zoom in (tl._zoom_level, 1.0):
        tl._zoom_level = float(zoom)
        _base, logical, csx, blocks = _strip_blocks_full(tl)
        slot = timeline_viewport.get_slot_width(tl)
        fpb = blocks[0][1] / slot
        for (x0, w0, _), (x1, _w1, _) in zip(blocks, blocks[1:]):
            assert x1 == pytest.approx(x0 + w0), (zoom, x0, w0, x1)
        assert blocks[0][0] == pytest.approx(csx), (zoom, blocks[0])
        assert blocks[-1][0] + blocks[-1][1] + 1e-6 >= csx + logical
        for f in range(0, tl._total_frames, 37):
            fx = csx + f * slot
            owner = [b for b in blocks if b[0] <= fx < b[0] + b[1]]
            assert owner, (zoom, f)
            assert owner[0][2] <= f <= owner[0][2] + fpb, (zoom, f, owner[0])


def test_visible_indices_match_strip_reps(qtbot):
    """Generation priority and paint draw from one layout: every visible
    index is a rep frame of the full-range strip layout."""
    tl = _make_widget(qtbot)
    _base, _logical, _csx, blocks = _strip_blocks_full(tl)
    reps = {r for _, _, r in blocks}
    idx = tl.get_visible_thumbnail_frame_indices(overscan_blocks=0)
    assert idx, "fit view must report visible frames"
    assert set(idx) <= reps, (idx, sorted(reps))
    assert idx == sorted(set(idx)), idx
