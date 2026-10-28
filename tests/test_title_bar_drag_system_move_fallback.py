"""Title-bar drag: a claimed-but-inert ``startSystemMove`` must not freeze the window.

Symptom (owner report, 2026-10-28): child windows cannot be dragged by the
title bar — press-and-drag changes the window *size* mentally (geometry
churn) but the window stays put. Platform discriminator: moves under
X11/XWayland (``QT_QPA_PLATFORM=xcb``), frozen on native Wayland and on
Windows.

Mechanism under test: ``QWindow.startSystemMove()`` returns True on those
platforms, ``mousePressEvent`` therefore sets ``_drag_system_move``, and
``mouseMoveEvent`` deliberately ignores its own motion events ("the
compositor owns this drag") — while the compositor moves nothing. Neither
side moves the window.

These tests emulate both platform behaviours (no real display needed):
``startSystemMove`` returning True while the window position never changes
(the broken platforms), and a compositor that genuinely moves the window
(no app-level delta may be added on top).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar


def _register_palettes(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("dark", qapp)


def _mouse_event(etype, local: QPoint, global_pos: QPoint, buttons=None):
    return QMouseEvent(
        etype,
        local,
        global_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton if buttons is None else buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _drag_bar(qapp):
    """A shown window with an attached, laid-out title bar + drag point."""
    _register_palettes(qapp)
    window = QWidget()
    window.resize(300, 200)
    bar = CustomTitleBar(parent=window, title="Test")
    bar.setGeometry(0, 0, 300, bar.height())
    bar.attach_window(window)
    window.show()
    qapp.processEvents()
    local = QPoint(10, bar.height() // 2)
    assert bar._is_draggable_at(local), "drag probe must be on open bar surface"
    return window, bar, local


def _press(bar, local: QPoint) -> QPoint:
    origin = bar.mapToGlobal(local)
    bar.mousePressEvent(
        _mouse_event(QMouseEvent.Type.MouseButtonPress, local, origin)
    )
    return origin


def _move(bar, local: QPoint, global_pos: QPoint) -> None:
    bar.mouseMoveEvent(
        _mouse_event(QMouseEvent.Type.MouseMove, local, global_pos)
    )


def _release(bar, local: QPoint) -> None:
    bar.mouseReleaseEvent(
        _mouse_event(
            QMouseEvent.Type.MouseButtonRelease,
            local,
            bar.mapToGlobal(local),
            buttons=Qt.MouseButton.NoButton,
        )
    )


def test_inert_system_move_falls_back_to_manual_move(qapp, monkeypatch):
    """startSystemMove() == True but the window never moves (native Wayland /
    Windows): the drag must take over manually instead of doing nothing."""
    window, bar, local = _drag_bar(qapp)
    try:
        monkeypatch.setattr(window.windowHandle(), "startSystemMove", lambda: True)
        origin = _press(bar, local)
        assert bar._drag_system_move is True, "press claims the system move"
        before = QPoint(window.pos())
        # Three motion events; the window stays exactly where the press left
        # it (emulates a compositor that accepts the request and ignores it).
        for step in (5, 10, 15):
            _move(bar, local + QPoint(step, 0), origin + QPoint(step, 0))
        assert bar._drag_system_move is False, "inert system move is dropped"
        # The first move after the fallback starts from a re-anchored origin,
        # so the window follows the remaining pointer delta — no teleport and
        # no jump to the cursor.
        assert window.pos() == before + QPoint(5, 0)
        # Continuing to drag keeps moving the window by the exact delta.
        _move(bar, local + QPoint(25, 8), origin + QPoint(25, 8))
        assert window.pos() == before + QPoint(15, 8)
        _release(bar, local)
        assert bar._drag_system_move is False
        assert bar._drag_start_global is None
    finally:
        window.deleteLater()
        bar.deleteLater()


def test_working_system_move_adds_no_app_delta(qapp, monkeypatch):
    """A compositor that really moves the window stays in charge: the app
    must not add its own delta on top (double movement)."""
    window, bar, local = _drag_bar(qapp)
    try:
        monkeypatch.setattr(window.windowHandle(), "startSystemMove", lambda: True)
        origin = _press(bar, local)
        assert bar._drag_system_move is True
        before = QPoint(window.pos())
        step = QPoint(10, 5)
        for i in range(1, 4):
            # Emulate the compositor: it moves the window by the pointer delta
            # *before* the motion event reaches the widget.
            window.move(window.pos() + step)
            _move(
                bar, local + step * i, origin + step * i
            )
        assert bar._drag_system_move is True, "a working system move is kept"
        assert window.pos() == before + step * 3, "no app-level double move"
    finally:
        window.deleteLater()
        bar.deleteLater()


def test_single_motion_event_does_not_fall_back(qapp, monkeypatch):
    """The first motion event of a press may legitimately precede the
    compositor's move — one event is not proof the system move is inert."""
    window, bar, local = _drag_bar(qapp)
    try:
        monkeypatch.setattr(window.windowHandle(), "startSystemMove", lambda: True)
        origin = _press(bar, local)
        before = QPoint(window.pos())
        _move(bar, local + QPoint(40, 20), origin + QPoint(40, 20))
        assert bar._drag_system_move is True
        assert window.pos() == before
    finally:
        window.deleteLater()
        bar.deleteLater()
