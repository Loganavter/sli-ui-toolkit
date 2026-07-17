from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabBar
from PySide6.QtTest import QTest

from sli_ui_toolkit.widgets import AdaptiveTabStrip, CloseButtonPolicy


def _strip(*, policy=CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT):
    return AdaptiveTabStrip(
        add_icon="add",
        close_icon="remove",
        close_policy=policy,
        single_tab_closable=True,
    )


def test_add_button_stays_next_to_last_tab(qapp):
    strip = _strip()
    strip.addTab("First")
    strip.addTab("Second")
    strip.resize(900, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    gap = strip.add_button.geometry().left() - strip.tab_bar.geometry().right() - 1
    free_space = strip.contentsRect().right() - strip.add_button.geometry().right()

    assert 0 <= gap <= strip.layout().spacing()
    assert free_space > 100


def test_all_close_buttons_are_shown_only_while_full_tabs_fit(qapp):
    strip = _strip()
    for title in ("First workspace", "Second workspace", "Third workspace"):
        strip.addTab(title)
    strip.setCurrentIndex(1)

    strip.resize(900, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()
    strip.refresh_close_buttons()
    assert all(
        strip.tabButton(index, QTabBar.ButtonPosition.RightSide) is not None
        for index in range(strip.count())
    )

    strip.resize(300, strip.sizeHint().height())
    qapp.processEvents()
    strip.refresh_close_buttons()
    assert [
        strip.tabButton(index, QTabBar.ButtonPosition.RightSide) is not None
        for index in range(strip.count())
    ] == [False, True, False]


def test_single_tab_is_closable(qapp):
    strip = _strip()
    strip.addTab("Only")
    strip.resize(300, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    assert strip.tabButton(0, QTabBar.ButtonPosition.RightSide) is not None


def test_selected_tab_widths_never_change(qapp):
    strip = _strip()
    for title in ("Short", "A much longer workspace", "Third"):
        strip.addTab(title)
    strip.resize(300, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()
    strip.setCurrentIndex(0)
    widths_before = [strip.tabRect(index).width() for index in range(strip.count())]

    strip.setCurrentIndex(2)
    qapp.processEvents()
    widths_after = [strip.tabRect(index).width() for index in range(strip.count())]

    assert widths_after == widths_before


def test_close_slot_emits_current_index(qapp):
    strip = _strip(policy=CloseButtonPolicy.ALL)
    strip.addTab("First")
    strip.addTab("Second")
    strip.resize(500, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()
    requested = []
    strip.tabCloseRequested.connect(requested.append)

    slot = strip.tabButton(1, QTabBar.ButtonPosition.RightSide)
    slot.button.clicked.emit()

    assert requested == [1]


def test_close_button_is_optically_lower_than_slot_center(qapp):
    strip = _strip()
    strip.addTab("Only")
    strip.resize(300, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    slot = strip.tabButton(0, QTabBar.ButtonPosition.RightSide)

    assert slot.button.geometry().center().y() == slot.rect().center().y() + 1


def test_close_button_hover_keeps_parent_tab_hovered(qapp):
    strip = _strip(policy=CloseButtonPolicy.ALL)
    strip.addTab("First")
    strip.addTab("Second")
    strip.resize(500, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    slot = strip.tabButton(1, QTabBar.ButtonPosition.RightSide)
    global_pos = slot.button.mapToGlobal(slot.button.rect().center())

    strip.tab_bar.set_hover_from_global(global_pos)

    assert strip.tab_bar._hover_index == 1


def test_close_slot_and_button_are_transparent_for_hover_layering(qapp):
    strip = _strip(policy=CloseButtonPolicy.ALL)
    strip.addTab("First")
    strip.resize(300, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    slot = strip.tabButton(0, QTabBar.ButtonPosition.RightSide)

    assert slot.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert slot.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
    assert not slot.autoFillBackground()
    assert slot.button.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert slot.button.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
    assert not slot.button.autoFillBackground()


def test_close_button_paints_tab_background_inside_button_pipeline(qapp):
    strip = _strip(policy=CloseButtonPolicy.ALL)
    strip.addTab("First")
    strip.addTab("Second")
    strip.resize(500, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    slot = strip.tabButton(1, QTabBar.ButtonPosition.RightSide)

    assert type(slot.button._painter.layers[0]).__name__ == "_CloseButtonTabBackgroundLayer"


def test_current_tab_close_idle_background_is_transparent(qapp):
    """Close X must not paint toggle.normal over the selected tab until hover."""
    from sli_ui_toolkit.theme import ThemeManager
    from sli_ui_toolkit.ui.widgets.buttons.layers.background import (
        BgResolveParams,
        resolve_button_background,
    )
    from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
    from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant

    strip = _strip(policy=CloseButtonPolicy.ALL)
    strip.addTab("First")
    strip.addTab("Second")
    strip.setCurrentIndex(0)
    strip.resize(500, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    slot = strip.tabButton(0, QTabBar.ButtonPosition.RightSide)
    button = slot.button
    states = frozenset(button.region_states("_main"))
    assert ButtonState.HOVERED not in states

    layers, _ = resolve_button_background(
        BgResolveParams(states=states, variant=get_variant("ghost")),
        ThemeManager.get_instance(),
    )
    assert layers == []


def test_right_click_on_tab_emits_context_menu_requested(qapp):
    strip = _strip(policy=CloseButtonPolicy.ALL)
    strip.addTab("First")
    strip.addTab("Second")
    strip.resize(600, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    requested = []
    strip.tabContextMenuRequested.connect(lambda idx, _pos: requested.append(idx))

    rect = strip.tab_bar.tabRect(0)
    # Pick a point away from the close-slot (right side).
    pos = rect.center()
    pos.setX(rect.left() + rect.width() // 4)

    QTest.mouseClick(strip.tab_bar, Qt.MouseButton.RightButton, pos=pos)
    qapp.processEvents()

    assert requested == [0]


def test_right_click_on_close_button_does_not_emit_context_menu(qapp):
    strip = _strip(policy=CloseButtonPolicy.ALL)
    strip.addTab("First")
    strip.resize(300, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    requested = []
    strip.tabContextMenuRequested.connect(lambda idx, _pos: requested.append(idx))

    slot = strip.tabButton(0, QTabBar.ButtonPosition.RightSide)
    assert slot is not None

    # Right click on the actual close button; parent tab-bar should not
    # produce a context menu request.
    pos = slot.button.rect().center()
    QTest.mouseClick(slot.button, Qt.MouseButton.RightButton, pos=pos)
    qapp.processEvents()

    assert requested == []
