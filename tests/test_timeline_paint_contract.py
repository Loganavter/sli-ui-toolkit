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

import inspect
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QPaintEvent

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    layout as timeline_layout,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    primitives as timeline_primitives,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    render as timeline_render,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    segments as timeline_segments,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.widgets import TimelineWidget

_DURATION = 100.0


def _keyframe(timestamp, value):
    return SimpleNamespace(
        timestamp=float(timestamp),
        value=value if isinstance(value, str) else float(value),
        interpolation="linear",
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


def test_timeline_debug_lines_format_cleanly(qtbot, monkeypatch):
    """Every ``[timeline-debug]`` / ``[timeline-paint]`` format string must
    match its args (a ``blocks=%s`` field without the arg once crashed
    *every* paint's logging handler with ``TypeError: not enough
    arguments``). Forces all strip debug lines with thumbs present and
    formats each captured record — any mismatch raises here, not in
    production logs."""
    import logging

    from PySide6.QtGui import QPixmap

    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import debug as timeline_debug

    monkeypatch.setenv("SLI_TIMELINE_DEBUG", "1")
    assert timeline_debug._timeline_debug_enabled()
    records: list = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("sli_ui_toolkit.timeline")
    handler = _Capture()
    old_level = logger.level
    # The level gate (SLI_TOOLKIT_DEBUG in host setup_logging) is env
    # behavior, not under test here — force records through so the
    # *format* parity below is what fails on mismatch.
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        tl = _make_widget(qtbot)
        for i in range(0, tl._total_frames, 7):
            px = QPixmap(160, 90)
            px.fill(0x4488CC)
            tl.add_thumbnail(i, px)
        _paint(tl, QRect(0, 0, tl.width(), tl.height()))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    assert records, "expected timeline debug records with the gate open"
    for record in records:
        record.getMessage()


# --- Phase 1 single-geometry contracts ---------------------------------------


def test_row_center_y_is_single_contract():
    """``row_center_y`` is the one lane-center mapping (float, no int)."""
    assert timeline_layout.row_center_y(100.0, 30.0) == 115.0
    assert timeline_layout.row_center_y(72.0, 28.0) == 86.0
    # Odd scaled heights land on .5 — the int() center used to floor these.
    assert timeline_layout.row_center_y(0.0, 33.0) == 16.5
    assert timeline_layout.row_center_y(10.0, 31.0) == 25.5
    for y, h in ((0.0, 30.0), (72.0, 28.0), (-20.0, 33.0), (5.5, 27.0)):
        assert timeline_layout.row_center_y(y, h) == y + h / 2.0


def test_draw_rows_routes_centers_through_primitive(qtbot, monkeypatch):
    """Both lane kinds paint centers via ``draw_center_line``, after curves."""
    tl = _make_widget(qtbot)
    order: list[tuple] = []
    original_segments = timeline_render._draw_keyframe_segments
    original_center = timeline_primitives.draw_center_line

    def _counting_segments(widget, painter, **kwargs):
        order.append(("segments", kwargs["track"].id))
        return original_segments(widget, painter, **kwargs)

    def _counting_center(painter, x0, x1, center_y, color):
        order.append(("center", round(float(center_y), 4)))
        return original_center(painter, x0, x1, center_y, color)

    monkeypatch.setattr(
        timeline_render, "_draw_keyframe_segments", _counting_segments
    )
    monkeypatch.setattr(
        timeline_primitives, "draw_center_line", _counting_center
    )
    _paint(tl, QRect(0, 0, tl.width(), tl.height()))
    kinds = [kind for kind, _ in order]
    # Two lanes (early + full) each paint segments then their center line.
    assert kinds == ["segments", "center", "segments", "center"], order
    centers = [value for kind, value in order if kind == "center"]
    # Centers equal the single-contract mapping for the painted rows.
    start, end, y = timeline_layout.visible_row_window(
        tl, tl.STRIP_HEIGHT, tl.height()
    )
    expected = []
    yy = y
    for item in tl._row_layout[start:end]:
        if item[0] == "group":
            yy += tl.GROUP_HEADER_HEIGHT
        else:
            row_h = (
                tl.TRACK_ROW_HEIGHT
                if item[0] == "track_single"
                else tl.CHANNEL_ROW_HEIGHT
            )
            expected.append(timeline_layout.row_center_y(yy, row_h))
            yy += row_h
    assert centers == pytest.approx(expected), (centers, expected)


def test_damage_pad_single_source():
    """One ``DAMAGE_PAD`` in layout; segments imports it, no literals."""
    assert timeline_layout.DAMAGE_PAD == 12.0
    params = inspect.signature(timeline_layout.row_time_x_range).parameters
    assert params["pad_px"].default == timeline_layout.DAMAGE_PAD
    segments_source = inspect.getsource(timeline_segments)
    assert "DAMAGE_PAD" in segments_source
    assert "- 12.0" not in segments_source
    assert "+ 12.0" not in segments_source
    layout_source = inspect.getsource(timeline_layout)
    assert layout_source.count("12.0") == 1, layout_source.count("12.0")


def _color_track(track_id="col", label="Col"):
    def _comp(name, values):
        return _channel(
            name,
            [_keyframe(t, float(v)) for t, v in enumerate(values)],
            kind="scalar",
        )

    return _track(
        track_id,
        label,
        {
            "r": _comp("r", [255, 10]),
            "g": _comp("g", [0, 200]),
            "b": _comp("b", [0, 30]),
            "a": _comp("a", [255, 255]),
        },
        kind="color",
    )


def _enum_track(track_id="mode", label="Mode"):
    return _track(
        track_id,
        label,
        {
            "v": _channel(
                "v",
                [
                    _keyframe(0, "a"),
                    _keyframe(5, "b"),
                    _keyframe(9, "b"),
                ],
                kind="enum",
            )
        },
        kind="enum",
    )


def _make_mixed_widget(qtbot):
    model = _model(
        {
            "g1": _group("G1", {"col": _color_track()}),
            "g2": _group("G2", {"mode": _enum_track()}),
        }
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


def test_color_enum_cull_matches_draw_path(qtbot):
    """Cull x-ranges come from the draw builders, tail to duration included."""
    tl = _make_mixed_widget(qtbot)
    duration = timeline_layout.content_duration(tl)
    logical = timeline_viewport.get_logical_width(tl)
    rows = {}
    for item in tl._row_layout:
        if item[0] == "track_single":
            _kind, _group, track, channel = item
            rows[track.id] = (track, channel)
    assert set(rows) == {"col", "mode"}, set(rows)
    for track_id, (track, channel) in rows.items():
        culled = timeline_layout.row_time_x_range(
            tl, track, channel, duration, logical
        )
        direct = timeline_segments.content_x_range(
            tl, track, channel, duration, logical
        )
        assert culled == direct, track_id
        assert culled is not None, track_id
        lo, hi = culled
        # The painted tail runs to the duration endpoint even though the
        # last keyframe sits earlier — the old min/max-stamp range missed it.
        end_x = timeline_layout.time_to_x(tl, duration, duration, logical)
        assert hi >= end_x - 1e-6, (track_id, culled, end_x)
        assert lo <= end_x, (track_id, culled, end_x)
        # Damage fully past the range culls; overlapping damage does not.
        assert (
            timeline_render._row_segments_culled(
                tl,
                track=track,
                channel=channel,
                duration=duration,
                logical_width=logical,
                start_x=hi + 100,
                end_x=hi + 200,
            )
            is True
        )
        mid = (lo + hi) * 0.5
        assert (
            timeline_render._row_segments_culled(
                tl,
                track=track,
                channel=channel,
                duration=duration,
                logical_width=logical,
                start_x=mid - 10,
                end_x=mid + 10,
            )
            is False
        )


def _brute_group_toggle_hit(tl, pos):
    """Pre-Phase-1 private y-loop, kept as the equivalence oracle."""
    if not tl._row_layout:
        return None
    scroll_area = timeline_viewport.get_scroll_area(tl)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    _content_top, rows_bottom = timeline_viewport.content_viewport_bounds(tl)
    y = tl.STRIP_HEIGHT - timeline_viewport.vertical_scroll_value(tl)
    for item in tl._row_layout:
        if y >= rows_bottom:
            break
        if item[0] == "group":
            group = item[1]
            rect = tl._group_chevron_rect(tl._group_header_rect(scroll_offset, y))
            if rect.contains(QPointF(pos)):
                return group
            y += tl.GROUP_HEADER_HEIGHT
        elif item[0] == "track_single":
            y += tl.TRACK_ROW_HEIGHT
        else:
            y += tl.CHANNEL_ROW_HEIGHT
    return None


def test_group_toggle_hit_matches_visible_window(qtbot, monkeypatch):
    """Rebuilt hit-test agrees with the old loop at several scrolls."""
    tl = _make_widget(qtbot)
    for scroll in (0, 50, 200, 2000):
        monkeypatch.setattr(
            timeline_viewport, "vertical_scroll_value", lambda _w, s=scroll: s
        )
        for y in range(0, tl.height(), 7):
            for x in (5, 15, 100, 400):
                pos = QPoint(x, y)
                assert timeline_layout.group_toggle_hit(tl, pos) == (
                    _brute_group_toggle_hit(tl, pos)
                ), (scroll, x, y)
    monkeypatch.undo()


def test_group_toggle_hit_chevron_click(qtbot):
    """Clicking a painted chevron toggles that group, elsewhere misses."""
    tl = _make_widget(qtbot)
    rows_top = tl.STRIP_HEIGHT - timeline_viewport.vertical_scroll_value(tl)
    _content_top, rows_bottom = timeline_viewport.content_viewport_bounds(tl)
    start, end, y = timeline_layout.visible_row_window(tl, rows_top, rows_bottom)
    groups = [item[1] for item in tl._row_layout[start:end] if item[0] == "group"]
    assert groups, "expected visible group rows"
    yy = y
    for item in tl._row_layout[start:end]:
        if item[0] != "group":
            yy += (
                tl.TRACK_ROW_HEIGHT
                if item[0] == "track_single"
                else tl.CHANNEL_ROW_HEIGHT
            )
            continue
        header = tl._group_header_rect(0, yy)
        chevron = tl._group_chevron_rect(header)
        center = chevron.center()
        hit = timeline_layout.group_toggle_hit(
            tl, QPoint(int(center.x()), int(center.y()))
        )
        assert hit is item[1], (center, hit)
        yy += tl.GROUP_HEADER_HEIGHT
    assert timeline_layout.group_toggle_hit(tl, QPoint(700, 5)) is None
