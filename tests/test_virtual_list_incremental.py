"""Incremental virtual-list rebinding tests.

Scrolling must not re-run ``bind()`` for rows that stay in the window —
only rows entering the window are bound; the rest are repositioned.
Data-changing rebinds (``rebind(force=True)``, ``set_count``) still bind
every window row so fresh item data always reaches the rows.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.virtual_list import RowPool, VirtualListController


def _make_controller(qtbot, count=100, row_height=30, viewport_h=200):
    area = OverlayScrollArea()
    qtbot.addWidget(area)
    host = QWidget()
    area.setWidget(host)
    host.resize(300, viewport_h)
    area.resize(300, viewport_h)
    area.show()

    bound: list[int] = []

    def factory() -> QLabel:
        return QLabel("")

    def bind(index: int, widget: QWidget) -> None:
        bound.append(index)
        widget.setText(f"item-{index}")

    ctrl = VirtualListController(
        area, host, factory=factory, bind=bind, row_height=row_height
    )
    ctrl.set_count(count)
    return area, ctrl, bound


def test_initial_rebind_binds_only_window(qtbot):
    area, ctrl, bound = _make_controller(qtbot)
    assert ctrl.count == 100
    start, end = ctrl.window()
    assert end - start == len(bound)  # exactly the window rows materialized
    assert bound == list(range(start, end))


def test_scroll_binds_only_entering_rows(qtbot):
    area, ctrl, bound = _make_controller(qtbot)
    initial = len(bound)
    area.verticalScrollBar().setValue(5 * 30)
    qtbot.wait(20)
    start, end = ctrl.window()
    # Window [3, 14): rows 3..8 were already bound and must be reused;
    # only rows 9..13 (entering) get bind() re-run.
    assert start == 3 and end == 14
    assert len(bound) == initial + 5
    assert bound[-5:] == list(range(9, 14))


def test_kept_rows_are_repositioned(qtbot):
    area, ctrl, bound = _make_controller(qtbot)
    area.verticalScrollBar().setValue(5 * 30)
    qtbot.wait(20)
    for idx in range(3, 14):
        widget = ctrl.widget_for_index(idx)
        assert widget is not None
        assert widget.geometry().y() == idx * 30 - 150
        assert widget.text() == f"item-{idx}"


def test_scroll_back_reuses_rows(qtbot):
    area, ctrl, bound = _make_controller(qtbot)
    area.verticalScrollBar().setValue(10 * 30)
    qtbot.wait(20)
    area.verticalScrollBar().setValue(0)
    qtbot.wait(20)
    # Optimal pool: every index that ever enters the window is bound exactly
    # once — 9 (initial window) + 10 (rows 9..18) + 8 (rows 0..7 re-entering
    # after their slots were recycled). No window-sized re-bind on scroll.
    assert len(bound) == 9 + 10 + 8


def test_force_rebind_refreshes_every_row(qtbot):
    area, ctrl, bound = _make_controller(qtbot)
    area.verticalScrollBar().setValue(5 * 30)
    qtbot.wait(20)
    before = len(bound)
    ctrl.rebind(force=True)
    start, end = ctrl.window()
    assert len(bound) == before + (end - start)


def test_set_count_with_same_count_forces(qtbot):
    area, ctrl, bound = _make_controller(qtbot)
    area.verticalScrollBar().setValue(5 * 30)
    qtbot.wait(20)
    before = len(bound)
    ctrl.set_count(100)  # same count: item data may have changed
    start, end = ctrl.window()
    assert len(bound) == before + (end - start)


def test_pool_reuse_false_full_rebind_every_time(qtbot):
    """The default (ComboBox dropdown) path must keep full rebinding —
    its bind index is positional, so reusing would show stale rows."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 200)
    bound: list[int] = []
    pool = RowPool(host, factory=lambda: QLabel(""))
    pool.rebind(0, 5, lambda idx, w: bound.append(idx), row_height=30)
    pool.rebind(1, 6, lambda idx, w: bound.append(idx), row_height=30, reuse=False)
    assert bound == [0, 1, 2, 3, 4, 1, 2, 3, 4, 5]