"""Frameless edge-resize: child hit-testing and software fallback."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.windows.frameless import (
    RESIZE_MARGIN,
    _ResizeFilter,
    _edges_for_pos,
    apply_frameless,
)


def test_edges_for_pos_detects_margin_zone():
    assert _edges_for_pos(200, 100, 0, 50) & int(Qt.Edge.LeftEdge.value)
    assert _edges_for_pos(200, 100, 199, 50) & int(Qt.Edge.RightEdge.value)
    assert _edges_for_pos(200, 100, 100, 0) & int(Qt.Edge.TopEdge.value)
    assert _edges_for_pos(200, 100, 100, 99) & int(Qt.Edge.BottomEdge.value)
    assert _edges_for_pos(200, 100, 100, 50) == 0


def test_resize_filter_manual_fallback_from_child_edge(qapp):
    window = QWidget()
    window.setMinimumSize(180, 120)
    window.resize(220, 160)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    child = QLabel("content", window)
    layout.addWidget(child)
    apply_frameless(window, resizable=True)
    window.show()
    qapp.processEvents()

    filt = window.findChild(_ResizeFilter)
    assert filt is not None

    # Pretend system resize is unavailable (typical Wayland dialog case).
    handle = window.windowHandle()
    assert handle is not None
    handle.startSystemResize = lambda _edges: False  # type: ignore[method-assign]

    # Press on the right edge inside the child (mapped into the window).
    edge_x = window.width() - 2
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(edge_x, 40),
        QPoint(edge_x, 40),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert filt.eventFilter(child, press) is True
    assert filt._manual_edges & int(Qt.Edge.RightEdge.value)

    start_w = window.width()
    # Manual resize tracks global deltas from the press origin.
    filt._update_manual_resize(
        QPoint(filt._manual_origin.x() + 40, filt._manual_origin.y())
    )
    qapp.processEvents()
    assert window.width() >= start_w + 30

    filt.end_manual_resize()
    assert filt._manual_edges == 0
    window.deleteLater()


def test_resize_filter_clears_cursor_for_other_window(qapp):
    a = QWidget()
    b = QWidget()
    apply_frameless(a, resizable=True)
    apply_frameless(b, resizable=True)
    a.resize(200, 150)
    b.resize(200, 150)
    a.show()
    b.show()
    qapp.processEvents()

    fa = a.findChild(_ResizeFilter)
    fb = b.findChild(_ResizeFilter)
    assert fa is not None and fb is not None

    fa._update_cursor(1, 75)
    assert fa._cursor_armed
    fb._update_cursor(1, 75)
    assert fb._cursor_armed
    assert not fa._cursor_armed

    a.deleteLater()
    b.deleteLater()


def test_resize_margin_constant_positive():
    assert RESIZE_MARGIN >= 4
