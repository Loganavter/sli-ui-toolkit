"""FlyoutManager: pinned=True persistent-HUD flyouts."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout


def _press_at(host: QWidget, global_pos) -> QMouseEvent:
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(host.mapFromGlobal(global_pos)),
        QPointF(global_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_pinned_flyout_survives_outside_click(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        anchor = QWidget(host)
        anchor.setGeometry(10, 10, 60, 40)
        anchor.show()

        hud = BaseFlyout(host, pinned=True)
        hud.show_aligned(anchor, "bottom-left", "top-left", offset=4)
        assert hud.isVisible()

        far = host.mapToGlobal(QPoint(host.width() - 2, host.height() - 2))
        manager.eventFilter(host, _press_at(host, far))
        assert hud.isVisible()

        hud.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_pinned_flyout_survives_anchor_move(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        anchor = QWidget(host)
        anchor.setGeometry(10, 10, 60, 40)
        anchor.show()

        hud = BaseFlyout(host, pinned=True)
        hud.show_aligned(anchor, "bottom-left", "top-left", offset=4)
        assert hud.isVisible()

        anchor.setGeometry(20, 60, 60, 40)
        manager._close_flyouts_with_moved_anchors()
        assert hud.isVisible()

        hud.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_pinned_flyout_does_not_dismiss_or_steal_active(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        real_anchor = QWidget(host)
        real_anchor.setGeometry(10, 10, 60, 40)
        real_anchor.show()
        real = BaseFlyout(host)
        real.show_aligned(real_anchor, "bottom-left", "top-left", offset=4)
        assert real.isVisible()
        assert manager.get_active_flyout() is real

        hud_anchor = QWidget(host)
        hud_anchor.setGeometry(200, 200, 60, 40)
        hud_anchor.show()
        hud = BaseFlyout(host, pinned=True)
        hud.show_aligned(hud_anchor, "bottom-left", "top-left", offset=4)

        assert real.isVisible()
        assert manager.get_active_flyout() is real

        # Reposition (e.g. from a resize handler) must not disturb it either.
        hud.reposition()
        assert real.isVisible()
        assert manager.get_active_flyout() is real

        hud.deleteLater()
        real.deleteLater()
        hud_anchor.deleteLater()
        real_anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_close_all_still_closes_pinned_flyout(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        anchor = QWidget(host)
        anchor.setGeometry(10, 10, 60, 40)
        anchor.show()

        hud = BaseFlyout(host, pinned=True)
        hud.show_aligned(anchor, "bottom-left", "top-left", offset=4)
        assert hud.isVisible()

        manager.close_all()
        assert not hud.isVisible()

        hud.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_reposition_tracks_anchor_move(qapp):
    host = QWidget()
    host.resize(400, 300)
    host.show()

    anchor = QWidget(host)
    anchor.setGeometry(10, 10, 60, 40)
    anchor.show()

    hud = BaseFlyout(host, pinned=True)
    hud.show_aligned(anchor, "bottom-left", "top-left", offset=4)
    first_pos = hud.pos()

    anchor.setGeometry(10, 120, 60, 40)
    hud.reposition()
    assert hud.pos() != first_pos
    assert hud.pos().y() > first_pos.y()

    hud.deleteLater()
    anchor.deleteLater()
    host.deleteLater()
