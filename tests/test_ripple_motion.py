"""Ripple motion contract: wall-clock time base + readable envelope.

Measured on the pre-change tree (2026-11-20) with the wave sampled at fixed
elapsed values on a 180x48 button: the overlay contrast fell to 9/255 by
192 ms and 2/255 by 256 ms of a 280 ms wave, i.e. the last ~100 ms moved the
edge at a contrast the eye cannot resolve; and a 20 ms/frame paint stretched
the 280 ms wave to 413 ms because ``_elapsed`` advanced by a fixed 16 ms per
tick instead of by measured time.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter

from sli_ui_toolkit.ui.widgets.buttons.feedback import (
    get_ripple_duration_ms,
    reset_feedback_defaults,
    set_ripple_duration_ms,
)
from sli_ui_toolkit.ui.widgets.buttons.layers.ripple import (
    RippleEffect,
    wave_opacity,
    wave_radius,
)
from sli_ui_toolkit.widgets import Button


# ---------------------------------------------------------------- envelope


def test_opacity_ramps_in_holds_and_fades() -> None:
    assert wave_opacity(0.0) == 0.0
    # Ramp-in during the first 10 %: a first frame at full opacity is a pop.
    assert wave_opacity(0.05) == pytest.approx(0.5)
    assert wave_opacity(0.10) == pytest.approx(1.0)
    # Hold through the travel of the radius.
    assert wave_opacity(0.30) == 1.0
    assert wave_opacity(0.62) == 1.0
    # Fade over the last third, monotonic, reaching zero at the end.
    values = [wave_opacity(p / 100) for p in range(62, 101)]
    assert all(a >= b for a, b in zip(values, values[1:]))
    assert values[-1] == 0.0
    # Halfway through the fade the overlay is still clearly visible.
    assert wave_opacity(0.80) > 0.5


def test_radius_is_independent_of_opacity_and_monotonic() -> None:
    assert wave_radius(0.0) == 0.0
    assert wave_radius(1.0) == 1.0
    # Fast start: a wave that reaches most of the button early reads as a
    # wave, not as a dot growing out of the pointer.
    assert wave_radius(0.3) > 0.5
    values = [wave_radius(p / 100) for p in range(101)]
    assert all(a <= b for a, b in zip(values, values[1:]))


def test_defaults_are_inside_the_motion_language() -> None:
    reset_feedback_defaults()
    assert get_ripple_duration_ms() == 200
    assert RippleEffect.DURATION_MS == 200
    # Finer than a 60 Hz frame so update() coalescing does the pacing instead
    # of a 62.5-vs-60 Hz beat.
    assert RippleEffect.TICK_MS <= 10


def test_set_ripple_duration_ms_keeps_class_attribute_in_sync() -> None:
    try:
        set_ripple_duration_ms(150)
        assert RippleEffect.DURATION_MS == 150
        assert get_ripple_duration_ms() == 150
    finally:
        reset_feedback_defaults()


# ---------------------------------------------------------------- wall clock


def test_tick_advances_by_measured_time_not_by_the_nominal_interval(qtbot) -> None:
    """A GUI-thread hitch must shorten the remaining frames, not stretch it."""
    button = Button(text="Apply", size=(120, 40))
    qtbot.addWidget(button)
    button.show()
    ripple = button._ripple
    ripple.trigger(QPointF(10, 10))
    ripple._timer.stop()  # isolate the tick bookkeeping from the event loop
    qtbot.wait(50)
    ripple._on_tick()
    # The old fixed-step tick moved 8/16 ms regardless of the 50 ms that
    # actually elapsed; the wave then ran long by exactly the hitch.
    assert 30 <= ripple._elapsed <= 120
    assert ripple.is_active()
    ripple.cancel()


def test_hidden_widget_ends_the_wave_without_advancing(qtbot) -> None:
    button = Button(text="Apply", size=(120, 40))
    qtbot.addWidget(button)
    button.show()
    ripple = button._ripple
    ripple.trigger(QPointF(10, 10))
    button.hide()
    ripple._on_tick()
    assert not ripple.is_active()
    assert ripple.remaining_ms() == 0


# ---------------------------------------------------------------- rendered


def _painted(button: Button) -> QImage:
    img = QImage(button.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(240, 240, 240))
    painter = QPainter(img)
    try:
        button._painter.paint(button._make_context(painter))
    finally:
        painter.end()
    return img


def _peak_delta(base: QImage, tinted: QImage, point) -> int:
    a = base.pixelColor(point)
    b = tinted.pixelColor(point)
    return max(
        abs(a.red() - b.red()),
        abs(a.green() - b.green()),
        abs(a.blue() - b.blue()),
    )


def test_overlay_still_has_contrast_when_the_edge_crosses_the_button(qtbot) -> None:
    """Mid-wave contrast is held at peak, not halved by a linear fade."""
    button = Button(text="", size=(120, 40))
    # A registered palette is not part of this fixture; pin an opaque base so
    # the black overlay is measurable (an unregistered token resolves black).
    button.set_override_bg_color(QColor(240, 240, 240))
    button.set_bg_locked(True)
    qtbot.addWidget(button)
    button.show()
    ripple = button._ripple
    base = _painted(button)
    point = button.rect().center()

    ripple.trigger(QPointF(point))
    ripple._timer.stop()
    ripple._elapsed = RippleEffect.DURATION_MS // 2
    mid = _painted(button)
    assert _peak_delta(base, mid, point) >= 25  # peak is 31/255 (light theme)

    # The tail is nearly gone — that part is the design, not the bug.
    ripple._elapsed = int(RippleEffect.DURATION_MS * 0.95)
    tail = _painted(button)
    assert _peak_delta(base, tail, point) <= 4
    ripple.cancel()
