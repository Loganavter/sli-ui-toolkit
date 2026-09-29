"""Tests for MarqueeState + paint_marquee_band + marquee_dirty_rect.

Port of the overlay-gesture contract (deleted ``test_marquee_band.py``) onto
the single in-paint mechanism: content-space identity, tiny-finish rule,
cancel-without-finish, release pass-through (hover-loss fix), pixel band.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    MarqueeState,
    marquee_dirty_rect,
    paint_marquee_band,
)


def _release_event(pos: QPoint, gpos: QPoint) -> QMouseEvent:
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        pos,
        gpos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_state_band_is_content_space_identity(qapp):
    del qapp
    host = QWidget()
    updates: list[QRect] = []
    finishes: list[QRect] = []
    st = MarqueeState(host, on_update=updates.append, on_finish=finishes.append)
    assert st.start(QPoint(10, 10)) is True
    assert st.active is True
    assert st.app_filter_installed is True
    assert updates == [QRect(10, 10, 1, 1)]
    rect = st.update_at(QPoint(80, 60))
    assert rect == QRect(QPoint(10, 10), QPoint(80, 60)).normalized()
    assert st.band_rect == rect
    out = st.finish_at(QPoint(80, 60))
    assert out == rect
    assert finishes == [rect]
    assert st.active is False
    assert st.app_filter_installed is False


def test_state_tiny_drag_finishes_empty(qapp):
    del qapp
    host = QWidget()
    finishes: list[QRect] = []
    st = MarqueeState(host, on_finish=finishes.append, min_drag_px=3)
    st.start(QPoint(20, 20))
    assert st.finish_at(QPoint(21, 21)) == QRect()
    assert finishes == [QRect()]


def test_state_cancel_clears_without_finish(qapp):
    del qapp
    host = QWidget()
    finishes: list[QRect] = []
    st = MarqueeState(host, on_finish=finishes.append)
    st.start(QPoint(5, 5))
    cleared = st.cancel()
    assert cleared == QRect(5, 5, 1, 1)
    assert finishes == []
    assert st.active is False
    assert st.app_filter_installed is False


def test_state_release_passes_through_while_finishing(qapp, qtbot):
    """Release finishes the drag but is NOT consumed (hover-loss contract)."""
    host = QWidget()
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()
    content = QWidget(host)
    content.setGeometry(0, 0, 400, 300)
    content.show()

    finishes: list[QRect] = []
    st = MarqueeState(content, on_finish=finishes.append)
    assert st.start(QPoint(10, 10)) is True
    release = _release_event(QPoint(80, 60), content.mapToGlobal(QPoint(80, 60)))
    assert st.eventFilter(host, release) is False
    assert st.active is False
    assert st.app_filter_installed is False
    assert finishes == [QRect(QPoint(10, 10), QPoint(80, 60)).normalized()]


def test_state_non_left_press_ignored_while_active(qapp):
    del qapp
    host = QWidget()
    st = MarqueeState(host)
    st.start(QPoint(10, 10))
    right = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(50, 50),
        QPoint(500, 500),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert st.eventFilter(host, right) is False
    assert st.active is True  # no cancel on interleaving press


def test_state_trace_gated(monkeypatch, qapp):
    del qapp
    from sli_ui_toolkit.widgets import MarqueeState as _S

    host = QWidget()
    lines: list[str] = []
    st = _S(host, on_trace=lines.append)
    monkeypatch.delenv("SLI_MARQUEE_DEBUG", raising=False)
    st.start(QPoint(1, 1))
    assert lines == []
    monkeypatch.setenv("SLI_MARQUEE_DEBUG", "1")
    st.cancel()
    assert any("state.cancel" in line for line in lines)


def test_paint_marquee_band_pixel() -> None:
    """Accent-blended pixels land inside the band rect, nowhere else."""
    from PySide6.QtGui import QImage

    band = QRect(100, 100, 200, 120)
    img = QImage(400, 300, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.white)
    painter = QPainter(img)
    paint_marquee_band(painter, band, QColor("#0078D4"))
    painter.end()
    white = QColor(Qt.GlobalColor.white).getRgb()
    assert img.pixelColor(band.center()).getRgb() != white
    assert img.pixelColor(5, 5).getRgb() == white
    # Empty/invalid rects are a no-op, never touch the device.
    painter2 = QPainter(img)
    paint_marquee_band(painter2, QRect(), QColor("#0078D4"))
    painter2.end()
    assert img.pixelColor(5, 5).getRgb() == white


def test_marquee_dirty_rect_union(qapp):
    del qapp
    old = QRect(100, 100, 400, 300)
    new = QRect(100, 100, 200, 150)
    dirty = marquee_dirty_rect(old, new)
    assert dirty == QRect(99, 99, 402, 302)
    assert marquee_dirty_rect(QRect(), QRect()).isEmpty()
    assert marquee_dirty_rect(QRect(), new) == new.adjusted(-1, -1, 1, 1)
    assert marquee_dirty_rect(old, QRect()) == old.adjusted(-1, -1, 1, 1)


def test_band_widget_stacks_over_content(qapp, qtbot):
    """Band widget floats above content children (Dolphin foreground parity)."""
    from sli_ui_toolkit.widgets import MarqueeBandWidget

    viewport = QWidget()
    viewport.resize(400, 300)
    qtbot.addWidget(viewport)
    viewport.show()
    content = QWidget(viewport)
    content.setGeometry(0, 0, 400, 600)
    content.show()
    card = QWidget(content)
    card.setGeometry(50, 50, 100, 100)
    card.show()
    band = MarqueeBandWidget(viewport)
    assert not band.isVisible()
    band.set_active(True)
    assert band.isVisible()
    band.set_band(QRect(40, 40, 200, 150))
    assert band.geometry() == QRect(40, 40, 200, 150)
    # Above the content and its cards in stacking order.
    siblings = viewport.children()
    assert siblings.index(band) > siblings.index(content)
    assert band.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    band.set_band(QRect(40, 40, 200, 150))  # identical: no-op, stays put
    assert band.geometry() == QRect(40, 40, 200, 150)
    band.set_active(False)
    assert not band.isVisible()
    assert band.band_rect().isEmpty()
