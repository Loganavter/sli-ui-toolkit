"""Anchor-move auto-close: per-flyout opt-out for self-reanchoring shells.

Regression: a host-assembled list picker (plain QWidget re-anchoring itself
on every refresh) was closed by ``FlyoutManager`` whenever an unrelated
layout reflow moved its trigger combos by a pixel (e.g. a rating label
becoming visible after a drag&drop). ``close_on_anchor_move = False`` opts
the flyout out of that close while keeping passive outside-click dismissal.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout


def _move_anchor(anchor: QWidget) -> None:
    anchor.move(anchor.x() + 3, anchor.y() + 2)


def test_anchor_move_closes_regular_flyout(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()
        anchor = QWidget(host)
        anchor.setGeometry(10, 10, 60, 24)
        anchor.show()

        flyout = BaseFlyout(host)
        flyout._anchor_widget = anchor
        flyout.setGeometry(10, 50, 100, 60)
        flyout.show()
        qapp.processEvents()
        assert flyout.isVisible()

        _move_anchor(anchor)
        manager._close_flyouts_with_moved_anchors()

        assert not flyout.isVisible()
        flyout.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_anchor_move_keeps_shell_with_close_on_anchor_move_false(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()
        anchor = QWidget(host)
        anchor.setGeometry(10, 10, 60, 24)
        anchor.show()

        flyout = BaseFlyout(host)
        flyout._anchor_widget = anchor
        flyout.close_on_anchor_move = False
        flyout.setGeometry(10, 50, 100, 60)
        flyout.show()
        qapp.processEvents()
        assert flyout.isVisible()

        _move_anchor(anchor)
        manager._close_flyouts_with_moved_anchors()

        assert flyout.isVisible()
        # Outside-click passive dismissal must still work for the shell.
        assert manager.close_if_outside(host.mapToGlobal(host.rect().topRight() + __import__("PySide6.QtCore", fromlist=["QPoint"]).QPoint(1, 1)))
        assert not flyout.isVisible()

        flyout.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)
