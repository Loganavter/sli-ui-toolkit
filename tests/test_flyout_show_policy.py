"""FlyoutManager show-policy coexistence (toolkit + app wiring)."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import (
    CallableShowPolicy,
    ChainShowPolicy,
    ExclusiveShowPolicy,
    FlyoutManager,
    GroupShowPolicy,
    flyout_group_of,
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
        # Non-context flyouts must not also arm the context-menu suppress flag.
        assert getattr(anchor, "_suppress_next_context_menu", False) is False

        anchor._emit_click_signals()
        assert clicks == []
        assert getattr(anchor, "_suppress_next_click", False) is False

        flyout.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_context_menu_anchor_dismiss_uses_menu_suppress_only(qapp):
    """Context menus arm ``_suppress_next_context_menu``, not ``_suppress_next_click``."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.managers import FlyoutManager
    from sli_ui_toolkit.ui.widgets.buttons import Button
    from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        manager.set_show_policy(None)
        host = QWidget()
        host.resize(400, 300)
        host.show()

        anchor = Button("File", parent=host)
        anchor.setGeometry(10, 10, 80, 32)
        anchor.show()

        flyout = BaseFlyout(host)
        flyout.flyout_group = "context_menu"
        flyout._anchor_widget = anchor
        flyout.setGeometry(10, 50, 120, 80)
        flyout.show()

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
        assert getattr(anchor, "_suppress_next_context_menu", False) is True
        assert getattr(anchor, "_suppress_next_click", False) is False

        flyout.deleteLater()
        anchor.deleteLater()
        host.deleteLater()
    finally:
        manager.set_show_policy(previous)


def test_emit_click_signals_clears_paired_context_menu_suppress(qapp):
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.widgets.buttons import Button

    host = QWidget()
    anchor = Button("File", parent=host)
    anchor._suppress_next_click = True
    anchor._suppress_next_context_menu = True
    clicks: list[int] = []
    anchor.clicked.connect(lambda: clicks.append(1))

    anchor._emit_click_signals()
    assert clicks == []
    assert getattr(anchor, "_suppress_next_click", False) is False
    assert getattr(anchor, "_suppress_next_context_menu", False) is False

    anchor._emit_click_signals()
    assert clicks == [1]

    anchor.deleteLater()
    host.deleteLater()


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


def test_group_inherits_parent_rules_when_unconfigured():
    policy = GroupShowPolicy()
    policy.configure_group("context_menu", dismisses=(), claim_active=False)
    policy.define_group("submenu", parent="context_menu")

    submenu_flyout = SimpleNamespace(flyout_group="submenu")
    other_list = SimpleNamespace(flyout_group="unified_list")

    assert policy.should_dismiss(submenu_flyout, other_list) is False
    assert policy.should_claim_active(submenu_flyout, None) is False


def test_group_inheritance_chain_and_own_override():
    policy = GroupShowPolicy()
    policy.configure_group("context_menu", dismisses=(), claim_active=False)
    policy.define_group("submenu", parent="context_menu")
    # Grandchild overrides claim_active but still inherits dismisses.
    policy.configure_group("submenu_item", parent="submenu", claim_active=True)

    grandchild = SimpleNamespace(flyout_group="submenu_item")
    other_list = SimpleNamespace(flyout_group="unified_list")

    assert policy.should_dismiss(grandchild, other_list) is False
    assert policy.should_claim_active(grandchild, None) is True


def test_unconfigured_group_with_parent_arg_only_does_not_set_own_rules():
    policy = GroupShowPolicy()
    policy.configure_group("base_group", dismisses=(), claim_active=False)
    # No dismisses/claim_active passed here -- must not silently default to
    # DISMISS_ALL/True and shadow the parent link.
    policy.configure_group("child_group", parent="base_group")

    child = SimpleNamespace(flyout_group="child_group")
    other = SimpleNamespace(flyout_group="anything")

    assert policy.should_dismiss(child, other) is False
    assert policy.should_claim_active(child, None) is False


def test_coexists_with_is_symmetric_and_overrides_dismiss_all():
    policy = GroupShowPolicy()
    # Both groups keep default exclusive (dismiss-all) rules otherwise.
    policy.coexists_with("context_menu", "unified_list")

    menu = SimpleNamespace(flyout_group="context_menu")
    listing = SimpleNamespace(flyout_group="unified_list")
    other = SimpleNamespace(flyout_group="options")

    assert policy.should_dismiss(menu, listing) is False
    assert policy.should_dismiss(listing, menu) is False
    # Unrelated groups are unaffected -- still dismiss-all by default.
    assert policy.should_dismiss(menu, other) is True


def test_chain_show_policy_and_combines_dismiss_any_protection_wins():
    protective = GroupShowPolicy()
    protective.coexists_with("context_menu", "unified_list")
    strict = ExclusiveShowPolicy()
    chain = ChainShowPolicy([protective, strict])

    menu = SimpleNamespace(flyout_group="context_menu")
    listing = SimpleNamespace(flyout_group="unified_list")
    other = SimpleNamespace(flyout_group="options")

    # protective says False for this pair -- AND-combine means chain says False
    # even though `strict` (ExclusiveShowPolicy) always says True.
    assert chain.should_dismiss(menu, listing) is False
    # Neither policy protects this pair -- both say True.
    assert chain.should_dismiss(menu, other) is True


def test_chain_show_policy_claim_active_uses_first_policy():
    first = GroupShowPolicy()
    first.configure_group("context_menu", dismisses=(), claim_active=False)
    second = ExclusiveShowPolicy()
    chain = ChainShowPolicy([first, second])

    menu = SimpleNamespace(flyout_group="context_menu")
    assert chain.should_claim_active(menu, None) is False


def test_chain_show_policy_requires_at_least_one_policy():
    try:
        ChainShowPolicy([])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty policy chain")


def test_coexists_with_follows_group_inheritance():
    policy = GroupShowPolicy()
    policy.coexists_with("context_menu", "unified_list")
    policy.define_group("submenu", parent="context_menu")

    submenu = SimpleNamespace(flyout_group="submenu")
    listing = SimpleNamespace(flyout_group="unified_list")

    # submenu declares no coexists_with edges of its own -- must still
    # inherit context_menu's, in both directions.
    assert policy.should_dismiss(submenu, listing) is False
    assert policy.should_dismiss(listing, submenu) is False


def test_coexists_with_inheritance_does_not_leak_to_unrelated_groups():
    policy = GroupShowPolicy()
    policy.coexists_with("context_menu", "unified_list")
    policy.define_group("submenu", parent="context_menu")

    submenu = SimpleNamespace(flyout_group="submenu")
    other = SimpleNamespace(flyout_group="pickers")

    assert policy.should_dismiss(submenu, other) is True


def test_manager_set_show_policy_accepts_a_list():
    manager = FlyoutManager.get_instance()
    previous = manager.show_policy()
    try:
        protective = GroupShowPolicy()
        protective.coexists_with("context_menu", "unified_list")
        manager.set_show_policy([protective, ExclusiveShowPolicy()])
        assert isinstance(manager.show_policy(), ChainShowPolicy)

        menu = SimpleNamespace(flyout_group="context_menu")
        listing = SimpleNamespace(flyout_group="unified_list")
        assert manager.show_policy().should_dismiss(menu, listing) is False
    finally:
        manager.set_show_policy(previous)


def test_chain_show_policy_three_way_composition_matches_realistic_host_stack():
    """Stress the AND-combine contract with a stack shaped like a real host:

    a one-off ``CallableShowPolicy`` for a single app-specific exception,
    layered on top of the toolkit's pre-configured ``GroupShowPolicy``,
    layered on top of the strict fallback -- the "LinkPolicy -> GroupPolicy
    -> fallback" shape from the plan doc, using a callable instead of a
    real link-aware policy since linking is handled by ``FlyoutManager``
    directly rather than through the policy protocol (see
    ``docs/dev/FLYOUT_LAYER_SYSTEM_PLAN.md`` phase 3 vs 4).
    """
    one_off = CallableShowPolicy(
        lambda showing, other: not (
            flyout_group_of(showing) == "special_tool"
            and flyout_group_of(other) == "options"
        )
    )
    group_policy = GroupShowPolicy()
    group_policy.configure_group("context_menu", claim_active=False)
    group_policy.coexists_with("context_menu", "unified_list")
    fallback = ExclusiveShowPolicy()

    chain = ChainShowPolicy([one_off, group_policy, fallback])

    special = SimpleNamespace(flyout_group="special_tool")
    options = SimpleNamespace(flyout_group="options")
    menu = SimpleNamespace(flyout_group="context_menu")
    listing = SimpleNamespace(flyout_group="unified_list")
    other = SimpleNamespace(flyout_group="pickers")

    # one_off protects (special_tool, options) -- wins over fallback's dismiss-all.
    assert chain.should_dismiss(special, options) is False
    # group_policy protects (context_menu, unified_list) via coexists_with.
    assert chain.should_dismiss(menu, listing) is False
    # No policy protects this pair -- all three agree to dismiss.
    assert chain.should_dismiss(special, other) is True
    assert chain.should_dismiss(menu, other) is True

    # claim_active: group_policy is second in the list but context_menu is
    # explicitly configured there; one_off (first) has no group opinion so
    # falls through to its own default (True, since it's a dismiss-only
    # callable) -- confirming priority-order means the FIRST policy's
    # answer wins even when a later policy has a more specific rule.
    assert chain.should_claim_active(menu, None) is True
