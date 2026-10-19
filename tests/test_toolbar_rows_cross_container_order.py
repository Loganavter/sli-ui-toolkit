"""`ToolbarRowsSection` must keep a host's explicit order when rows span containers.

Regression (2026-10-19): the section began sorting its curated ``rows_provider``
list by the rows' GLOBAL centre y. For a host whose rows live in DIFFERENT
containers — the video-editor dialog's form rows, its export tab's SCROLL pane,
the toolbar and the timeline — a scroll pane's rows carry global y values that
interleave with the sibling containers, so the explicit visual order was
destroyed and Improve-ImgSLI's
``test_export_tab_fields_walk_in_visual_order`` /
``test_up_walks_rows_in_visual_order`` went red.

The rule pinned here: sort by y only when every row shares ONE parent (a plain
toolbar/footer, where geometry is the truth); a cross-container layout keeps the
host's order.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection


def _host(qtbot) -> QWidget:
    host = QWidget()
    host.resize(400, 400)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    return host


def test_single_container_rows_are_sorted_by_geometry(qtbot) -> None:
    """One parent: a host that appends rows out of order still navigates visually."""
    host = _host(qtbot)
    target = QWidget(host)
    target.setGeometry(0, 0, 200, 200)
    target.show()
    bottom = QWidget(target)
    top = QWidget(target)
    bottom.setGeometry(0, 40, 120, 20)
    top.setGeometry(0, 0, 120, 20)
    # A freshly created child of a shown parent is hidden until shown, and
    # ``_rows()`` drops hidden rows (its "visible rows" contract).
    bottom.show()
    top.show()
    QApplication.processEvents()

    section = ToolbarRowsSection(lambda: [bottom, top], tag="t")
    assert section._rows() == [top, bottom], "rows in one container were not sorted by y"


def test_cross_container_rows_keep_the_host_order(qtbot) -> None:
    """Different parents (a scroll pane among siblings): the host's order wins."""
    host = _host(qtbot)
    outer = QVBoxLayout(host)
    outer.setContentsMargins(0, 0, 0, 0)
    pane = QScrollArea(host)
    inner = QWidget()
    pane.setWidget(inner)
    pane.setWidgetResizable(True)
    inner_layout = QVBoxLayout(inner)
    pane_row = QWidget(inner)
    inner_layout.addWidget(pane_row)
    sibling = QWidget(host)
    outer.addWidget(sibling)
    outer.addWidget(pane)
    pane_row.show()
    sibling.show()
    QApplication.processEvents()

    section = ToolbarRowsSection(lambda: [pane_row, sibling], tag="t")
    assert section._rows() == [pane_row, sibling], (
        "a cross-container row list was re-sorted by global y — the host's explicit "
        "visual order must win (video-editor dialog regression)"
    )
