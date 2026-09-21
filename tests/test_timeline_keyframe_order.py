"""Order-invariant keyframe evaluation (unsorted-keyframes fix).

Regression test for task-fix-toolkit-unsorted-keyframes-2026-09-21:
``layout._evaluate_channel_at_timestamp``, ``layout._channel_value_at_timestamp``
(prefer-exact), ``layout.visible_keyframe_segments``, and
``segments._enum_state_spans`` assumed time-sorted ``channel.keyframes`` —
shuffled host input dropped or misplaced spans. All four sites now route
through ``layout._ordered_keyframes`` (stable sort, no host-data mutation),
so sorted and shuffled input evaluate identically.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    layout as timeline_layout,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    segments as timeline_segments,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.widgets import TimelineWidget


def _fitted_widget(qapp, qtbot):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("dark", qapp)
    w = TimelineWidget()
    snaps = [SimpleNamespace(timestamp=i / 10.0) for i in range(1001)]
    w.set_data(
        snapshots=snaps,
        fps=10,
        timeline_model=SimpleNamespace(
            groups={},
            sample_timestamps=[0.0, 100.0],
            get_duration=lambda: 100.0,
        ),
        duration=100.0,
    )
    qtbot.addWidget(w)
    w.resize(900, 500)
    w.show()
    qtbot.waitExposed(w)
    w.fit_view()
    qtbot.wait(10)
    return w


def _shuffled(keyframes):
    """Deterministic non-chronological permutation (rotate + interleave)."""
    order = [2, 0, 4, 1, 3]
    out = []
    for start in range(0, len(keyframes), 5):
        chunk = keyframes[start : start + 5]
        out.extend(chunk[i] for i in order if i < len(chunk))
    return out


def _scalar_pair():
    kfs = [
        SimpleNamespace(
            timestamp=float(t), value=float((t // 5) % 2), interpolation="linear"
        )
        for t in range(0, 50, 5)
    ]
    ordered = SimpleNamespace(
        kind="scalar", label="v", keyframes=list(kfs), interpolate_values=False
    )
    shuffled = SimpleNamespace(
        kind="scalar", label="v", keyframes=_shuffled(list(kfs)),
        interpolate_values=False,
    )
    track = SimpleNamespace(id="s", kind="scalar", label="S",
                            channels={"v": ordered})
    return track, ordered, shuffled


def _enum_pair():
    values = ["idle", "walk", "run", "idle", "walk", "run", "idle"]
    kfs = [
        SimpleNamespace(timestamp=float(t * 5), value=v, interpolation="linear")
        for t, v in enumerate(values)
    ]
    ordered = SimpleNamespace(
        kind="enum", label="st", keyframes=list(kfs), interpolate_values=False
    )
    shuffled = SimpleNamespace(
        kind="enum", label="st", keyframes=_shuffled(list(kfs)),
        interpolate_values=False,
    )
    track = SimpleNamespace(id="e", kind="enum", label="E",
                            channels={"st": ordered})
    return track, ordered, shuffled


def _color_track_pair():
    def _chan(levels):
        kfs = [
            SimpleNamespace(timestamp=float(i * 10), value=float(v),
                            interpolation="linear")
            for i, v in enumerate(levels)
        ]
        return kfs

    levels = {
        "r": [10, 200, 30, 255, 0],
        "g": [20, 40, 210, 128, 64],
        "b": [30, 60, 90, 32, 192],
    }
    ordered_channels, shuffled_channels = {}, {}
    for name, vals in levels.items():
        kfs = _chan(vals)
        ordered_channels[name] = SimpleNamespace(
            kind="scalar", label=name, keyframes=list(kfs),
            interpolate_values=False,
        )
        shuffled_channels[name] = SimpleNamespace(
            kind="scalar", label=name, keyframes=_shuffled(list(kfs)),
            interpolate_values=False,
        )
    ordered_track = SimpleNamespace(
        id="c", kind="color", label="C", channels=ordered_channels)
    shuffled_track = SimpleNamespace(
        id="c", kind="color", label="C", channels=shuffled_channels)
    return ordered_track, shuffled_track


def _probes():
    return [t * 2.5 for t in range(-1, 22)]


def test_scalar_step_evaluation_sorted_vs_shuffled():
    _, ordered, shuffled = _scalar_pair()
    shuffled_before = list(shuffled.keyframes)
    for ts in _probes():
        assert (
            timeline_layout._evaluate_channel_at_timestamp(shuffled, ts)
            == timeline_layout._evaluate_channel_at_timestamp(ordered, ts)
        )
    # No host-data mutation: shuffled order is preserved.
    assert list(shuffled.keyframes) == shuffled_before
    assert list(ordered.keyframes) == sorted(
        ordered.keyframes, key=lambda kf: float(kf.timestamp))


def test_prefer_exact_lookup_sorted_vs_shuffled():
    _, ordered, shuffled = _scalar_pair()
    for ts in _probes():
        assert (
            timeline_layout._channel_value_at_timestamp(
                shuffled, ts, prefer_exact=True)
            == timeline_layout._channel_value_at_timestamp(
                ordered, ts, prefer_exact=True)
        )


def test_enum_spans_sorted_vs_shuffled(qapp, qtbot):
    w = _fitted_widget(qapp, qtbot)
    track, ordered, shuffled = _enum_pair()
    duration, logical = 100.0, timeline_viewport.get_logical_width(w)
    ordered_spans = timeline_segments._enum_state_spans(
        w, track, ordered, duration, logical)
    shuffled_spans = timeline_segments._enum_state_spans(
        w, track, shuffled, duration, logical)
    assert len(shuffled_spans) == len(ordered_spans) > 0
    for got, want in zip(shuffled_spans, ordered_spans):
        assert got[:4] == want[:4]
        assert got[4] == want[4]


def test_scalar_segments_sorted_vs_shuffled(qapp, qtbot):
    w = _fitted_widget(qapp, qtbot)
    track, ordered, shuffled = _scalar_pair()
    duration = 100.0
    logical = timeline_viewport.get_logical_width(w)
    gx = float(w.LEFT_GUTTER)

    def _key(segment):
        return (
            round(segment["x1"], 4),
            round(segment["x2"], 4),
            round(segment["y"], 4),
            float(segment["start_kf"].timestamp),
            float(segment["end_kf"].timestamp),
            segment["start_kf"].value,
            segment["end_kf"].value,
        )

    want = timeline_layout.visible_keyframe_segments(
        w, track, ordered, duration, logical, 50.0, gx, gx + logical)
    got = timeline_layout.visible_keyframe_segments(
        w, track, shuffled, duration, logical, 50.0, gx, gx + logical)
    assert len(got) == len(want) > 0
    assert [_key(s) for s in got] == [_key(s) for s in want]


def test_color_track_value_sorted_vs_shuffled():
    ordered_track, shuffled_track = _color_track_pair()
    for ts in _probes():
        want = timeline_layout._color_track_value(ordered_track, ts)
        got = timeline_layout._color_track_value(shuffled_track, ts)
        assert (got.red(), got.green(), got.blue()) == (
            want.red(), want.green(), want.blue())
