"""Tests for MarqueeBandOverlay + MarqueeBandGesture."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    MarqueeBandGesture,
    MarqueeBandOverlay,
    map_content_rect_to_window,
)


def test_marquee_band_overlay_is_pointer_transparent(qapp, qtbot):
    host = QWidget()
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    band = MarqueeBandOverlay(host)
    band.set_accent(QColor("#9eccef"))
    band.set_band(QRect(40, 50, 120, 80))
    assert band.isVisible()
    assert band.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert band.parentWidget() is host
    assert band.geometry() == QRect(40, 50, 120, 80)

    band.set_band(None)
    assert not band.isVisible()


def test_map_content_rect_to_window_clips_to_viewport(qapp, qtbot):
    window = QWidget()
    window.resize(400, 300)
    qtbot.addWidget(window)
    window.show()
    qapp.processEvents()

    # Viewport owns content (same relationship as QScrollArea).
    clip = QWidget(window)
    clip.setGeometry(10, 20, 200, 100)
    clip.show()
    content = QWidget(clip)
    content.setGeometry(0, 0, 200, 400)
    content.show()
    qapp.processEvents()

    mapped = map_content_rect_to_window(
        content,
        QRect(0, 0, 50, 300),
        window=window,
        clip_widget=clip,
    )
    assert mapped.width() == 50
    assert mapped.height() == 100
    assert mapped.topLeft() == content.mapTo(window, QPoint(0, 0))


def test_marquee_band_gesture_updates_and_finishes(qapp, qtbot):
    host = QWidget()
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    content = QWidget(host)
    content.setGeometry(0, 0, 400, 300)
    content.show()

    updates: list[QRect] = []
    finishes: list[QRect] = []

    gesture = MarqueeBandGesture(
        content,
        on_update=updates.append,
        on_finish=finishes.append,
    )
    gesture.set_accent(QColor("#9eccef"))
    assert gesture.start(QPoint(10, 10)) is True
    assert gesture.active is True
    assert gesture.app_filter_installed is True
    assert gesture.overlay is not None
    assert gesture.overlay.isVisible()
    assert len(updates) == 1

    gesture._update_at(QPoint(80, 60))
    expected = QRect(QPoint(10, 10), QPoint(80, 60)).normalized()
    assert updates[-1] == expected

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(80, 60),
        content.mapToGlobal(QPoint(80, 60)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert gesture.eventFilter(host, release) is False
    assert gesture.active is False
    assert gesture.app_filter_installed is False
    assert finishes == [expected]
    assert not gesture.overlay.isVisible()


def test_marquee_release_reaches_widgets(qapp, qtbot):
    """Release passes through after finish (no press-tracking desync).

    Regression for inv-gallery-hover-loss-2026-09-26: the app-level
    filter used to consume the release whose press went through the
    window, leaving Qt press-tracking stuck ("LeftButton held") so
    later moves grab-routed to the press receiver — no hit-testing,
    no Enter, gallery hover capsule + delete badge dead.
    """
    host = QWidget()
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    content = QWidget(host)
    content.setGeometry(0, 0, 400, 300)
    content.show()

    finishes: list[QRect] = []
    gesture = MarqueeBandGesture(content, on_finish=finishes.append)
    assert gesture.start(QPoint(10, 10)) is True

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(80, 60),
        content.mapToGlobal(QPoint(80, 60)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # Finish runs, filter removed, overlay hidden — but the event itself
    # is NOT consumed, so QWidgetWindow sees the release.
    assert gesture.eventFilter(host, release) is False
    assert gesture.active is False
    assert gesture.app_filter_installed is False
    assert not gesture.overlay.isVisible()
    assert len(finishes) == 1


def test_marquee_band_gesture_tiny_drag_finishes_empty(qapp, qtbot):
    host = QWidget()
    host.resize(200, 200)
    qtbot.addWidget(host)
    host.show()
    content = QWidget(host)
    content.setGeometry(0, 0, 200, 200)
    content.show()

    finishes: list[QRect] = []
    gesture = MarqueeBandGesture(content, on_finish=finishes.append, min_drag_px=3)
    gesture.start(QPoint(20, 20))
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(21, 21),
        content.mapToGlobal(QPoint(21, 21)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    gesture.eventFilter(host, release)
    assert finishes == [QRect()]


def test_marquee_band_set_band_skips_identical_geometry(qapp, qtbot):
    """Same-geometry set_band is a no-op (no restack/repaint spam).

    The gesture drives set_band per mousemove (100+/s); without the
    early-out every event restacks + repaints the overlay and the band
    edge judders against compositor paint frames.
    """
    from PySide6.QtCore import QEvent, QObject

    host = QWidget()
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    paints: list[int] = []

    class _PaintCounter(QObject):
        def eventFilter(self, obj, ev):  # noqa: N802
            if ev.type() == QEvent.Type.Paint:
                paints.append(1)
            return False

    counter = _PaintCounter()
    band = MarqueeBandOverlay(host)
    band.installEventFilter(counter)
    rect = QRect(40, 50, 120, 80)
    band.set_band(rect)
    qapp.processEvents()
    qapp.processEvents()
    n1 = len(paints)
    assert band.isVisible()
    assert band.geometry() == rect
    band.set_band(QRect(rect))
    band.set_band(QRect(rect))
    qapp.processEvents()
    qapp.processEvents()
    assert band.isVisible()
    assert band.geometry() == rect
    assert len(paints) == n1  # no redundant repaint for identical geometry


def test_marquee_band_set_band_reraises_when_covered(qapp, qtbot):
    """Identical geometry re-raises a covered band — still without repaint.

    Sibling flyouts (context menus restack themselves on open) can end up
    above the band; the no-op path must restore stacking while skipping
    the repaint.
    """
    from PySide6.QtCore import QEvent, QObject

    host = QWidget()
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    paints: list[int] = []

    class _PaintCounter(QObject):
        def eventFilter(self, obj, ev):  # noqa: N802
            if ev.type() == QEvent.Type.Paint:
                paints.append(1)
            return False

    counter = _PaintCounter()
    band = MarqueeBandOverlay(host)
    band.installEventFilter(counter)
    rect = QRect(40, 50, 120, 80)
    band.set_band(rect)
    qapp.processEvents()
    qapp.processEvents()
    n1 = len(paints)

    cover = QWidget(host)
    cover.setGeometry(0, 0, 400, 300)
    cover.show()
    cover.raise_()
    qapp.processEvents()
    assert host.children()[-1] is cover

    band.set_band(QRect(rect))
    qapp.processEvents()
    qapp.processEvents()
    assert host.children()[-1] is band  # stacking restored
    assert band.isVisible()
    assert band.geometry() == rect
    n2 = len(paints)  # at most the one legitimate restack repaint
    assert n2 <= n1 + 1
    band.set_band(QRect(rect))  # topmost again: pure no-op
    qapp.processEvents()
    qapp.processEvents()
    assert len(paints) == n2  # ...with zero further repaints
