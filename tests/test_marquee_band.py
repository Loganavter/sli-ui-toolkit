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
    assert gesture.eventFilter(host, release) is True
    assert gesture.active is False
    assert gesture.app_filter_installed is False
    assert finishes == [expected]
    assert not gesture.overlay.isVisible()


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
