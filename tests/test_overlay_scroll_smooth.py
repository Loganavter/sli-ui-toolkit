"""OverlayScrollArea wheel-glide tests.

Wheel deltas accumulate into a target scroll position and the viewport eases
toward it over several ticks (Chrome/Firefox-style) instead of jumping in
discrete steps. External setValue cancels the glide.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea


def _build_area(qtbot, content_h=2000):
    area = OverlayScrollArea()
    qtbot.addWidget(area)
    host = QWidget()
    host.resize(300, 400)
    host.setMinimumHeight(content_h)
    area.setWidget(host)
    area.resize(300, 400)
    area.show()
    qtbot.waitExposed(area)
    return area


def _wheel(angle_y=-120, pixel_y=0):
    return QWheelEvent(
        QPointF(150, 200),
        QPointF(150, 200),
        QPoint(0, pixel_y),
        QPoint(0, angle_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_wheel_glides_smoothly(qtbot):
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    assert native.maximum() == 1600
    samples: list[int] = []
    native.valueChanged.connect(samples.append)
    QApplication.sendEvent(area.viewport(), _wheel())
    expected = area._scroll_target
    assert expected == 60  # wheelScrollLines(3) * singleStep(20), min 40
    qtbot.waitUntil(lambda: native.value() == expected, timeout=2000)
    assert samples == sorted(samples)  # monotonic — no jumps or backtracking
    assert len(set(samples)) > 3  # eased over many ticks, not one step
    # Glide finished: no further activity.
    count = len(samples)
    qtbot.wait(150)
    assert len(samples) == count


def test_wheel_accumulates_during_glide(qtbot):
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    QApplication.sendEvent(area.viewport(), _wheel())
    qtbot.wait(50)  # glide in flight
    assert 0 < native.value() < 60
    QApplication.sendEvent(area.viewport(), _wheel())
    qtbot.waitUntil(lambda: native.value() == 120, timeout=2000)


def test_external_setvalue_cancels_glide(qtbot):
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    QApplication.sendEvent(area.viewport(), _wheel())
    qtbot.wait(30)
    assert native.value() > 0
    native.setValue(500)  # thumb drag / programmatic scroll
    qtbot.wait(300)
    assert native.value() == 500


def test_touchpad_pixel_delta_glides(qtbot):
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    samples: list[int] = []
    native.valueChanged.connect(samples.append)
    # Negative pixel delta = finger down = scroll down (Qt convention).
    QApplication.sendEvent(area.viewport(), _wheel(pixel_y=-25))
    qtbot.waitUntil(lambda: native.value() == 25, timeout=2000)
    assert len(set(samples)) > 2


def test_no_scroll_range_ignores_wheel(qtbot):
    area = _build_area(qtbot, content_h=300)  # content fits the viewport
    native = area.verticalScrollBar()
    assert native.maximum() == 0
    QApplication.sendEvent(area.viewport(), _wheel())
    qtbot.wait(100)
    assert native.value() == 0