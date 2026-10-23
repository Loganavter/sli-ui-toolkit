from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QTabBar
from PySide6.QtTest import QTest

from sli_ui_toolkit.widgets import AdaptiveTabStrip, CloseButtonPolicy

RS = QTabBar.ButtonPosition.RightSide
WIDE_TITLES = ("Image Compare", "Multi Compare", "Video Editor", "Image Gallery")


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


def test_tab_titles_stay_bound_to_their_index(qapp):
    """Content identity: index i always reports title i.

    The close/geometry suites never checked tab content, so a remap that
    shifted titles between indices (or a stale title after a close) passed.
    """
    strip = _strip(policy=CloseButtonPolicy.ALL)
    titles = ["Alpha", "Beta", "Gamma", "Delta"]
    for title in titles:
        strip.addTab(title)
    strip.resize(900, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()

    def current_titles():
        return [strip.tabText(i) for i in range(strip.count())]

    assert current_titles() == titles

    strip.setCurrentIndex(2)
    qapp.processEvents()
    assert current_titles() == titles

    strip.removeTab(1)
    qapp.processEvents()
    assert current_titles() == ["Alpha", "Gamma", "Delta"]


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


def test_close_slots_follow_scale_change(qapp):
    """Live UiScale change must re-fit close slots to the rescaled buttons.

    Regression: the slot baked its fixed size from the button at creation;
    on scale change the button rescales but the slot did not, so the close
    button stuck out past the tab's right edge and sat vertically off-center.
    """
    from sli_ui_toolkit.managers import UiScale

    previous = UiScale.get_instance().factor()
    try:
        UiScale.get_instance().set_factor(1.0)
        strip = _strip(policy=CloseButtonPolicy.ALL)
        for i in range(3):
            strip.addTab(f"Tab {i}")
        strip.resize(900, 100)
        strip.show()
        qapp.processEvents()

        bar = strip.tab_bar

        def assert_fit(tag):
            for index in range(strip.count()):
                slot = bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
                assert slot is not None, f"{tag}: tab {index} lost its close slot"
                tab_rect = bar._painted_tab_rect(bar.tabRect(index))
                button = slot.button
                btn_right = slot.x() + button.x() + button.width()
                # The close button must sit inside its tab, right-aligned
                # with the tab's painted right edge (margin tolerance).
                assert tab_rect.contains(slot.geometry().center()), (
                    f"{tag}: tab {index} slot center outside tab"
                )
                assert btn_right <= tab_rect.right() + 1, (
                    f"{tag}: tab {index} button right {btn_right} "
                    f"past tab right {tab_rect.right()}"
                )
                assert btn_right >= tab_rect.right() - slot.width() - 3, (
                    f"{tag}: tab {index} button floated left of the tab edge"
                )

        assert_fit("1.0")
        UiScale.get_instance().set_factor(1.5)
        qapp.processEvents()
        assert_fit("1.5")
        UiScale.get_instance().set_factor(1.0)
        qapp.processEvents()
        assert_fit("1.0 back")
    finally:
        UiScale.get_instance().set_factor(previous)


def test_current_tab_stays_visible_when_bar_shrinks(qapp):
    """Live resize must keep the current tab (and its close button) in view.

    Regression: resizeEvent only clamped the scroll offset, so shrinking the
    window could leave the current tab scrolled past the edge with its close
    button off-screen.
    """
    strip = _strip(policy=CloseButtonPolicy.ALL)
    for i in range(10):
        strip.addTab(f"Session {i}")
    strip.resize(900, 60)
    strip.show()
    qapp.processEvents()

    bar = strip.tab_bar
    bar.setCurrentIndex(9)
    qapp.processEvents()
    assert bar.tabRect(9).right() <= bar.width()

    for width in (600, 350, 250):
        strip.resize(width, 60)
        qapp.processEvents()
        rect = bar.tabRect(9)
        assert rect.left() >= 0, f"width {width}: current tab left {rect.left()} < 0"
        assert rect.right() <= bar.width(), (
            f"width {width}: current tab right {rect.right()} > bar {bar.width()}"
        )
        slot = bar.tabButton(9, QTabBar.ButtonPosition.RightSide)
        assert slot is not None and bar.rect().contains(slot.geometry().center()), (
            f"width {width}: close button off-screen"
        )


# -- width regimes: natural → compressed → scrolling (owner report 2026-10-23)


def _wide_strip(qapp) -> AdaptiveTabStrip:
    strip = _strip(policy=CloseButtonPolicy.ALL)
    for title in WIDE_TITLES:
        strip.addTab(title)
    strip.resize(1200, 60)
    strip.show()
    qapp.processEvents()
    return strip


def _bar_chrome(strip: AdaptiveTabStrip, qapp) -> int:
    """Layout width the strip spends outside the tab bar (margins+add button).

    Measured on a deliberately narrow strip, where the bar is squeezed to the
    remaining width instead of sitting at its own sizeHint.
    """
    previous = strip.width()
    strip.resize(150, 60)
    qapp.processEvents()
    chrome = strip.width() - strip.tab_bar.width()
    strip.resize(previous, 60)
    qapp.processEvents()
    return chrome


def _fit_bar(strip: AdaptiveTabStrip, qapp, bar_width: int) -> None:
    """Size the strip so the tab bar itself is exactly *bar_width* wide."""
    chrome = _bar_chrome(strip, qapp)
    strip.resize(bar_width + chrome, 60)
    qapp.processEvents()
    strip.refresh_close_buttons()
    qapp.processEvents()


def _send_wheel(bar, dy: int) -> QWheelEvent:
    pos = QPointF(bar.width() / 2, bar.height() / 2)
    event = QWheelEvent(
        pos,
        QPointF(bar.mapToGlobal(pos.toPoint())),
        QPoint(0, 0),
        QPoint(0, dy),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(bar, event)
    return event


def test_tabs_compress_before_the_bar_starts_scrolling(qapp):
    """Labels shrink to a couple of glyphs before the bar scrolls at all.

    Regression (owner report): the tabs kept their natural width and the bar
    switched to horizontal scrolling as soon as they missed by one pixel.
    """
    strip = _wide_strip(qapp)
    bar = strip.tab_bar
    natural = [bar._natural_tab_width(i) for i in range(bar.count())]
    minimums = [bar._min_tab_width(i) for i in range(bar.count())]
    assert sum(minimums) < sum(natural)

    middle = (sum(natural) + sum(minimums)) // 2
    _fit_bar(strip, qapp, middle)

    widths = [bar.tabRect(i).width() for i in range(bar.count())]
    assert bar._arrows_active is False, "scrolling began while labels could still shrink"
    assert sum(widths) == bar.width(), f"compressed row does not fill the bar: {widths}"
    assert all(m <= w < n for w, n, m in zip(widths, natural, minimums)), (
        f"widths {widths} not inside [{minimums}, {natural})"
    )
    assert [bar.tabText(i) for i in range(bar.count())] == list(WIDE_TITLES)
    # The natural total still drives the close-button policy.
    assert bar.full_tabs_width() == sum(natural)


def test_scroll_arrows_appear_only_when_minimum_widths_overflow(qapp):
    strip = _wide_strip(qapp)
    bar = strip.tab_bar
    natural = [bar._natural_tab_width(i) for i in range(bar.count())]
    minimums = [bar._min_tab_width(i) for i in range(bar.count())]

    _fit_bar(strip, qapp, sum(minimums) + 40)
    assert bar._arrows_active is False, "scroll mode started before the minimum width was reached"
    left, right = bar._arrow_rects()
    assert left.isEmpty() and right.isEmpty()

    _fit_bar(strip, qapp, sum(minimums) - 40)
    assert bar._arrows_active is True
    left, right = bar._arrow_rects()
    assert left.width() > 0 and right.width() > 0
    assert bar._viewport_rect().left() == left.right() + 1
    # Scrolling exists to read full labels, so tabs keep their natural width.
    assert [bar.tabRect(i).width() for i in range(bar.count())] == natural

    current = bar.currentIndex()
    # The left arrow is inert at the start of the row.
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=left.center())
    qapp.processEvents()
    assert bar._scroll_offset == 0
    # The right arrow reveals a whole next tab and never activates anything.
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=right.center())
    qapp.processEvents()
    forward = bar._scroll_offset
    assert forward > 0
    assert bar.currentIndex() == current
    # …and the left arrow now walks back toward the row start.
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=left.center())
    qapp.processEvents()
    assert 0 < bar._scroll_offset < forward
    assert bar.currentIndex() == current
    while bar._scroll_offset > 0:
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=left.center())
        qapp.processEvents()
    assert bar._scroll_offset == 0
    assert bar.currentIndex() == current


def test_wheel_scrolls_the_strip_and_never_activates_a_tab(qapp):
    """The wheel is a scroll gesture on both paths — never a tab switch."""
    strip = _wide_strip(qapp)
    bar = strip.tab_bar
    minimums = [bar._min_tab_width(i) for i in range(bar.count())]

    _fit_bar(strip, qapp, sum(minimums) - 40)
    bar.setCurrentIndex(0)
    qapp.processEvents()
    before_index = bar.currentIndex()
    before_offset = bar._scroll_offset

    accepted = _send_wheel(bar, -120)
    qapp.processEvents()
    assert accepted.isAccepted()
    assert bar._scroll_offset > before_offset
    assert bar.currentIndex() == before_index

    # Without overflow the gesture is still consumed: an ignored wheel reaches
    # the host, where it can be read as "next/previous tab" (the report).
    natural = [bar._natural_tab_width(i) for i in range(bar.count())]
    _fit_bar(strip, qapp, sum(natural) + 10)
    no_overflow = _send_wheel(bar, -120)
    qapp.processEvents()
    assert no_overflow.isAccepted()
    assert bar.currentIndex() == before_index
    assert bar._scroll_offset == 0


def test_close_slots_never_float_over_a_scroll_arrow(qapp):
    strip = _wide_strip(qapp)
    bar = strip.tab_bar
    minimums = [bar._min_tab_width(i) for i in range(bar.count())]
    _fit_bar(strip, qapp, sum(minimums) - 40)
    # Scroll all the way to the end so left-side tabs sit under the gutter.
    for _ in range(bar.count() + 1):
        left, right = bar._arrow_rects()
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=right.center())
        qapp.processEvents()

    viewport = bar._viewport_rect()
    for index in range(bar.count()):
        slot = bar.tabButton(index, RS)
        assert slot is not None, f"tab {index} lost its close slot"
        if slot.isVisible():
            assert viewport.contains(slot.geometry()), (
                f"tab {index} close slot {slot.geometry().getRect()} "
                f"overlaps the arrow gutter {viewport.getRect()}"
            )
