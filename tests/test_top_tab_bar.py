from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.constants import TAB_SPACING
from sli_ui_toolkit.widgets import TopTabBar, TopTabHost, TopTabItem


def test_top_tab_bar_selection(qapp):
    bar = TopTabBar()
    bar.add_item("Standard")
    bar.add_item("Manual")
    bar.add_item("Output")

    assert bar.count() == 3
    assert bar.currentIndex() == -1

    bar.setCurrentIndex(1)
    assert bar.currentIndex() == 1
    assert bar._tabs[1].button.isChecked()
    assert ButtonState.CHECKED in bar._tabs[1].button.region_states("_main")
    assert not bar._tabs[0].button.isChecked()

    bar.setTabText(1, "CLI")
    assert bar.tabText(1) == "CLI"
    bar.deleteLater()


def test_top_tab_bar_set_items(qapp):
    bar = TopTabBar()
    bar.set_items([TopTabItem("A"), ("B", "data-b"), "C"])
    assert bar.count() == 3
    assert bar.tabText(0) == "A"
    assert bar.tabData(1) == "data-b"
    bar.deleteLater()


def test_top_tab_bar_keeps_fixed_gap_for_selection_frame(qapp):
    """Selected folder outline must not crowd neighbours — spacing is fixed."""
    bar = TopTabBar()
    bar.add_item("Standard")
    bar.add_item("Manual CLI")
    bar.add_item("Output")
    bar.add_item("Export log")
    bar.setCurrentIndex(0)
    bar.resize(bar.sizeHint())
    bar.show()
    qapp.processEvents()

    assert bar._layout.spacing() == TAB_SPACING
    gaps = []
    for index in range(1, bar.count()):
        prev = bar._tabs[index - 1].button.geometry()
        curr = bar._tabs[index].button.geometry()
        gaps.append(curr.x() - (prev.x() + prev.width()))
    assert gaps == [TAB_SPACING] * (bar.count() - 1)
    assert bar.sizeHint().width() >= sum(
        tab.button.width() for tab in bar._tabs
    ) + TAB_SPACING * (bar.count() - 1)
    bar.deleteLater()


def test_top_tab_label_is_not_falsely_elided(qapp):
    """Width already includes TAB_H_PAD — paint must not subtract it again."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtCore import Qt

    from sli_ui_toolkit.ui.managers.ui_font import paint_font
    from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.tab_button import TopTabButton

    text = "Ручной ввод CLI"
    button = TopTabButton(text=text, size=(0, 32), variant="top_tab")
    button.setFixedWidth(button.sizeHint().width())
    fm = QFontMetrics(paint_font(button))
    painted = fm.elidedText(
        text,
        Qt.TextElideMode.ElideRight,
        max(0, button.width() - 4),
    )
    assert painted == text
    button.deleteLater()


def test_top_tab_bar_does_not_overlap_when_squeezed(qapp):
    """Narrow parent must clip the strip, never stack Fixed tabs on each other."""
    bar = TopTabBar()
    for label in ("Стандартный", "Ручной ввод CLI", "Вывод", "Логи"):
        bar.add_item(label)
    needed = bar.sizeHint().width()
    assert needed > 200

    bar.resize(200, bar.sizeHint().height())
    bar.show()
    qapp.processEvents()

    assert bar._strip.width() == needed
    for index in range(1, bar.count()):
        prev = bar._tabs[index - 1].button.geometry()
        curr = bar._tabs[index].button.geometry()
        assert curr.x() - (prev.x() + prev.width()) == TAB_SPACING
    bar.deleteLater()


def test_top_tab_host_qtabwidget_api(qapp):
    host = TopTabHost()
    pages = [QLabel(f"page-{i}") for i in range(3)]
    for i, page in enumerate(pages):
        host.addTab(page, f"Tab {i}")

    assert host.count() == 3
    assert host.currentIndex() == 0
    assert host.currentWidget() is pages[0]
    assert host.indexOf(pages[2]) == 2
    assert host.tabText(1) == "Tab 1"

    host.setCurrentIndex(2)
    assert host.pages_stack.currentIndex() == 2
    assert host.currentWidget() is pages[2]

    host.setCurrentWidget(pages[1])
    assert host.currentIndex() == 1

    host.setTabText(1, "Renamed")
    assert host.tabText(1) == "Renamed"
    assert host._labels[1] == "Renamed"

    host.removeTab(0)
    assert host.count() == 2
    assert host.indexOf(pages[1]) == 0
    host.deleteLater()


def test_top_tab_host_selected_cover_maps_via_host(qapp):
    host = TopTabHost()
    pages = [QLabel(f"p{i}") for i in range(2)]
    for i, page in enumerate(pages):
        host.addTab(page, f"T{i}")
    host.resize(320, 240)
    host.show()
    qapp.processEvents()

    cover = host._selected_tab_cover_in_pane(host._pane)
    assert cover is not None
    assert cover.width() > 0
    assert cover.top() == 0
    host.deleteLater()


def test_top_tab_host_applies_rounded_content_clip(qapp):
    host = TopTabHost()
    host.addTab(QLabel("page"), "One")
    host.resize(320, 240)
    host.show()
    qapp.processEvents()
    host._apply_content_clip()

    # Masks were removed — they caused neighbour-framebuffer bleed.
    assert host.pages_stack.mask().isEmpty()


def test_close_policy_disabled_by_default(qapp):
    bar = TopTabBar()
    bar.add_item("One")
    bar.add_item("Two")
    assert bar._tabs[0].close_button is None
    assert bar._tabs[1].close_button is None
    bar.deleteLater()


def test_close_button_emits_tab_close_requested_and_does_not_select(qapp):
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
        CloseButtonPolicy,
    )

    bar = TopTabBar(close_policy=CloseButtonPolicy.ALL)
    bar.add_item("One")
    bar.add_item("Two")
    bar.resize(bar.sizeHint())
    bar.show()
    qapp.processEvents()
    closed = []
    bar.tabCloseRequested.connect(closed.append)

    # close is a real button next to the tab: clicking it closes, not selects
    close0 = bar._tabs[0].close_button
    assert isinstance(close0, QWidget)
    close0.click()
    assert closed == [0]
    assert bar.currentIndex() == -1
    # clicking the tab body selects, no close
    bar._tabs[0].button.click()
    assert closed == [0]
    assert bar.currentIndex() == 0
    bar.deleteLater()


def test_close_buttons_widen_the_strip(qapp):
    from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
        CloseButtonPolicy,
    )

    plain = TopTabBar()
    plain.add_item("One")
    closable = TopTabBar(close_policy=CloseButtonPolicy.ALL)
    closable.add_item("One")
    assert closable._content_width() > plain._content_width()
    assert closable._tabs[0].close_button.width() == closable._close_size
    plain.deleteLater()
    closable.deleteLater()


def test_close_button_lives_inside_the_tab(qapp):
    from PySide6.QtCore import QEvent, QPoint, QPointF
    from PySide6.QtGui import QEnterEvent

    from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
        CloseButtonPolicy,
    )

    bar = TopTabBar(close_policy=CloseButtonPolicy.ALL)
    bar.add_item("One")
    bar.resize(bar.sizeHint())
    bar.show()
    qapp.processEvents()

    tab = bar._tabs[0].button
    close = bar._tabs[0].close_button
    assert close is not None
    # the close button is embedded in the tab, at its right edge
    assert close.parentWidget() is tab
    assert tab.rect().contains(close.geometry().center())
    assert close.geometry().right() <= tab.width() - 4
    # hovering the close button keeps the tab itself hovered
    over_tab = tab.mapToGlobal(QPoint(10, 10))
    qapp.sendEvent(
        close,
        QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(over_tab)),
    )
    assert tab._hovered is True
    qapp.sendEvent(close, QEvent(QEvent.Type.Leave))
    bar.deleteLater()


def test_close_slot_background_follows_bar_state(qapp):
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(
        {
            "surface.background": "#123456",
            "button.toggle.background.hover": "#654321",
            "Window": "#ffffff",
            "dialog.text": "#111111",
        },
        {
            "surface.background": "#abcdef",
            "button.toggle.background.hover": "#fedcba",
            "Window": "#000000",
            "dialog.text": "#dddddd",
        },
    )
    tm.set_theme("light", qapp)

    from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
        CloseButtonPolicy,
    )

    bar = TopTabBar(close_policy=CloseButtonPolicy.ALL)
    bar.add_item("One")
    tab = bar._tabs[0].button
    # unselected, unhovered -> transparent slot
    assert bar.close_slot_background_color_for(tab) is None
    # bar hover -> hover token
    bar._set_hover_index(0)
    assert bar.close_slot_background_color_for(tab).name() == "#654321"
    assert tab._hovered is True
    bar._set_hover_index(-1)
    assert tab._hovered is False
    # selected -> tab background token
    bar.setCurrentIndex(0)
    assert bar.close_slot_background_color_for(tab).name() == "#123456"
    bar.deleteLater()


def _host_with_pages(**kwargs) -> TopTabHost:
    host = TopTabHost(**kwargs)
    for name in ("one", "two"):
        page = QWidget()
        page.setObjectName(name)
        host.addTab(page, name)
    return host


def test_a_host_that_paints_no_pane_keeps_the_page_gutter_without_a_frame(qapp):
    """A pane that paints nothing must not stay in the tree as an empty QFrame.

    RVE's hosts pass `pane_fill_token=None`, `pane_radius=0`, `chrome_inset=0` and `TabStyle(border=False)`: the frame
    painted nothing and its only job was the page gutter (the QSS `padding:5px 10px` the Designer's `QStackedWidget`
    carried). `QStackedLayout` ignores the LAYOUT's margins, but honours the WIDGET's `contentsRect`, so the stack can
    own the gutter itself and the frame goes (owner, 2026-11-23: BlinkTable's tabs have no such level).
    """
    from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.pane import TopTabPane
    from sli_ui_toolkit.widgets import TabStyle

    host = _host_with_pages(pane_fill_token=None, pane_radius=0, chrome_inset=0, pane_inset=(10, 5, 10, 5),
                            tab_style=TabStyle(border=False))
    host.resize(400, 300)
    host.show()
    qapp.processEvents()

    assert host._pane is None, "nothing is painted, so there is no frame to keep"
    assert host.findChild(TopTabPane) is None, "the empty frame must not be in the widget tree"
    assert host.pages_stack.parentWidget() is host, "the page stack is the host's own child"
    margins = host.pages_stack.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (10, 5, 10, 5), (
        "the stack carries the page gutter as its own contents margins")

    page = host.pages_stack.currentWidget()
    assert page.geometry() == host.pages_stack.contentsRect(), (
        f"the page must sit at the stack's contents rect: page {page.geometry().getRect()} vs "
        f"contents {host.pages_stack.contentsRect().getRect()}")
    host.close()


def test_a_host_with_a_pane_surface_keeps_its_frame(qapp):
    """The default host paints the pane (fill token, rounded radius, a border), so its frame stays and insets the pages."""
    from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.pane import TopTabPane

    host = _host_with_pages(pane_inset=(10, 5, 10, 5))
    host.resize(400, 300)
    host.show()
    qapp.processEvents()

    pane = host.findChild(TopTabPane)
    assert pane is not None, "a host with a pane surface must still have its frame"
    assert host.pages_stack.parentWidget() is pane, "with a frame, the stack lives inside it"
    margins = host.pages_stack.contentsMargins()
    assert (margins.left(), margins.top()) == (0, 0), "with a frame the gutter is the frame's layout margins"
    page = host.pages_stack.currentWidget()
    assert page.geometry().getRect() == (0, 0, host.pages_stack.width(), host.pages_stack.height()), (
        f"with a frame the page fills the stack: {page.geometry().getRect()}")
    host.close()
