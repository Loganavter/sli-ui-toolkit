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
    assert host._content_inset >= host._pane_radius
    host.deleteLater()
