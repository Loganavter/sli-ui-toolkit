"""FlyoutManager show-policy coexistence (toolkit + app wiring)."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import (
    FlyoutManager,
    GroupShowPolicy,
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction


def test_context_menu_and_unified_list_group_tags():
    from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import (
        SimpleOptionsFlyout,
    )
    from sli_ui_toolkit.ui.widgets.composite.unified_flyout import UnifiedFlyout

    assert ContextMenu.flyout_group == "context_menu"
    assert UnifiedFlyout.flyout_group == "unified_list"
    assert SimpleOptionsFlyout.flyout_group == "options"


def test_base_flyout_registers_and_close_if_outside(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        flyout = BaseFlyout(host)
        flyout.flyout_group = "options"
        flyout.setGeometry(40, 40, 100, 80)
        assert flyout in manager._registered_flyouts

        flyout.show()
        assert manager.get_active_flyout() is flyout
        assert flyout.isVisible()

        from PySide6.QtCore import QPoint

        # Corner of the host — outside the flyout body.
        far = host.mapToGlobal(QPoint(host.width() - 1, host.height() - 1))
        if flyout.contains_global(far):
            far = host.mapToGlobal(QPoint(0, 0))
        assert not flyout.contains_global(far)
        assert manager.close_if_outside(far) is True
        assert not flyout.isVisible()

        flyout.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_anchor_dismiss_suppresses_button_click(qapp):
    """Closing via anchor press must not let Button.clicked reopen the flyout."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF
    from sli_ui_toolkit.widgets import Button

    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        anchor = Button("Open", parent=host)
        anchor.setGeometry(10, 10, 80, 32)
        anchor.show()

        flyout = BaseFlyout(host)
        flyout._anchor_widget = anchor
        flyout.setGeometry(10, 50, 120, 80)
        flyout.show()
        assert manager.get_active_flyout() is flyout

        clicks: list[int] = []
        anchor.clicked.connect(lambda: clicks.append(1))

        # Simulate FlyoutManager's anchor-dismiss path.
        center = anchor.mapToGlobal(anchor.rect().center())
        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(anchor.rect().center()),
            center,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        manager.eventFilter(host, press)
        assert not flyout.isVisible()
        assert getattr(anchor, "_suppress_next_click", False) is True

        anchor._emit_click_signals()
        assert clicks == []
        assert getattr(anchor, "_suppress_next_click", False) is False

        flyout.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_label_follows_application_font_family(qapp):
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

    app = QApplication.instance()
    previous = QFont(app.font())
    try:
        baked = QFont("Sans Serif")
        baked.setPixelSize(13)
        app.setFont(QFont("Monospace"))

        label = Label("Hello", pixel_size=13)
        # Simulate old bug: label already had a system face baked in.
        label.setFont(baked)
        label._apply_style()
        assert label.font().family() == app.font().family()
        assert label.font().pixelSize() == 13
        # Color must not be applied via stylesheet (that makes Qt ignore setFont).
        assert "color:" not in (label.styleSheet() or "").lower()
        label.deleteLater()
    finally:
        app.setFont(previous)


def test_title_bar_title_keeps_app_font_without_qss_color(qapp):
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar

    app = QApplication.instance()
    previous = QFont(app.font())
    previous_ss = app.styleSheet()
    try:
        app.setFont(QFont("Monospace", 12))
        # Former app.qss rule that forced stylesheet painting on the title.
        app.setStyleSheet(
            "QLabel#CustomTitleBarTitle { color: #1f1f1f; background: transparent; }"
        )
        bar = CustomTitleBar(title="Improve ImgSLI")
        label = bar._title_label
        # Clear the app rule like production app.qss now does, then restyle.
        app.setStyleSheet("")
        label._apply_style()
        assert label.font().family() == app.font().family()
        assert label.font().pixelSize() == 16
        assert not (label.styleSheet() or "").strip()
        bar.deleteLater()
    finally:
        app.setFont(previous)
        app.setStyleSheet(previous_ss)


def test_group_policy_keeps_list_open_when_menu_shows(qapp):
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        policy = GroupShowPolicy()
        policy.configure_group("context_menu", dismisses=(), claim_active=False)
        manager.set_show_policy(policy)

        host = QWidget()
        host.resize(400, 300)
        host.show()

        listing = BaseFlyout(host)
        listing.flyout_group = "unified_list"
        listing.setGeometry(10, 10, 120, 80)
        listing.show()
        assert listing.isVisible()
        assert manager.get_active_flyout() is listing

        menu = ContextMenu(
            host,
            entries=(ContextMenuAction("x.remove", "Remove"),),
        )
        menu.popup_at(host.mapToGlobal(host.rect().center()))

        assert menu.isVisible()
        assert listing.isVisible()
        assert manager.get_active_flyout() is listing

        menu.hide()
        listing.hide()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_per_flyout_override_can_dismiss_only_one_group():
    policy = GroupShowPolicy()
    policy.configure_group("context_menu", dismisses=(), claim_active=False)
    special = SimpleNamespace(flyout_group="special")
    other_list = SimpleNamespace(flyout_group="unified_list")
    other_picker = SimpleNamespace(flyout_group="pickers")
    policy.configure_flyout(special, dismisses=("unified_list",), claim_active=True)

    assert policy.should_dismiss(special, other_list) is True
    assert policy.should_dismiss(special, other_picker) is False
    assert policy.should_dismiss(
        SimpleNamespace(flyout_group="context_menu"), other_list
    ) is False
