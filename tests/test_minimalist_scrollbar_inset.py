"""OverlayScrollArea's reported width is a single fixed value — the bar's
maximum width plus a small margin — regardless of the thumb's state."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import OverlayScrollArea, overlay_scrollbar_max_inset


def _make_scrolling_area(qtbot) -> tuple[OverlayScrollArea, QWidget]:
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)

    area = OverlayScrollArea(host)
    qtbot.addWidget(area)
    area.set_reserve_scrollbar_space(False)
    area.setGeometry(0, 0, 300, 200)

    content = QWidget()
    content.setMinimumHeight(600)  # overflows the 200px viewport
    area.setWidget(content)

    host.show()  # children created before show() become visible with it
    qtbot.wait(30)  # native range -> custom bar visibility sync is deferred
    return area, host


def test_inset_is_fixed_max_width_plus_margin(qtbot):
    area, _host = _make_scrolling_area(qtbot)

    bar = area.custom_v_scrollbar
    assert bar.isVisible()

    expected = overlay_scrollbar_max_inset()
    assert area.overlay_scrollbar_inset() == expected

    # The value is stable across the thumb's states — no live switching.
    bar.setHoverActive(True)
    assert area.overlay_scrollbar_inset() == expected
    bar._is_dragging = True
    assert area.overlay_scrollbar_inset() == expected
    bar._is_dragging = False
    bar.setHoverActive(False)
    assert area.overlay_scrollbar_inset() == expected


def test_bar_keeps_fixed_width(qtbot):
    area, _host = _make_scrolling_area(qtbot)

    bar = area.custom_v_scrollbar
    assert bar.width() == area._scrollbar_width
    assert bar.x() == area.width() - area._scrollbar_width

    bar.setHoverActive(True)
    assert bar.width() == area._scrollbar_width
    bar._is_dragging = True
    assert bar.width() == area._scrollbar_width


def test_inset_collapses_when_nothing_overflows(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)

    area = OverlayScrollArea(host)
    qtbot.addWidget(area)
    area.set_reserve_scrollbar_space(False)
    area.setGeometry(0, 0, 300, 200)
    content = QWidget()
    content.setMinimumHeight(100)  # fits the viewport
    area.setWidget(content)
    host.show()
    qtbot.wait(30)

    assert not area.custom_v_scrollbar.isVisible()
    assert area.overlay_scrollbar_inset() == 0


def test_reserve_mode_reports_nothing(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)

    area = OverlayScrollArea(host)
    qtbot.addWidget(area)
    area.set_reserve_scrollbar_space(True)
    area.setGeometry(0, 0, 300, 200)
    content = QWidget()
    content.setMinimumHeight(600)
    area.setWidget(content)
    host.show()
    qtbot.wait(30)

    bar = area.custom_v_scrollbar
    assert bar.isVisible()
    # Reserve mode gives the bar its own viewport margin — the overlay inset
    # reports nothing and the bar keeps its fixed width.
    assert area.overlay_scrollbar_inset() == 0
    assert bar.width() == area._scrollbar_width
    bar.setHoverActive(True)
    assert bar.width() == area._scrollbar_width
    assert area.overlay_scrollbar_inset() == 0
