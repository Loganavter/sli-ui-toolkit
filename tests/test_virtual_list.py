"""Virtual list engine tests — window math, height cache, pool, controller."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.widgets import (
    MeasuredHeights,
    OverlayScrollArea,
    RowPool,
    VirtualListController,
    max_scroll_px,
    visible_window,
)


# ---------------------------------------------------------------------------
# window math (fixed heights)
# ---------------------------------------------------------------------------

def test_visible_window_at_top():
    assert visible_window(1000, 300, 30, 0) == (0, 10)


def test_visible_window_mid_scroll():
    # scroll 1500px -> first row 50, viewport fits 10 -> window [50, 60)
    assert visible_window(1000, 300, 30, 1500) == (50, 60)


def test_visible_window_clamps_scroll_to_max():
    # scroll beyond max clamps to max -> last visible window
    assert visible_window(1000, 300, 30, 10 ** 9) == (990, 1000)


def test_visible_window_overscan_pads_both_sides():
    assert visible_window(1000, 300, 30, 0, overscan=2) == (0, 12)
    assert visible_window(1000, 300, 30, 1500, overscan=2) == (48, 62)


def test_visible_window_empty_count():
    assert visible_window(0, 300, 30, 0) == (0, 0)


def test_max_scroll_px():
    assert max_scroll_px(1000, 300, 30) == 29700
    assert max_scroll_px(5, 300, 30) == 0  # fits -> nothing scrolls


# ---------------------------------------------------------------------------
# MeasuredHeights (variable heights)
# ---------------------------------------------------------------------------

def test_measured_heights_prefix_math():
    m = MeasuredHeights()
    m.set_count(5)
    for i in range(5):
        m.set_height(i, 10 + i)
    assert m.total() == 60
    assert m.offset_of_index(3) == 33  # 10 + 11 + 12
    assert m.index_at_offset(0) == 0
    assert m.index_at_offset(10) == 1  # row 1 starts at offset 10
    assert m.index_at_offset(22) == 2  # row 2 spans offsets 21..32
    assert m.index_at_offset(60) == 5  # past the end -> clamped


def test_measured_heights_set_count_truncates():
    m = MeasuredHeights()
    m.set_count(5)
    for i in range(5):
        m.set_height(i, 10)
    m.set_count(3)
    assert m.total() == 30
    assert m.max_scroll(0) == 30


def test_measured_heights_visible_window():
    m = MeasuredHeights()
    m.set_count(5)
    for i in range(5):
        m.set_height(i, 10 + i)
    # viewport 30px starting at offset 15 -> covers rows 1,2,3
    assert m.visible_window(30, 15) == (1, 4)
    # overscan extends both sides
    assert m.visible_window(30, 15, overscan=1) == (0, 5)


# ---------------------------------------------------------------------------
# RowPool
# ---------------------------------------------------------------------------

def test_pool_reuses_widgets_and_hides_leftovers(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    created = []

    def factory():
        w = QLabel("x")
        created.append(w)
        return w

    pool = RowPool(host, factory)
    try:
        pool.ensure(3)
        assert len(created) == 3

        bound = []

        def bind(idx, w):
            bound.append((idx, w))

        pool.rebind(10, 13, bind, row_height=20, scroll_offset=100)
        assert len(bound) == 3
        assert bound[0][0] == 10 and bound[1][0] == 11 and bound[2][0] == 12
        # widgets are repositioned inside the host and not hidden
        # (isVisible() also requires the parent chain to be shown, so the
        # host is never shown in this test — check the widget's own state)
        assert all(not w.isHidden() for w in created)
        assert created[0].y() == 10 * 20 - 100
        assert created[1].y() == 11 * 20 - 100

        # shrinking the window hides surplus slots, reuses the same widgets
        bound.clear()
        pool.rebind(10, 11, bind, row_height=20, scroll_offset=100)
        assert len(bound) == 1
        assert not created[0].isHidden()
        assert created[1].isHidden()
        assert created[2].isHidden()
    finally:
        pool.dispose()


def test_pool_dispose_deletes_widgets(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    pool = RowPool(host, lambda: QLabel("x"))
    pool.ensure(2)
    pool.dispose()
    assert pool.widgets() == []
    assert len(host.findChildren(QLabel)) == 0


# ---------------------------------------------------------------------------
# VirtualListController
# ---------------------------------------------------------------------------

def _build_controller(host_widget):
    """Build scroll area + content + controller inside ``host_widget``.

    The host must be created and held by the TEST body (top-level widgets are
    Python-owned: dropping the reference garbage-collects the whole tree).
    """
    scroll = OverlayScrollArea(host_widget)
    scroll.setGeometry(0, 0, 300, 300)
    scroll.setWidgetResizable(True)
    content = QWidget()
    scroll.setWidget(content)
    ctrl = VirtualListController(
        scroll, content, factory=lambda: QLabel("row"),
        bind=lambda i, w: w.setText(f"row-{i}"),
        row_height=30,
    )
    return scroll, content, ctrl


def test_controller_materializes_only_visible_rows(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll, content, ctrl = _build_controller(host)
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(1000)
    ctrl.rebind()
    viewport_h = scroll.viewport().height()
    assert viewport_h >= 0
    # window at scroll 0: [0, ceil(viewport/row_h) + overscan)
    expected = math.ceil(viewport_h / 30) + 2
    live = [w for w in content.findChildren(QLabel) if not w.isHidden()]
    assert len(live) == expected
    assert content.minimumHeight() == 1000 * 30


def test_controller_scroll_rebinds_rows(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll, content, ctrl = _build_controller(host)
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(1000)
    ctrl.rebind()

    def visible_texts():
        return {w.text() for w in content.findChildren(QLabel) if w.isVisible()}

    top = visible_texts()
    assert "row-0" in top

    scroll.verticalScrollBar().setValue(600)  # 20 rows down
    qtbot.wait(10)
    texts = visible_texts()
    assert "row-0" not in texts
    assert any(t.startswith("row-2") for t in texts)


def test_controller_widget_for_index(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll, content, ctrl = _build_controller(host)
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(1000)
    ctrl.rebind()
    w0 = ctrl.widget_for_index(0)
    assert w0 is not None
    assert w0.text() == "row-0"
    assert ctrl.widget_for_index(999) is None  # not materialized


def test_controller_empty_count_materializes_nothing(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll, content, ctrl = _build_controller(host)
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(0)
    ctrl.rebind()
    assert [w for w in content.findChildren(QLabel) if w.isVisible()] == []
    assert content.minimumHeight() == 0


def test_controller_resize_triggers_rebind(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll, content, ctrl = _build_controller(host)
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(1000)
    ctrl.rebind()
    before = len([w for w in content.findChildren(QLabel) if not w.isHidden()])

    # Grow the viewport: more rows must materialize without any explicit
    # rebind call (the controller watches the scroll area's Resize event).
    scroll.resize(300, 600)
    qtbot.wait(30)
    after = len([w for w in content.findChildren(QLabel) if not w.isHidden()])
    assert after > before


def test_controller_scrollbar_range_and_page(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll, content, ctrl = _build_controller(host)
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(1000)
    ctrl.rebind()
    # Let the scroll area's deferred custom-bar sync run.
    qtbot.wait(30)

    native = scroll.verticalScrollBar()
    viewport = scroll.viewport().height()
    assert native.minimum() == 0
    assert native.maximum() == 1000 * 30 - viewport
    assert native.pageStep() == viewport
    assert native.singleStep() == 30
    # The custom bar mirrors the native range (OverlayScrollArea plumbing).
    assert scroll.custom_v_scrollbar.maximum() == native.maximum()
    assert scroll.custom_v_scrollbar.isVisible()

    # Small list: no range, bar hidden.
    ctrl.set_count(5)
    ctrl.rebind()
    qtbot.wait(30)
    assert native.maximum() == 0
    assert scroll.custom_v_scrollbar.maximum() == 0


def test_controller_index_at_global_pos(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll, content, ctrl = _build_controller(host)
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(1000)
    ctrl.rebind()

    # Rows sit at absolute content coordinates (Qt moves the content
    # widget itself): row 10 occupies content y 300..330 regardless of
    # scroll; scrolling 300px puts it at the viewport top.
    ctrl.scroll_to(300)
    qtbot.wait(10)
    assert ctrl.index_at(content.mapToGlobal(QPoint(5, 300))) == 10
    assert ctrl.index_at(content.mapToGlobal(QPoint(5, 315))) == 10
    # Content origin is always row 0, scrolled or not.
    assert ctrl.index_at(content.mapToGlobal(content.rect().topLeft())) == 0
    # Below the content -> out of range.
    assert ctrl.index_at(content.mapToGlobal(QPoint(5, 1000 * 30))) == -1


def test_scrolled_rows_keep_absolute_positions(qtbot):
    """No double scroll offset: Qt moves the content widget itself, so the
    pool must position rows at absolute content coordinates.

    Regression: subtracting the offset again scrolled lists at 2x and left
    ~2 pitches of dead space under the last row at max scroll.
    """
    from sli_ui_toolkit.widgets import OverlayScrollArea, VirtualListController

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 300)
    scroll = OverlayScrollArea(host)
    scroll.setGeometry(0, 0, 300, 300)
    content = QWidget()
    scroll.setWidget(content)
    ym, pitch, widget_h, count = 4, 30, 28, 20
    ctrl = VirtualListController(
        scroll, content, factory=lambda: QLabel("row"),
        bind=lambda i, w: w.setText(f"row-{i}"),
        row_height=pitch, widget_height=widget_h,
        x_margin=4, y_margin=ym,
    )
    host.show()
    qtbot.waitExposed(host)
    ctrl.set_count(count)
    ctrl.rebind()
    qtbot.wait(30)

    expected_last_y = ym + (count - 1) * pitch
    assert ctrl.widget_for_index(0).y() == ym

    native = scroll.verticalScrollBar()
    viewport = scroll.viewport().height()
    assert native.maximum() == ctrl._content_height() - viewport

    # Scroll to the very end: row geometry is absolute (no offset
    # subtracted), so the last row sits at ym + (count-1)*pitch; its
    # bottom + margin lands exactly on the content end (which Qt parks at
    # the viewport bottom) — no dead band.
    native.setValue(native.maximum())
    qtbot.wait(30)
    assert ctrl.widget_for_index(count - 1).y() == expected_last_y
    last_bottom = expected_last_y + widget_h
    assert last_bottom + ym == ctrl._content_height()
    assert last_bottom - native.value() == viewport - ym