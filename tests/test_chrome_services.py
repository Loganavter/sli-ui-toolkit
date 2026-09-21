"""Chrome services: prewarm visibility guard, icon negative cache, drag-drop
stacking/signal/hygiene, title-bar cluster arrow fallthrough.

Covers task-fix-toolkit-chrome-services-2026-09-20. The title-bar arrow case
touches ``custom_title_bar/widget.py`` (shared with the wave-2 lifecycle
task) — behavior-only change at the cluster ends, no lifecycle wiring.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QPushButton, QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, CustomTitleBar, ThemeManager
from sli_ui_toolkit.ui.services import dragdrop_service as dd_module
from sli_ui_toolkit.ui.services import icon_service as icon_module
from sli_ui_toolkit.ui.services.dragdrop_service import ToolkitDragDropService
from sli_ui_toolkit.ui.services.icon_service import IconService, get_icon_service
from sli_ui_toolkit.ui.services.window_prewarm import (
    prewarm_widget_window,
    prewarm_widget_window_once,
    reset_prewarm_once,
)


def _mouse_press(pos: QPointF = QPointF(5, 5)) -> QMouseEvent:
    from PySide6.QtCore import Qt

    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _register_palettes(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("dark", qapp)


# -- prewarm ---------------------------------------------------------------

def test_prewarm_hidden_widget_stays_hidden(qapp):
    w = QWidget()
    assert not w.isVisible()
    prewarm_widget_window(qapp, w)
    qapp.processEvents()
    assert not w.isVisible()
    w.deleteLater()


def test_prewarm_visible_widget_stays_visible(qapp):
    w = QWidget()
    w.show()
    qapp.processEvents()
    assert w.isVisible()
    prewarm_widget_window(qapp, w)
    qapp.processEvents()
    assert w.isVisible()
    w.deleteLater()


def test_prewarm_once_flag_lifecycle(qapp):
    w = QWidget()
    try:
        assert prewarm_widget_window_once(qapp, w) is True
        assert prewarm_widget_window_once(qapp, w) is False
        reset_prewarm_once(w)
        assert prewarm_widget_window_once(qapp, w) is True
    finally:
        w.deleteLater()


# -- icon service ----------------------------------------------------------

def _write_svg(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"></svg>'
    )


def test_icon_negative_cache_records_miss(qapp, tmp_path):
    svc = IconService(str(tmp_path))
    icon = svc.get_icon("nope-missing", is_dark=True)
    assert icon.isNull()
    assert ("nope-missing.svg", True) in svc._miss_cache


def test_icon_first_root_revisit_recovers_new_file(qapp, tmp_path):
    svc = IconService(str(tmp_path))
    assert svc.get_icon("late-icon", is_dark=True).isNull()
    # Icon lands in the primary (first, dark/) root after the miss: the next
    # lookup must resolve it even though the negative entry is still fresh.
    _write_svg(tmp_path / "resources" / "assets" / "icons" / "dark" / "late-icon.svg")
    assert not svc.get_icon("late-icon", is_dark=True).isNull()
    assert ("late-icon.svg", True) not in svc._miss_cache


def test_icon_negative_ttl_expiry_reprobes_other_roots(qapp, tmp_path):
    svc = IconService(str(tmp_path), negative_ttl_s=0)
    assert svc.get_icon("slow-icon", is_dark=True).isNull()
    # Non-primary root: only a TTL-expired re-probe finds it (ttl=0 here).
    _write_svg(tmp_path / "resources" / "assets" / "icons" / "light" / "slow-icon.svg")
    assert not svc.get_icon("slow-icon", is_dark=True).isNull()


def test_icon_negative_entry_sticky_within_ttl(qapp, tmp_path):
    svc = IconService(str(tmp_path), negative_ttl_s=3600)
    assert svc.get_icon("sticky-icon", is_dark=True).isNull()
    # Lands in a non-primary root while the negative entry is fresh: no
    # re-probe happens (first-root revisit only covers dark/), so the miss
    # entry survives and the stat storm stays skipped.
    _write_svg(tmp_path / "resources" / "assets" / "icons" / "light" / "sticky-icon.svg")
    svc.get_icon("sticky-icon", is_dark=True)
    assert ("sticky-icon.svg", True) in svc._miss_cache
    svc.invalidate("sticky-icon", is_dark=True)
    assert ("sticky-icon.svg", True) not in svc._miss_cache
    assert not svc.get_icon("sticky-icon", is_dark=True).isNull()


def test_get_icon_service_explicit_root_revisits(qapp, tmp_path):
    name = "test-revisit-proj"
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    try:
        first = get_icon_service(name, project_root=str(root_a))
        assert first.project_root == root_a
        second = get_icon_service(name, project_root=str(root_b))
        assert second.project_root == root_b
        # No explicit root: existing entry reused.
        assert get_icon_service(name) is second
    finally:
        icon_module._services.pop(name, None)


# -- drag-drop -------------------------------------------------------------

def test_busy_drag_signal(qapp):
    svc = ToolkitDragDropService()
    states: list[bool] = []
    svc.drag_state_changed.connect(states.append)

    class Src(QWidget):
        list_num = 1
        index = 0

    src = Src()
    try:
        svc.start_drag(src, _mouse_press())
        assert states == [True]
        svc.cancel_drag()
        assert states == [True, False]
    finally:
        src.deleteLater()


def test_stacking_aware_target_pick(qapp, qtbot):
    svc = ToolkitDragDropService()

    class Target(QWidget):
        pass

    host = QWidget()
    host.resize(200, 200)
    host.show()
    qtbot.addWidget(host)
    bottom = Target(parent=host)
    bottom.resize(100, 100)
    bottom.move(0, 0)
    bottom.show()
    top = Target(parent=host)
    top.resize(100, 100)
    top.move(0, 0)
    top.show()
    top.raise_()
    qapp.processEvents()
    # Registration order disagrees with stacking: bottom registered last, but
    # the raised (topmost) widget must still win.
    svc.register_drop_target(top)
    svc.register_drop_target(bottom)
    try:
        probe = QPointF(top.mapToGlobal(top.rect().center()))
        assert svc._target_at(probe) is top
    finally:
        host.deleteLater()
        qapp.processEvents()


def test_unregister_dead_target_is_safe(qapp, qtbot):
    svc = ToolkitDragDropService()
    tgt = QWidget()
    tgt.show()
    svc.register_drop_target(tgt)
    assert tgt in svc._drop_targets
    tgt.deleteLater()
    qapp.processEvents()
    from PySide6.QtCore import QEvent as _QEvent

    qapp.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    qapp.processEvents()
    # Must not raise, and the dead entry must be purged on next mutation.
    svc.unregister_drop_target(tgt)
    live = QWidget()
    svc.register_drop_target(live)
    try:
        assert all(t is live for t in svc._drop_targets)
    finally:
        live.deleteLater()


def test_target_at_snapshot_survives_mid_iter_unregister(qapp, qtbot):
    """Dead targets unregistered during _target_at must not skip entries."""
    svc = ToolkitDragDropService()
    host = QWidget()
    host.resize(300, 100)
    host.show()
    qtbot.addWidget(host)
    targets = []
    for i in range(3):
        t = QWidget(parent=host)
        t.resize(100, 100)
        t.move(i * 100, 0)
        t.show()
        targets.append(t)
        svc.register_drop_target(t)
    qapp.processEvents()
    targets[0].deleteLater()
    qapp.processEvents()
    from PySide6.QtCore import QEvent as _QEvent

    qapp.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    qapp.processEvents()
    try:
        probe = QPointF(targets[2].mapToGlobal(targets[2].rect().center()))
        assert svc._target_at(probe) is targets[2]
    finally:
        host.deleteLater()
        qapp.processEvents()


# -- title-bar cluster arrow fallthrough -----------------------------------

def _key_press(key) -> QKeyEvent:
    from PySide6.QtCore import Qt

    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


def test_cluster_arrow_fallthrough_at_ends(qapp, qtbot):
    from PySide6.QtCore import Qt

    _register_palettes(qapp)
    bar = CustomTitleBar(title="Test")
    bar.resize(400, 36)
    left = QPushButton("A", parent=bar)
    right = QPushButton("B", parent=bar)
    left.move(10, 5)
    right.move(120, 5)
    bar.show()
    qtbot.addWidget(bar)
    qapp.processEvents()
    try:
        assert len(bar._focusable_buttons()) == 2
        # Mid-cluster: Right moves focus and is consumed.
        left.setFocus()
        qapp.processEvents()
        assert qapp.focusWidget() is left
        assert bar.eventFilter(left, _key_press(Qt.Key.Key_Right)) is True
        assert qapp.focusWidget() is right
        # Right end: falls through (not consumed).
        assert bar.eventFilter(right, _key_press(Qt.Key.Key_Right)) is False
        # Left end: falls through (not consumed).
        right.setFocus()
        assert bar.eventFilter(right, _key_press(Qt.Key.Key_Left)) is True
        assert qapp.focusWidget() is left
        assert bar.eventFilter(left, _key_press(Qt.Key.Key_Left)) is False
    finally:
        bar.deleteLater()
        qapp.processEvents()
