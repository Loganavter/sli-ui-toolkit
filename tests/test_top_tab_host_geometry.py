"""TopTabHost must be able to reproduce a stock QTabWidget's geometry (flat pane, no chrome inset)."""
from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import TopTabHost


def _host(qapp, **options) -> TopTabHost:
    host = TopTabHost(**options)
    for index in range(3):
        host.addTab(QWidget(), f"tab {index}")
    host.resize(600, 400)
    host.show()
    qapp.processEvents()   # a layout without a pass reports construction-time geometry
    return host


def test_default_keeps_the_rounded_pane_inset(qapp):
    host = _host(qapp)
    assert host.pages_stack.geometry().top() > 0
    assert host.pages_stack.geometry().left() >= 2


def test_flat_geometry_matches_a_stock_tab_widget(qapp):
    host = _host(qapp, tab_height=22, pane_radius=0, pane_inset=0, chrome_inset=0)
    origin = host.pages_stack.mapTo(host, QPoint(0, 0))
    # QTabWidget: the stack starts directly under the tab bar and spans the widget's full width.
    assert (origin.x(), origin.y()) == (0, 22)
    size = host.pages_stack.size()
    assert (size.width(), size.height()) == (host.width(), host.height() - 22)


def test_pane_inset_is_independent_of_the_radius(qapp):
    host = _host(qapp, pane_radius=10, pane_inset=0)
    assert host.pages_stack.geometry().left() == 0
