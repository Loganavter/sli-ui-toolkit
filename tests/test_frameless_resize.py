"""Frameless edge-resize: child hit-testing and software fallback."""

from __future__ import annotations

import os
from unittest.mock import patch

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


def _mouse_event(etype, local: QPoint, global_pos: QPoint):
    return QMouseEvent(
        etype,
        local,
        global_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
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


def _make_resizable_window(qapp) -> tuple[QWidget, _ResizeFilter]:
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
    return window, filt


def test_update_cursor_out_of_rect_clears(qapp):
    """Positions outside the window must never arm the resize cursor.

    ``_edges_for_pos`` treats any x past ``width - RESIZE_MARGIN`` as the
    right edge — without a bounds check, a stale global pointer position
    (e.g. after the window shrank under the pointer) keeps the resize
    cursor armed forever.
    """
    window, filt = _make_resizable_window(qapp)
    filt._update_cursor(window.width() - 2, 60)
    assert filt._cursor_armed
    filt._update_cursor(window.width() + 50, 60)
    assert not filt._cursor_armed
    filt._update_cursor(60, window.height() + 50)
    assert not filt._cursor_armed
    window.deleteLater()


def test_manual_resize_release_resnaps_cursor_to_release_position(qapp):
    """Releasing a live resize must re-evaluate the edge zone immediately.

    The window may have moved under the pointer during the drag; with no
    motion event after release, the resize cursor stays armed even when the
    pointer now sits in the middle of the (shrunk) window.
    """
    window, filt = _make_resizable_window(qapp)

    handle = window.windowHandle()
    assert handle is not None
    handle.startSystemResize = lambda _edges: False  # type: ignore[method-assign]

    edge_x = window.width() - 2
    press = _mouse_event(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(edge_x, 60),
        window.mapToGlobal(QPoint(edge_x, 60)),
    )
    assert filt.eventFilter(window, press) is True
    assert filt._manual_edges & int(Qt.Edge.RightEdge.value)

    # Drag the right edge left, past the pointer's own position: after the
    # release the pointer lands in the middle of the window, not on an edge.
    filt._update_manual_resize(window.mapToGlobal(QPoint(edge_x - 100, 60)))
    qapp.processEvents()

    release_local = QPoint(window.width() // 2, 60)
    release = _mouse_event(
        QMouseEvent.Type.MouseButtonRelease,
        release_local,
        window.mapToGlobal(release_local),
    )
    assert filt.eventFilter(window, release) is True
    assert filt._manual_edges == 0
    assert not filt._cursor_armed
    window.deleteLater()


def test_native_resize_release_resnaps_cursor_and_hover(qapp):
    """Native (compositor-driven) resize: on release the cursor zone and
    hover must snap to the real pointer position."""
    window, filt = _make_resizable_window(qapp)

    handle = window.windowHandle()
    assert handle is not None
    handle.startSystemResize = lambda _edges: True  # type: ignore[method-assign]

    # The compositor owns the cursor during a native drag; simulate the edge
    # zone being armed beforehand (hover over the edge) so we can verify the
    # release clears it when the pointer ends up in the middle.
    filt._update_cursor(window.width() - 2, 60)
    assert filt._cursor_armed

    edge_x = window.width() - 2
    press = _mouse_event(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(edge_x, 60),
        window.mapToGlobal(QPoint(edge_x, 60)),
    )
    assert filt.eventFilter(window, press) is True
    assert filt._native_resizing

    # The pointer ends up inside the window after the drag.
    release_local = QPoint(window.width() // 2, 60)
    release = _mouse_event(
        QMouseEvent.Type.MouseButtonRelease,
        release_local,
        window.mapToGlobal(release_local),
    )
    with patch(
        "sli_ui_toolkit.ui.widgets.helpers.hover_coordinator._COORDINATOR.reconcile"
    ) as spy:
        assert filt.eventFilter(window, release) is True
        spy.assert_called_once()
        assert spy.call_args.args[0] == window.mapToGlobal(release_local)
    assert not filt._native_resizing
    assert not filt._cursor_armed
    window.deleteLater()


def test_manual_resize_reconciles_hover_per_move(qapp):
    """During a software live-resize drag the grabbed pointer never delivers
    hover/move events to children — hover must be reconciled explicitly so
    button hover tracks the moving geometry."""
    window, filt = _make_resizable_window(qapp)
    handle = window.windowHandle()
    assert handle is not None
    handle.startSystemResize = lambda _edges: False  # type: ignore[method-assign]

    edge_x = window.width() - 2
    press = _mouse_event(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(edge_x, 60),
        window.mapToGlobal(QPoint(edge_x, 60)),
    )
    assert filt.eventFilter(window, press) is True

    with patch(
        "sli_ui_toolkit.ui.widgets.helpers.hover_coordinator._COORDINATOR.reconcile"
    ) as spy:
        filt._update_manual_resize(window.mapToGlobal(QPoint(edge_x + 30, 60)))
        filt._update_manual_resize(window.mapToGlobal(QPoint(edge_x + 60, 60)))
        assert spy.call_count == 2
        assert spy.call_args.args[0] == window.mapToGlobal(QPoint(edge_x + 60, 60))

    filt.end_manual_resize()
    window.deleteLater()


def test_filter_unhooked_when_window_destroyed(qapp):
    """Destroying a frameless window must drop its app-level resize filter.

    The filter is a QObject child of the window, but the app-level
    registration is not removed automatically — after the window is gone,
    every app event would keep invoking the dead filter (the shiboken
    "Internal C++ object already deleted" storm seen after closing a CSD
    dialog).
    """
    import shiboken6
    from PySide6.QtCore import QEvent

    window, filt = _make_resizable_window(qapp)

    # Arm so the destroy path has real state to release.
    filt._update_cursor(window.width() - 2, 60)
    assert filt._cursor_armed

    window.deleteLater()
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    # The filter (a QObject child of the window) dies with it; the destroyed
    # hook must have unhooked it from the app before that.
    assert not shiboken6.isValid(filt)

    # A straggler app event must not blow up (validity guard inside the
    # filter's eventFilter for whatever lands in the removal gap).
    other = QWidget()
    other.resize(100, 80)
    other.show()
    qapp.processEvents()
    qapp.sendEvent(other, QEvent(QEvent.Type.HoverMove))
    qapp.processEvents()
    other.deleteLater()
    qapp.processEvents()
