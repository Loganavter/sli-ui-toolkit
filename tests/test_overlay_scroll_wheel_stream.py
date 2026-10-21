"""High-resolution wheel streams that mark EVERY event ``ScrollBegin``.

Owner live report (2026-10-22): vertical scrolling in the image-gallery grid
"crawls" — one wheel notch seems to take seconds, with a storm of events even
at ~50 cards. Plain xdotool notches settle to 60 px in ~0.5 s (measured on a
private Xvfb), so the defect shows only for devices/compositors that emit a
high-resolution stream.

Defect: ``OverlayScrollArea.wheelEvent`` re-based ``_scroll_target`` on
``event.phase() == Qt.ScrollPhase.ScrollBegin``. A high-resolution wheel (or a
smooth-scroll compositor) marks every event as ``ScrollBegin``, so each event
reset the accumulated glide target back to the still-unmoved live value before
the 16 ms ticker could advance it — every event discarded the previous one's
progress.

Red on the unmodified code: 10 ``ScrollBegin`` notches 16 ms apart advanced the
viewport 132 px (~13 px/notch) instead of the nominal 600 px (60/notch); with a
stream faster than the ticker the advance drops toward ~1 px per event.
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea


def _build_area(qtbot, content_h=4000):
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


def _wheel(angle_y=-120, pixel_y=0, phase=Qt.ScrollPhase.NoScrollPhase):
    return QWheelEvent(
        QPointF(150, 200),
        QPointF(150, 200),
        QPoint(0, pixel_y),
        QPoint(0, angle_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        phase,
        False,
    )


def test_scroll_begin_stream_advances_each_notch(qtbot):
    """10 ScrollBegin notches 16 ms apart must move >= 10 * 40 px.

    Red on the unmodified code (measured 132 px = ~13 px/notch): the target
    was re-based on every event, so only the last notch survived the glide.
    """
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    assert native.maximum() >= 1000
    notches = 10
    for _ in range(notches):
        QApplication.sendEvent(
            area.viewport(), _wheel(phase=Qt.ScrollPhase.ScrollBegin)
        )
        qtbot.wait(16)
    qtbot.waitUntil(lambda: native.value() >= notches * 40, timeout=3000)
    assert native.value() >= notches * 40


def test_scroll_begin_stream_accumulates_target(qtbot):
    """Each ScrollBegin notch adds a full notch to the target (~60 px)."""
    area = _build_area(qtbot)
    notches = 8
    for _ in range(notches):
        QApplication.sendEvent(
            area.viewport(), _wheel(phase=Qt.ScrollPhase.ScrollBegin)
        )
        qtbot.wait(16)
    # wheelScrollLines(3) * singleStep(20), floored at _SCROLL_MIN_NOTCH_PX(40)
    assert area._scroll_target is not None
    assert area._scroll_target >= notches * 40


def test_single_begin_then_update_behaves_as_before(qtbot):
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    QApplication.sendEvent(
        area.viewport(), _wheel(phase=Qt.ScrollPhase.ScrollBegin)
    )
    qtbot.waitUntil(lambda: native.value() == 60, timeout=2000)
    QApplication.sendEvent(area.viewport(), _wheel(phase=Qt.ScrollPhase.ScrollUpdate))
    qtbot.waitUntil(lambda: native.value() == 120, timeout=2000)
    assert native.value() == 120


def test_new_gesture_after_settle_rebases_from_live(qtbot):
    """A real new gesture after the glide settled continues from live value."""
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    QApplication.sendEvent(area.viewport(), _wheel())
    qtbot.waitUntil(lambda: native.value() == 60, timeout=2000)
    samples: list[int] = []
    native.valueChanged.connect(samples.append)
    QApplication.sendEvent(
        area.viewport(), _wheel(phase=Qt.ScrollPhase.ScrollBegin)
    )
    qtbot.waitUntil(lambda: native.value() == 120, timeout=2000)
    assert native.value() == 120
    assert samples == sorted(samples), samples  # no jump backwards
    assert all(value >= 60 for value in samples), samples


def test_begin_after_long_gap_rebases_while_glide_in_flight(qtbot):
    """A ScrollBegin >120 ms after the last wheel event starts a new gesture.

    Exercises the staleness branch deterministically: an in-flight target is
    present, but the previous wheel event is old, so the new gesture re-bases
    from the live value instead of stacking two notches on one.
    """
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    area._scroll_target = 60  # in-flight glide target, ticker not started
    area._last_wheel_ts = time.monotonic() - 1.0
    QApplication.sendEvent(
        area.viewport(), _wheel(phase=Qt.ScrollPhase.ScrollBegin)
    )
    assert area._scroll_target == native.value() + 60


def test_pixel_delta_stays_one_to_one(qtbot):
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    QApplication.sendEvent(
        area.viewport(), _wheel(angle_y=0, pixel_y=-25, phase=Qt.ScrollPhase.ScrollBegin)
    )
    qtbot.waitUntil(lambda: native.value() == 25, timeout=2000)
    assert native.value() == 25


def test_no_phase_notch_still_uses_single_step_lines(qtbot):
    area = _build_area(qtbot)
    native = area.verticalScrollBar()
    QApplication.sendEvent(area.viewport(), _wheel())
    assert area._scroll_target == 60  # wheelScrollLines(3) * singleStep(20)
    qtbot.waitUntil(lambda: native.value() == 60, timeout=2000)
    assert native.value() == 60
