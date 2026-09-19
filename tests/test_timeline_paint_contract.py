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
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPaintEvent

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager

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
    theme as timeline_theme,
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


# --- Wave G: single geometry source + token-only paint ------------------------


def _row_height_of(tl, kind: str) -> float:
    if kind == "group":
        return float(tl.GROUP_HEADER_HEIGHT)
    if kind == "track_single":
        return float(tl.TRACK_ROW_HEIGHT)
    return float(tl.CHANNEL_ROW_HEIGHT)


def _brute_row_rects(tl, rows_top: float, rows_bottom: float):
    """Independent oracle: full accumulation, visibility filter, no helpers."""
    out = []
    y = float(rows_top)
    for item in tl._row_layout:
        kind = item[0]
        h = _row_height_of(tl, kind)
        if y + h > 0.0 and y < rows_bottom:
            out.append((kind, item, QRectF(0.0, y, float(tl.LEFT_GUTTER), h)))
        y += h
    return out


def _tall_widget(qtbot):
    tracks = {}
    for i in range(30):
        tracks[f"t{i}"] = _track(
            f"t{i}",
            f"T{i}",
            {"v": _channel("v", [_keyframe(0, 0.0), _keyframe(10, 1.0)])},
        )
    groups = {f"g{i}": _group(f"G{i}", {f"t{i}": tracks[f"t{i}"]}) for i in range(10)}
    return _make_widget(qtbot, model=_model(groups))


def test_iter_row_rects_matches_brute_force_scrolled(qtbot):
    """``iter_row_rects`` agrees with brute force at several scrolls."""
    tl = _tall_widget(qtbot)
    _, rows_bottom = timeline_viewport.content_viewport_bounds(tl)
    for scroll in (0, 40, 200, 900, 5000):
        rows_top = tl.STRIP_HEIGHT - scroll
        got = list(timeline_layout.iter_row_rects(tl, rows_top, rows_bottom))
        expected = _brute_row_rects(tl, rows_top, rows_bottom)
        assert [k for k, _, _ in got] == [k for k, _, _ in expected], scroll
        assert len(got) == len(expected), scroll
        for (kind, key, rect), (exp_kind, exp_item, exp_rect) in zip(got, expected):
            assert kind == exp_kind, scroll
            assert key is exp_item, scroll
            assert rect == exp_rect, (scroll, rect, exp_rect)
        # y_at_start consistency with the window helper.
        start, end, y0 = timeline_layout.visible_row_window(tl, rows_top, rows_bottom)
        assert (len(got) == 0) == (start == end), scroll
        if got:
            assert got[0][2].top() == y0, (scroll, got[0][2].top(), y0)


def _id_group(group_id: str, label: str, tracks):
    grp = _group(label, tracks)
    grp.id = group_id
    return grp


def test_iter_row_rects_collapsed_state(qtbot):
    """Collapsed groups hide their children from ``iter_row_rects``."""
    early = _track(
        "early", "Early", {"v": _channel("v", [_keyframe(t, float(t % 2)) for t in range(6)])}
    )
    full = _track(
        "full",
        "Full",
        {"v": _channel("v", [_keyframe(t, float((t // 5) % 2)) for t in range(0, 101, 5)])},
    )
    model = _model(
        {
            "g1": _id_group("g1", "G1", {"early": early}),
            "g2": _id_group("g2", "G2", {"full": full}),
        }
    )
    tl = _make_widget(qtbot, model=model)
    _, rows_bottom = timeline_viewport.content_viewport_bounds(tl)
    rows_top = tl.STRIP_HEIGHT
    full_kinds = [k for k, _, _ in timeline_layout.iter_row_rects(tl, rows_top, rows_bottom)]
    assert full_kinds == ["group", "track_single", "group", "track_single"], full_kinds

    g1 = model.groups["g1"]
    assert not timeline_layout.is_group_collapsed(tl, g1)
    timeline_layout.toggle_group_collapsed(tl, g1)
    try:
        assert timeline_layout.is_group_collapsed(tl, g1)
        assert tl._is_group_collapsed(g1)
        got = list(timeline_layout.iter_row_rects(tl, rows_top, rows_bottom))
        assert [k for k, _, _ in got] == ["group", "group", "track_single"], got
        # Collapsed children are gone from the layout itself, so the brute
        # oracle over the rebuilt layout agrees too.
        expected = _brute_row_rects(tl, rows_top, rows_bottom)
        assert [k for k, _, _ in got] == [k for k, _, _ in expected]
        assert [r for _, _, r in got] == [r for _, _, r in expected]
    finally:
        timeline_layout.toggle_group_collapsed(tl, g1)
    assert not timeline_layout.is_group_collapsed(tl, g1)
    restored = [k for k, _, _ in timeline_layout.iter_row_rects(tl, rows_top, rows_bottom)]
    assert restored == full_kinds, restored


def test_group_key_prefers_id_then_label():
    assert timeline_layout.group_key(SimpleNamespace(id="abc", label="L")) == "abc"
    assert timeline_layout.group_key(SimpleNamespace(label="L")) == "L"
    assert timeline_layout.group_key(SimpleNamespace()) == ""


def test_group_functions_match_widget_methods(qtbot):
    """Layout group functions equal the widget methods wave T delegates."""
    tl = _make_widget(qtbot)
    groups = [item[1] for item in tl._row_layout if item[0] == "group"]
    assert groups, "expected group rows"
    for group in groups:
        assert timeline_layout.group_key(group) == tl._group_key(group)
        assert timeline_layout.is_group_collapsed(tl, group) == tl._is_group_collapsed(group)
        assert timeline_layout.group_accent_color(tl, group) == tl._group_accent_color(group)
        for left, top in ((0.0, 72.0), (137.0, 200.5)):
            header = timeline_layout.group_header_rect(tl, left, top)
            assert header == tl._group_header_rect(left, top), (left, top)
            assert timeline_layout.group_chevron_rect(header) == tl._group_chevron_rect(header)


def test_group_header_chevron_geometry(qtbot):
    """Exact header/chevron numbers (chevron must sit inside the gutter band)."""
    tl = _make_widget(qtbot)
    header = timeline_layout.group_header_rect(tl, 137.0, 72.0)
    assert header == QRectF(137.0, 72.0, float(tl.LEFT_GUTTER), float(tl.GROUP_HEADER_HEIGHT))
    chevron = timeline_layout.group_chevron_rect(header)
    assert chevron == QRectF(137.0 + 8, 72.0 + 2, 18, float(tl.GROUP_HEADER_HEIGHT) - 4)
    band = timeline_viewport.gutter_band_rect(tl, 137)
    assert band.contains(int(chevron.left()), int(chevron.center().y()))
    assert band.contains(int(chevron.right()), int(chevron.center().y()))


def test_toggle_group_collapsed_roundtrip(qtbot):
    """Toggle twice restores the layout; the key tracks membership."""
    tl = _tall_widget(qtbot)
    before = list(tl._row_layout)
    group = next(item[1] for item in before if item[0] == "group")
    key = timeline_layout.group_key(group)
    timeline_layout.toggle_group_collapsed(tl, group)
    assert key in tl._collapsed_group_ids
    assert len(tl._row_layout) < len(before)
    timeline_layout.toggle_group_collapsed(tl, group)
    assert key not in tl._collapsed_group_ids
    assert [i[0] for i in tl._row_layout] == [i[0] for i in before]


def test_no_is_dark_in_owned_paint_paths():
    """Plan I8 guard: render/primitives/segments paint without theme ternaries."""
    from pathlib import Path

    base = Path(timeline_render.__file__).resolve().parent
    for name in ("render.py", "primitives.py", "segments.py"):
        source = (base / name).read_text()
        assert "is_dark" not in source, name


@pytest.fixture()
def _themed(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    try:
        yield tm
    finally:
        tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
        tm.set_theme("light", qapp, await_ripples=False)


def test_wash_alpha_resolves_tokens_and_defaults(_themed, qapp):
    """Wash strengths: per-theme defaults, host token override wins in both."""
    tm = _themed
    assert timeline_render._wash_alpha(tm, "timeline.group.wash.track.alpha") == 22
    assert timeline_render._wash_alpha(tm, "timeline.group.wash.first.alpha") == 18
    assert timeline_render._wash_alpha(tm, "timeline.group.wash.channel.alpha") == 10
    assert timeline_render._wash_alpha(tm, "timeline.ruler.minor.tick.alpha") == 180
    tm.set_theme("dark", qapp, await_ripples=False)
    try:
        assert timeline_render._wash_alpha(tm, "timeline.group.wash.track.alpha") == 46
        assert timeline_render._wash_alpha(tm, "timeline.group.wash.first.alpha") == 42
        assert timeline_render._wash_alpha(tm, "timeline.group.wash.channel.alpha") == 24
        assert timeline_render._wash_alpha(tm, "timeline.ruler.minor.tick.alpha") == 150
        tm.set_color("timeline.group.wash.track.alpha", QColor(0, 0, 0, 99))
        assert timeline_render._wash_alpha(tm, "timeline.group.wash.track.alpha") == 99
    finally:
        tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
        tm.set_theme("light", qapp, await_ripples=False)


def _strip_probe(tl):
    """A thumbnail-strip pixel with no thumbs/segments/playhead.

    Phase 1 T-paint: a rep absent from the store paints the fail-closed
    placeholder (``timeline.track.background`` token), never raw canvas and
    never a neighbor pixmap.
    """
    return tl.grab().toImage().pixelColor(int(tl.LEFT_GUTTER) + 100, 10)


# --- Phase 3 polish: single DAMAGE_PAD + allocation-free loops -----------------


def test_damage_pad_singular_across_paint_passes():
    """One ``DAMAGE_PAD`` in layout; render culls through it, no literals.

    The old per-pass magic margins (ruler ``±20``/``±50``) are gone:
    minor ticks cull against ``DAMAGE_PAD``, major ticks against
    ``DAMAGE_PAD + _RULER_LABEL_EXTENT`` (label geometry, derived), and
    the selection/playhead passes cull against ``DAMAGE_PAD``-derived
    pads. ``viewport.damage_pad()`` resolves the same value.
    """
    from pathlib import Path

    render_src = Path(timeline_render.__file__).read_text()
    assert "DAMAGE_PAD" in render_src
    assert timeline_viewport.damage_pad() == timeline_layout.DAMAGE_PAD == 12.0
    for literal in ("start_x - 20", "end_x + 20", "start_x - 50", "end_x + 50"):
        assert literal not in render_src, literal
    layout_src = Path(timeline_layout.__file__).read_text()
    assert layout_src.count("12.0") == 1, layout_src.count("12.0")
    assert "_RULER_LABEL_EXTENT" in render_src


def test_no_qt_allocations_inside_paint_loops():
    """No ``QColor(``/``QPen(``/``QBrush(`` directly inside ``for``/``while``
    bodies in the paint modules: per-row/per-tick/per-segment colors and
    pens resolve through the per-paint locals and the private
    ``primitives._alpha_color`` / ``primitives._pen_for`` caches (whose
    definitions live outside any loop)."""
    import ast
    from pathlib import Path

    for module in (timeline_render, timeline_primitives):
        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        func = child.func
                        name = (
                            func.id
                            if isinstance(func, ast.Name)
                            else getattr(func, "attr", "")
                        )
                        assert name not in ("QColor", "QPen", "QBrush"), (
                            module.__name__,
                            ast.dump(child),
                        )


def test_double_paint_is_deterministic(qtbot):
    """Two full repaints produce byte-identical images (cache-share proof).

    The shared pen/color caches must not mutate between paints: any
    aliasing mutation would show up here as pixel drift.
    """
    from PySide6.QtGui import QImage, QPixmap

    tl = _make_widget(qtbot)
    for i in range(0, tl._total_frames, 11):
        px = QPixmap(64, 36)
        px.fill(0x4488CC)
        tl.add_thumbnail(i, px)

    def _render_once():
        image = QImage(tl.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        tl.render(image)
        return image

    first = _render_once()
    second = _render_once()
    assert not first.isNull() and not second.isNull()
    assert bytes(first.bits()) == bytes(second.bits())


def test_light_dark_paint_diverges_through_tokens(qtbot, qapp, _themed):
    """Light/dark paints differ, and a token override reaches the pixels."""
    tm = _themed
    tl = _make_widget(qtbot)
    qapp.processEvents()

    tm.set_theme("light", qapp, await_ripples=False)
    qapp.processEvents()
    light_px = _strip_probe(tl)
    assert light_px.rgb() == timeline_theme.build_theme_colors(tl)["track_bg"].rgb()

    tm.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    dark_px = _strip_probe(tl)
    assert dark_px.rgb() == timeline_theme.build_theme_colors(tl)["track_bg"].rgb()
    assert dark_px.rgb() != light_px.rgb()

    # Override the wash token: two alphas must paint two different gutters.
    tm.set_theme("light", qapp, await_ripples=False)
    tm.set_color("timeline.group.wash.track.alpha", QColor(0, 0, 0, 255))
    qapp.processEvents()
    opaque = tl.grab().toImage()
    tm.set_color("timeline.group.wash.track.alpha", QColor(0, 0, 0, 0))
    qapp.processEvents()
    clear = tl.grab().toImage()
    assert bytes(opaque.bits()) != bytes(clear.bits())
