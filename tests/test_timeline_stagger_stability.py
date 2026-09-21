"""Scalar lane stagger is damage-independent (timeline track-render remainder).

Regression test for task-timeline-track-render-remainder-2026-09-19:
``layout.visible_keyframe_segments`` used to advance its stagger parity
counter only for appended (in-damage) segments, so a partial repaint
assigned different lane y values than a full repaint and scalar lanes
visibly jumped between partial paints (playhead/hover/selection) and full
paints. The counter now advances per eligible segment before the damage
cull — partial and full paints agree on y and curve_points.
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


def _step_channel():
    kfs = [
        SimpleNamespace(timestamp=float(t), value=float((t // 5) % 2),
                        interpolation="linear")
        for t in range(0, 101, 5)
    ]
    ch = SimpleNamespace(kind="scalar", label="v", keyframes=kfs,
                         interpolate_values=False)
    tr = SimpleNamespace(id="s", kind="scalar", label="S", channels={"v": ch})
    return tr, ch


def test_scalar_stagger_matches_full_paint_in_damage_window(qapp, qtbot):
    w = _fitted_widget(qapp, qtbot)
    tr, ch = _step_channel()
    duration = 100.0
    logical = timeline_viewport.get_logical_width(w)
    gx = float(w.LEFT_GUTTER)
    full = timeline_layout.visible_keyframe_segments(
        w, tr, ch, duration, logical, 50.0, gx, gx + logical)
    assert len(full) > 1
    lo, hi = gx + logical * 0.4, gx + logical * 0.6
    part = timeline_layout.visible_keyframe_segments(
        w, tr, ch, duration, logical, 50.0, lo, hi)
    assert len(part) >= 1
    full_by_x = {
        (round(s["x1"], 4), round(s["x2"], 4)): s for s in full
    }
    for s in part:
        key = (round(s["x1"], 4), round(s["x2"], 4))
        assert key in full_by_x
        assert s["y"] == full_by_x[key]["y"]
        assert s.get("curve_points") == full_by_x[key].get("curve_points")


def test_scalar_stagger_matches_full_paint_at_left_edge(qapp, qtbot):
    """A damage window touching the content start must agree too (the old
    code counted parity from the first in-damage segment anywhere)."""
    w = _fitted_widget(qapp, qtbot)
    tr, ch = _step_channel()
    duration = 100.0
    logical = timeline_viewport.get_logical_width(w)
    gx = float(w.LEFT_GUTTER)
    full = timeline_layout.visible_keyframe_segments(
        w, tr, ch, duration, logical, 50.0, gx, gx + logical)
    edge = timeline_layout.visible_keyframe_segments(
        w, tr, ch, duration, logical, 50.0, gx, gx + logical * 0.15)
    assert len(edge) >= 1
    full_by_x = {
        (round(s["x1"], 4), round(s["x2"], 4)): s for s in full
    }
    for s in edge:
        key = (round(s["x1"], 4), round(s["x2"], 4))
        assert s["y"] == full_by_x[key]["y"]
