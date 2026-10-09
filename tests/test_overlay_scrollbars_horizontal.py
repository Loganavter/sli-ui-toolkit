"""OverlayScrollArea horizontal bar + custom→native drag propagation.

The floating thumbs used to set only their own value (vertical thumb drag
left native at 0 — measured live), and no horizontal overlay bar existed
at all. Uses direct handler calls (same idiom as
test_combo_scrollbar_drag), offscreen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.widgets import OverlayScrollArea


def _make_area(qtbot, content_w, content_h, area_w=300, area_h=200, **kwargs):
    area = OverlayScrollArea(**kwargs)
    qtbot.addWidget(area)
    content = QWidget()
    content.setFixedSize(content_w, content_h)
    area.setWidget(content)
    area.resize(area_w, area_h)
    area.show()
    qtbot.waitExposed(area)
    QApplication.processEvents()
    QApplication.processEvents()
    return area, content


def _event(typ, pos, buttons):
    return QMouseEvent(
        typ,
        QPointF(pos),
        pos,
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_h_bar_hidden_when_fits(qtbot):
    area, _ = _make_area(qtbot, 200, 100)
    assert not area.custom_h_scrollbar.isVisible()
    assert not area.custom_v_scrollbar.isVisible()


def test_h_bar_shows_on_overflow_bottom_anchored(qtbot):
    area, _ = _make_area(qtbot, 600, 100)
    bar = area.custom_h_scrollbar
    assert bar.isVisible()
    assert not area.custom_v_scrollbar.isVisible()
    assert bar.height() == area.scrollbar_width()
    assert bar.y() == area.height() - area.scrollbar_width() - area.scrollbar_gap()
    assert bar.x() == area.viewport().x()
    assert bar.width() == area.viewport().width()


def test_h_thumb_drag_drives_native(qtbot):
    area, _ = _make_area(qtbot, 600, 100)
    bar = area.custom_h_scrollbar
    native = area.horizontalScrollBar()
    assert native.maximum() > 0
    handle = bar._get_handle_rect()
    assert not handle.isEmpty()
    bar.mousePressEvent(_event(QMouseEvent.Type.MouseButtonPress, handle.center(), Qt.MouseButton.LeftButton))
    assert bar._is_dragging
    bar.mouseMoveEvent(
        _event(QMouseEvent.Type.MouseMove, handle.center() + QPoint(60, 0), Qt.MouseButton.LeftButton)
    )
    assert native.value() != 0
    assert native.value() == bar.value()
    bar.mouseReleaseEvent(
        _event(QMouseEvent.Type.MouseButtonRelease, handle.center(), Qt.MouseButton.NoButton)
    )
    assert not bar._is_dragging


def test_v_thumb_drag_drives_native(qtbot):
    area, _ = _make_area(qtbot, 100, 600)
    bar = area.custom_v_scrollbar
    native = area.verticalScrollBar()
    assert native.maximum() > 0
    handle = bar._get_handle_rect()
    assert not handle.isEmpty()
    bar.mousePressEvent(_event(QMouseEvent.Type.MouseButtonPress, handle.center(), Qt.MouseButton.LeftButton))
    assert bar._is_dragging
    bar.mouseMoveEvent(
        _event(QMouseEvent.Type.MouseMove, handle.center() + QPoint(0, 60), Qt.MouseButton.LeftButton)
    )
    assert native.value() != 0
    assert native.value() == bar.value()
    bar.mouseReleaseEvent(
        _event(QMouseEvent.Type.MouseButtonRelease, handle.center(), Qt.MouseButton.NoButton)
    )
    assert not bar._is_dragging


def test_widget_resizable_false_keeps_fixed_content(qtbot):
    area, content = _make_area(qtbot, 600, 100, widget_resizable=False)
    assert content.width() == 600
    assert area.custom_h_scrollbar.isVisible()


def test_thumb_position_tracks_scroll_value(qtbot):
    """Content identity: the painted handle position is the one implied by the
    value — at min it hugs the groove start, at max the end, and it advances
    monotonically. Geometry/value suites never checked the mapping, so a thumb
    drawn at the wrong (mirrored/stale) position passed them."""
    area, _ = _make_area(qtbot, 600, 100, area_w=300, area_h=200)
    bar = area.custom_h_scrollbar
    native = area.horizontalScrollBar()
    assert native.maximum() > 0

    handles = []
    for value in (native.minimum(), native.maximum() // 2, native.maximum()):
        native.setValue(value)
        QApplication.processEvents()
        QApplication.processEvents()
        handles.append(bar._get_handle_rect())

    first, mid, last = handles
    assert first.left() < mid.left() < last.left(), handles
    assert last.left() - first.left() > 10
    assert first.left() >= 0 and last.right() <= bar.width(), handles


def test_h_bar_autohides_and_reshows_on_scroll(qtbot):
    area, _ = _make_area(qtbot, 600, 100)
    bar = area.custom_h_scrollbar
    assert bar.isVisible()
    bar.set_auto_hide(0.15)
    qtbot.waitUntil(lambda: not bar.isVisible(), timeout=2000)
    area.horizontalScrollBar().setValue(50)  # scroll activity re-shows
    assert bar.isVisible()
