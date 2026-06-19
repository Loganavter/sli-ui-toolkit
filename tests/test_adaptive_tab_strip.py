from PySide6.QtWidgets import QTabBar

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
