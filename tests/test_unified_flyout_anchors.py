from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    SimpleUnifiedFlyoutController,
    SimpleUnifiedFlyoutStore,
    UnifiedFlyout,
)


def test_unified_flyout_uses_explicit_list_anchors(qapp):
    store = SimpleUnifiedFlyoutStore()
    controller = SimpleUnifiedFlyoutController(store)
    host = QWidget()
    left = QWidget(host)
    right = QWidget(host)
    flyout = UnifiedFlyout(store=store, main_controller=controller, main_window=host)
    flyout.set_list_anchors(left, right)

    assert flyout.anchor_for_list(1) is left
    assert flyout.anchor_for_list(2) is right
    assert flyout.anchor_widgets() == (left, right)

    flyout.deleteLater()
    host.deleteLater()


def test_create_double_list_registers_anchors(qapp):
    host = QWidget()
    left = QWidget(host)
    right = QWidget(host)
    flyout = UnifiedFlyout.create_double_list(
        parent_window=host,
        anchor_left=left,
        anchor_right=right,
        left_items=["A"],
        right_items=["B"],
    )

    assert flyout.anchor_for_list(1) is left
    assert flyout.anchor_for_list(2) is right
    assert not hasattr(host, "ui")

    flyout.deleteLater()
    host.deleteLater()
