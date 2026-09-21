"""Chrome resize/move: content-frame limits, press system-move, mask coalescing."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from sli_ui_toolkit import (
    FLUENT_DARK,
    FLUENT_LIGHT,
    CustomTitleBar,
    ThemeManager,
    WindowChrome,
    WindowChromeConfig,
    apply_frameless,
    remove_frameless,
)
from sli_ui_toolkit.ui.windows import csd_helpers
from sli_ui_toolkit.ui.windows.csd_helpers import (
    _mask_edge_hosts,
    request_csd_mask_sync,
    sync_csd_chrome,
)
from sli_ui_toolkit.ui.windows.frameless import _ResizeFilter
from sli_ui_toolkit.ui.windows.rounded_body import apply_top_rounded_mask


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


def _banded_window(qapp, *, band=8, min_size=(300, 200), max_size=None):
    window = QWidget()
    window.setMinimumSize(*min_size)
    if max_size is not None:
        window.setMaximumSize(*max_size)
    window.resize(*min_size)
    apply_frameless(window, resizable=True, outer_band=band)
    window.show()
    qapp.processEvents()
    filt = window.findChild(_ResizeFilter)
    assert filt is not None
    handle = window.windowHandle()
    assert handle is not None
    return window, filt, handle


def _press_right_edge(qapp, window, filt, handle, *, native: bool):
    handle.startSystemResize = (lambda _e: True) if native else (lambda _e: False)  # type: ignore[method-assign]
    edge_x = window.width() - 2
    press = _mouse_event(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(edge_x, 60),
        window.mapToGlobal(QPoint(edge_x, 60)),
    )
    assert filt.eventFilter(window, press) is True
    return edge_x


def test_band_patch_translates_min_max_to_frame_space(qapp):
    """Install with a band bumps min/max by 2*band (frame space); remove
    restores the app's content sizes."""
    window = QWidget()
    window.setMinimumSize(300, 200)
    window.setMaximumSize(400, 300)
    apply_frameless(window, resizable=True, outer_band=8)
    try:
        assert (window.minimumWidth(), window.minimumHeight()) == (316, 216)
        assert (window.maximumWidth(), window.maximumHeight()) == (416, 316)
    finally:
        remove_frameless(window)
    assert (window.minimumWidth(), window.minimumHeight()) == (300, 200)
    assert (window.maximumWidth(), window.maximumHeight()) == (400, 300)
    window.deleteLater()


def test_manual_resize_clamps_to_content_frame_min(qapp):
    """App min is a CONTENT size: the frame keeps 2*band on top of it."""
    window, filt, handle = _banded_window(qapp, band=8, min_size=(300, 200))
    try:
        _press_right_edge(qapp, window, filt, handle, native=False)
        assert filt._manual_edges & int(Qt.Edge.RightEdge.value)
        filt._update_manual_resize(
            QPoint(filt._manual_origin.x() - 500, filt._manual_origin.y())
        )
        qapp.processEvents()
        # Frame floor = 300 content + 2*8 band (old code clamped to 300).
        assert window.width() == 316
        assert window.height() == 216
    finally:
        filt.end_manual_resize()
        window.deleteLater()


def test_manual_resize_clamps_to_content_frame_max(qapp):
    window, filt, handle = _banded_window(
        qapp, band=8, min_size=(300, 200), max_size=(400, 300)
    )
    try:
        _press_right_edge(qapp, window, filt, handle, native=False)
        filt._update_manual_resize(
            QPoint(filt._manual_origin.x() + 500, filt._manual_origin.y())
        )
        qapp.processEvents()
        # Frame ceiling = 400 content + 2*8 band (old code clamped to 400).
        assert window.width() == 416
    finally:
        filt.end_manual_resize()
        window.deleteLater()


def test_native_release_clamps_to_content_limits(qapp):
    """Native/manual parity: a native drag ending out of bounds is
    reconciled to the same content-frame limits on release."""
    window, filt, handle = _banded_window(qapp, band=8, min_size=(300, 200))
    try:
        _press_right_edge(qapp, window, filt, handle, native=True)
        assert filt._native_resizing
        # Compositor shrank the frame below the content minimum.
        from PySide6.QtWidgets import QWidget as _QWidget

        geo = window.geometry()
        _QWidget.setGeometry(window, QRect(geo.x(), geo.y(), 200, 150))
        qapp.processEvents()
        release_at = QPoint(window.width() // 2, 60)
        release = _mouse_event(
            QMouseEvent.Type.MouseButtonRelease,
            release_at,
            window.mapToGlobal(release_at),
        )
        assert filt.eventFilter(window, release) is True
        assert not filt._native_resizing
        assert window.width() == 316
        assert window.height() == 216
    finally:
        window.deleteLater()


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


def test_titlebar_press_attempts_system_move_first(qapp, monkeypatch):
    """The system move starts on PRESS (Wayland binds the press serial);
    while it owns the drag, app-level moves are ignored."""
    window, bar, local = _drag_bar(qapp)
    try:
        calls = []
        monkeypatch.setattr(
            window.windowHandle(),
            "startSystemMove",
            lambda: calls.append(1) or True,
        )
        before = window.pos()
        bar.mousePressEvent(
            _mouse_event(
                QMouseEvent.Type.MouseButtonPress, local, bar.mapToGlobal(local)
            )
        )
        assert calls, "press must attempt startSystemMove"
        assert bar._drag_system_move is True
        bar.mouseMoveEvent(
            _mouse_event(
                QMouseEvent.Type.MouseMove,
                local + QPoint(40, 20),
                bar.mapToGlobal(local) + QPoint(40, 20),
            )
        )
        assert window.pos() == before, "compositor owns the drag: no manual move"
        bar.mouseReleaseEvent(
            _mouse_event(
                QMouseEvent.Type.MouseButtonRelease,
                local,
                bar.mapToGlobal(local),
                buttons=Qt.MouseButton.NoButton,
            )
        )
        assert bar._drag_system_move is False
    finally:
        window.deleteLater()
        bar.deleteLater()


def test_titlebar_manual_drag_moves_by_exact_delta(qapp, monkeypatch):
    """System move unavailable → manual path moves by the exact delta
    (screen-move stability: no teleport, no scaling)."""
    window, bar, local = _drag_bar(qapp)
    try:
        monkeypatch.setattr(window.windowHandle(), "startSystemMove", lambda: False)
        origin = bar.mapToGlobal(local)
        bar.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, local, origin)
        )
        assert bar._drag_system_move is False
        before = window.pos()
        bar.mouseMoveEvent(
            _mouse_event(
                QMouseEvent.Type.MouseMove, local + QPoint(30, 12), origin + QPoint(30, 12)
            )
        )
        assert window.pos() == before + QPoint(30, 12)
    finally:
        window.deleteLater()
        bar.deleteLater()


def test_titlebar_drag_unmaximize_reanchors_without_teleport(qapp):
    """Press-drag on a maximized window restores it but does NOT apply the
    pending delta (the restored rect rarely sits under the cursor)."""
    window, bar, local = _drag_bar(qapp)
    try:
        window.showMaximized()
        qapp.processEvents()
        assert window.isMaximized()
        origin = bar.mapToGlobal(local)
        bar.mousePressEvent(
            _mouse_event(QMouseEvent.Type.MouseButtonPress, local, origin)
        )
        anchored = window.pos()
        bar.mouseMoveEvent(
            _mouse_event(
                QMouseEvent.Type.MouseMove, local + QPoint(50, 30), origin + QPoint(50, 30)
            )
        )
        assert not window.isMaximized(), "drag restores the window"
        assert window.pos() == anchored, "no teleport on un-maximize"
    finally:
        window.deleteLater()
        bar.deleteLater()


def test_mask_sync_coalesces_resize_stream(qapp):
    """N deferred syncs in one burst rebuild masks once; immediate stays sync."""
    _register_palettes(qapp)
    dialog = QDialog()
    QVBoxLayout(dialog)
    WindowChrome.install(dialog, config=WindowChromeConfig(title="Hi"))
    try:
        with patch.object(csd_helpers, "_mask_edge_hosts") as spy:
            for _ in range(5):
                sync_csd_chrome(dialog, defer_mask=True)
            assert spy.call_count == 0, "deferred: nothing synchronous"
            qapp.processEvents()
            qapp.processEvents()
            assert spy.call_count == 1, "one burst → one rebuild"
            sync_csd_chrome(dialog)
            sync_csd_chrome(dialog)
            assert spy.call_count == 3, "immediate path stays synchronous"
    finally:
        dialog.deleteLater()


def test_mask_uses_logical_geometry_at_any_dpr(qapp):
    """Corner masks are DPR-safe: logical rect in, clipped mask out at
    dpr 1 and 2 (masks sit at physical pixels, geometry stays logical)."""
    for dpr in (1.0, 2.0):
        child = QWidget()
        child.resize(100, 50)
        child.devicePixelRatioF = lambda: dpr  # type: ignore[method-assign]
        apply_top_rounded_mask(child, radius=10.0)
        assert not child.mask().isEmpty(), f"mask must clip at dpr={dpr}"
        child.deleteLater()


def test_mask_edge_hosts_clips_corner_children(qapp):
    """A child reaching a corner zone gets a real (non-empty) mask."""
    _register_palettes(qapp)
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    dialog.resize(200, 150)
    child = QWidget(dialog)
    child.setGeometry(0, 0, 200, 60)  # reaches both top corners
    layout.addWidget(child)
    dialog.show()
    qapp.processEvents()
    try:
        _mask_edge_hosts(dialog, radius=10.0, squared=False)
        assert not child.mask().isEmpty()
    finally:
        dialog.deleteLater()


def test_move_keeps_relative_chrome_geometry(qapp):
    """Screen moves need no re-sync: the bar/body ride with the window."""
    _register_palettes(qapp)
    dialog = QDialog()
    QVBoxLayout(dialog)
    dialog.resize(300, 200)
    WindowChrome.install(dialog, config=WindowChromeConfig(title="Hi"))
    dialog.show()
    qapp.processEvents()
    try:
        bar_geo = dialog._csd_title_bar.geometry()
        dialog.move(dialog.pos() + QPoint(60, 40))
        qapp.processEvents()
        assert dialog._csd_title_bar.geometry() == bar_geo
    finally:
        dialog.deleteLater()
