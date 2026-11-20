"""Ripple motion contract: M3 geometry (centre-based radius) and soft edge.

Reference: Compose `RippleAnimation` / Flutter `InkRipple` — expansion from
`0.3 x longest side` to half the diagonal (+ pad), the centre sliding from the
press point to the rect centre, phases 75 / expand / 150 ms.

Measured before this contract (hard 1 px edge, radius from the press point to
the farthest corner, fixed 200 ms) on a 1200 px button: the edge moved ~88 px
per 60 Hz frame, so successive frames read as two edges ("doubled"). After:
~43 px per frame inside a soft rim, and the wave ends as one centred circle.
"""

from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from sli_ui_toolkit.ui.widgets.buttons.feedback import (
    get_ripple_duration_ms,
    reset_feedback_defaults,
    set_ripple_duration_ms,
)
from sli_ui_toolkit.ui.widgets.buttons.layers.ripple import (
    FADE_IN_MS,
    FADE_OUT_MS,
    START_RADIUS_FRACTION,
    RippleEffect,
    ease_out_slow_in,
    wave_alpha,
    wave_edge_band,
    wave_edge_step,
    wave_geometry,
)
from sli_ui_toolkit.widgets import Button


# ---------------------------------------------------------------- phases


def test_alpha_fades_in_holds_and_fades_out() -> None:
    expand = 240
    assert wave_alpha(0, expand) == 0.0
    assert wave_alpha(FADE_IN_MS / 2, expand) == pytest.approx(0.5)
    assert wave_alpha(FADE_IN_MS, expand) == 1.0
    assert wave_alpha(expand, expand) == 1.0
    assert wave_alpha(expand + FADE_OUT_MS / 2, expand) == pytest.approx(0.5)
    assert wave_alpha(expand + FADE_OUT_MS, expand) == 0.0
    ramp = [wave_alpha(t, expand) for t in range(0, FADE_IN_MS + 1, 3)]
    assert all(a <= b for a, b in zip(ramp, ramp[1:]))
    fade = [
        wave_alpha(t, expand)
        for t in range(expand, expand + FADE_OUT_MS + 1, 5)
    ]
    assert all(a >= b for a, b in zip(fade, fade[1:]))


def test_expansion_curve_is_the_m3_bezier() -> None:
    assert ease_out_slow_in(0.0) == 0.0
    assert ease_out_slow_in(1.0) == 1.0
    values = [ease_out_slow_in(p / 100) for p in range(101)]
    assert all(a <= b for a, b in zip(values, values[1:]))
    # cubic-bezier(0.4, 0, 0.2, 1): slow out of the gate, then accelerate
    assert ease_out_slow_in(0.1) < 0.05
    assert ease_out_slow_in(0.5) > 0.5


# ---------------------------------------------------------------- geometry


def test_radius_is_centre_based_not_press_based() -> None:
    rect = QRectF(0, 0, 1200, 44)
    end = math.hypot(rect.width(), rect.height()) / 2
    # A press at the left end must NOT need a 1200 px radius: the wave ends as
    # one centred circle of half the diagonal.
    centre, radius = wave_geometry(QPointF(5, 22), rect, 1.0)
    assert radius == pytest.approx(end, abs=0.5)
    assert centre.x() == pytest.approx(rect.center().x())
    # ... and it starts already large (0.3 x the longest side), not at a dot.
    start_centre, start_radius = wave_geometry(QPointF(5, 22), rect, 0.0)
    assert start_radius == pytest.approx(START_RADIUS_FRACTION * 1200)
    assert start_centre.x() == pytest.approx(5)
    assert start_radius < radius


def test_edge_step_and_rim_scale_with_the_control() -> None:
    short = wave_edge_step(QPointF(8, 22), QRectF(0, 0, 160, 44), 240)
    long = wave_edge_step(QPointF(60, 22), QRectF(0, 0, 1200, 44), 240, pad_px=10)
    assert short < 16
    assert 75 <= long <= 90
    # The rim is one frame of travel: the band must be at least the step, or
    # consecutive frames leave a seam (the "doubling").
    assert wave_edge_band(600, long) >= long
    assert wave_edge_band(600, long) <= 0.35 * 600
    # ... but a slow edge keeps a crisp rim (10 % floor).
    assert wave_edge_band(600, 10) == pytest.approx(60)


def test_defaults_are_the_m3_expansion_length() -> None:
    reset_feedback_defaults()
    assert get_ripple_duration_ms() == 240
    assert RippleEffect.DURATION_MS == 240
    assert RippleEffect.TICK_MS <= 10


def test_set_ripple_duration_ms_keeps_class_attribute_in_sync() -> None:
    try:
        set_ripple_duration_ms(150)
        assert RippleEffect.DURATION_MS == 150
    finally:
        reset_feedback_defaults()


# ---------------------------------------------------------------- effect


def test_every_width_uses_the_reference_expansion(qtbot) -> None:
    """No distance stretch: 225 ms everywhere, plus the fade-out."""
    for width in (160, 400, 800, 1200):
        button = Button(text="x", size=(width, 44))
        qtbot.addWidget(button)
        button.show()
        ripple = button._ripple
        ripple.trigger(QPointF(10, 10))
        assert ripple.expand_ms() == 240, (width, ripple.expand_ms())
        assert ripple.total_ms() == 240 + FADE_OUT_MS
        ripple.cancel()
        button.close()


def test_tick_advances_by_measured_time_not_by_the_nominal_interval(qtbot) -> None:
    button = Button(text="x", size=(120, 40))
    qtbot.addWidget(button)
    button.show()
    ripple = button._ripple
    ripple.trigger(QPointF(10, 10))
    ripple._timer.stop()
    qtbot.wait(50)
    ripple._on_tick()
    assert 30 <= ripple._elapsed <= 120
    assert ripple.is_active()
    ripple.cancel()


def test_hidden_widget_ends_the_wave_without_advancing(qtbot) -> None:
    button = Button(text="x", size=(120, 40))
    qtbot.addWidget(button)
    button.show()
    ripple = button._ripple
    ripple.trigger(QPointF(10, 10))
    button.hide()
    ripple._on_tick()
    assert not ripple.is_active()
    assert ripple.remaining_ms() == 0


# ---------------------------------------------------------------- rendered


def _button(qtbot, width: int) -> Button:
    button = Button(text="", size=(width, 44))
    # A registered palette is not part of this fixture; pin an opaque base so
    # the black overlay is measurable.
    button.set_override_bg_color(QColor(240, 240, 240))
    button.set_bg_locked(True)
    qtbot.addWidget(button)
    button.show()
    return button


def _painted(button: Button) -> QImage:
    img = QImage(button.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(240, 240, 240))
    painter = QPainter(img)
    try:
        button._painter.paint(button._make_context(painter))
    finally:
        painter.end()
    return img


def _edge_x(button: Button) -> int | None:
    """Rightmost column carrying at least a quarter of the wave's contrast."""
    base = _painted_rest(button)
    img = _painted(button)
    deltas = [
        abs(base.pixelColor(x, 3).red() - img.pixelColor(x, 3).red())
        for x in range(img.width())
    ]
    peak = max(deltas)
    if peak < 6:
        return None
    threshold = peak * 0.25
    for x in range(len(deltas) - 1, -1, -1):
        if deltas[x] >= threshold:
            return x
    return None


def _painted_rest(button: Button) -> QImage:
    blocked = button._ripple.is_active()
    if blocked:
        button._ripple.cancel()
    img = _painted(button)
    return img


def test_per_frame_edge_step_is_bounded_on_a_long_button(qtbot) -> None:
    """The acceptance for "the wave doubles": the rim covers the per-frame step.

    At 240 ms a 1200 px control moves the edge ~84 px per 60 Hz frame; the
    outer 15 % of the radius (~90 px at full expansion) has to be at least
    that wide for consecutive frames to overlap.
    """
    button = _button(qtbot, 1200)
    ripple = button._ripple
    base = _painted(button)
    ripple.trigger(QPointF(60, 22))
    ripple._timer.stop()
    expand = ripple.expand_ms()
    edges = []
    frame_ms = 16.667
    for i in range(0, 28):
        ripple._elapsed = min(expand, int(i * frame_ms))
        img = _painted(button)
        deltas = [
            abs(base.pixelColor(x, 3).red() - img.pixelColor(x, 3).red())
            for x in range(img.width())
        ]
        peak = max(deltas)
        if peak < 6:
            edges.append(None)
            continue
        threshold = peak * 0.25
        edges.append(next((x for x in range(len(deltas) - 1, -1, -1) if deltas[x] >= threshold), None))
    steps = [b - a for a, b in zip(edges, edges[1:]) if a is not None and b is not None]
    assert steps, "no wave frames measured"
    assert max(steps) <= 90, f"per-frame step {max(steps)} px (edges={edges})"
    ripple.cancel()


def test_overlay_still_has_contrast_when_the_edge_crosses_the_button(qtbot) -> None:
    button = _button(qtbot, 120)
    base = _painted(button)
    ripple = button._ripple
    point = button.rect().center()
    ripple.trigger(QPointF(point))
    ripple._timer.stop()
    ripple._elapsed = ripple.expand_ms() // 2
    mid = _painted(button)
    delta = max(
        abs(base.pixelColor(point).red() - mid.pixelColor(point).red()),
        abs(base.pixelColor(point).green() - mid.pixelColor(point).green()),
        abs(base.pixelColor(point).blue() - mid.pixelColor(point).blue()),
    )
    assert delta >= 20
    ripple._elapsed = ripple.expand_ms() + FADE_OUT_MS
    tail = _painted(button)
    assert max(
        abs(base.pixelColor(point).red() - tail.pixelColor(point).red()),
        abs(base.pixelColor(point).green() - tail.pixelColor(point).green()),
        abs(base.pixelColor(point).blue() - tail.pixelColor(point).blue()),
    ) <= 4
    ripple.cancel()
