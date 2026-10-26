"""Drag-to-reorder for ``AdaptiveTabStrip`` (opt-in ``setMovable``).

The strip is a custom-painted ``QWidget`` with a ``QTabBar``-shaped surface, so
reordering cannot be inherited from ``QTabBar``: these tests drive the real
press/move/release gesture offscreen and pin the contract the host relies on
(``tabMoved``, one reorder path, active-tab identity, cancel paths).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.widgets import AdaptiveTabStrip, CloseButtonPolicy

RS = 1  # QTabBar.ButtonPosition.RightSide
TITLES = ("Alpha", "Beta", "Gamma")


def _strip(*, movable: bool = True, titles=TITLES, policy=CloseButtonPolicy.ALL):
    strip = AdaptiveTabStrip(
        add_icon="add",
        close_icon="remove",
        close_policy=policy,
        single_tab_closable=True,
    )
    for index, title in enumerate(titles):
        strip.addTab(title)
        strip.setTabData(index, f"data:{title}")
    if movable:
        strip.setMovable(True)
    strip.resize(900, strip.sizeHint().height())
    strip.show()
    QApplication.processEvents()
    return strip


def _titles(strip):
    return [strip.tabText(index) for index in range(strip.count())]


def _data(strip):
    return [strip.tabData(index) for index in range(strip.count())]


def _press_point(strip, index: int) -> QPoint:
    """Point in the left part of a tab: away from its close slot and centre."""
    rect = strip.tab_bar.tabRect(index)
    return QPoint(rect.left() + max(4, rect.width() // 8), rect.center().y())


def _drop_point(strip, index: int, *, right_half: bool = False) -> QPoint:
    """Point in a tab's left half (gap before it) or right half (gap after)."""
    rect = strip.tab_bar.tabRect(index)
    x = rect.left() + ((rect.width() * 3) // 4 if right_half else max(2, rect.width() // 4))
    return QPoint(x, rect.center().y())


def _drag(strip, from_index: int, to_point: QPoint) -> None:
    bar = strip.tab_bar
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=_press_point(strip, from_index))
    QTest.mouseMove(bar, to_point)
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=to_point)
    QApplication.processEvents()


# -- default off ---------------------------------------------------------------


def test_movable_is_off_by_default_and_a_drag_is_a_click(qapp):
    strip = _strip(movable=False)
    bar = strip.tab_bar
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))

    assert strip.isMovable() is False
    point = _press_point(strip, 2)
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(bar, _drop_point(strip, 0))
    assert bar._drag_active is False

    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=point)
    qapp.processEvents()

    assert _titles(strip) == list(TITLES)
    assert moves == []
    # The press is still a plain tab activation.
    assert strip.currentIndex() == 2


# -- the gesture ---------------------------------------------------------------


def test_drag_right_moves_the_tab_and_emits_once(qapp):
    strip = _strip()
    bar = strip.tab_bar
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))
    target = _drop_point(strip, 2, right_half=True)

    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=_press_point(strip, 0))
    QTest.mouseMove(bar, target)
    assert bar._drag_active is True
    assert bar._drop_index == 3
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=target)
    qapp.processEvents()

    assert _titles(strip) == ["Beta", "Gamma", "Alpha"]
    assert moves == [(0, 2)]


def test_drag_left_moves_the_tab_to_the_front(qapp):
    strip = _strip()
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))

    _drag(strip, 2, _drop_point(strip, 0))

    assert _titles(strip) == ["Gamma", "Alpha", "Beta"]
    assert moves == [(2, 0)]


def test_press_below_the_drag_threshold_does_not_reorder(qapp):
    strip = _strip()
    bar = strip.tab_bar
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))
    start = _press_point(strip, 0)

    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
    # Under ``QApplication.startDragDistance()``: still a click, never a drag.
    QTest.mouseMove(bar, QPoint(start.x() + 2, start.y()))
    assert bar._drag_active is False
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=_drop_point(strip, 2, right_half=True))
    qapp.processEvents()

    assert _titles(strip) == list(TITLES)
    assert moves == []


def test_plain_click_still_activates_without_reordering(qapp):
    strip = _strip()
    bar = strip.tab_bar
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))

    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=_press_point(strip, 2))
    qapp.processEvents()

    assert strip.currentIndex() == 2
    assert _titles(strip) == list(TITLES)
    assert moves == []


def test_close_slot_press_never_starts_a_drag(qapp):
    strip = _strip()
    bar = strip.tab_bar
    slot = strip.tabButton(0, RS)
    assert slot is not None and slot.isVisible()
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))
    target = _drop_point(strip, 2, right_half=True)

    # The slot's own press is ignored and propagates into the bar at the same
    # point, which must not arm a reorder (the slot owns that gesture).
    QTest.mousePress(slot, Qt.MouseButton.LeftButton, pos=slot.rect().center())
    QTest.mouseMove(bar, target)
    assert bar._drag_active is False
    assert bar._drag_index == -1
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=target)
    qapp.processEvents()

    assert _titles(strip) == list(TITLES)
    assert moves == []


def test_escape_cancels_the_drag(qapp):
    strip = _strip()
    bar = strip.tab_bar
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))
    target = _drop_point(strip, 2, right_half=True)

    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=_press_point(strip, 0))
    QTest.mouseMove(bar, target)
    assert bar._drag_active is True

    QTest.keyClick(bar, Qt.Key.Key_Escape)
    assert bar._drag_active is False

    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=target)
    qapp.processEvents()

    assert _titles(strip) == list(TITLES)
    assert moves == []


def test_leaving_the_strip_cancels_the_drag(qapp):
    strip = _strip()
    bar = strip.tab_bar
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))
    target = _drop_point(strip, 2, right_half=True)

    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=_press_point(strip, 0))
    QTest.mouseMove(bar, target)
    assert bar._drag_active is True

    QApplication.sendEvent(bar, QEvent(QEvent.Type.Leave))
    assert bar._drag_active is False

    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=target)
    qapp.processEvents()

    assert _titles(strip) == list(TITLES)
    assert moves == []


def test_release_outside_the_bar_cancels(qapp):
    strip = _strip()
    bar = strip.tab_bar
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))

    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=_press_point(strip, 0))
    QTest.mouseMove(bar, _drop_point(strip, 2, right_half=True))
    assert bar._drag_active is True

    # A grab-handed release outside the bar (the strip's add button, the app
    # beside it) still arrives at the bar in its own coordinates.
    outside = QPointF(bar.width() + 40.0, float(bar.rect().center().y()))
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        outside,
        QPointF(bar.mapToGlobal(outside.toPoint())),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, event)
    qapp.processEvents()

    assert bar._drag_active is False
    assert _titles(strip) == list(TITLES)
    assert moves == []


def test_dropping_in_the_gap_next_to_the_dragged_tab_is_a_noop(qapp):
    strip = _strip()
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))

    # Gap before Beta and gap after Beta both mean "Beta stays where it is".
    _drag(strip, 1, _drop_point(strip, 1))
    _drag(strip, 1, _drop_point(strip, 1, right_half=True))

    assert _titles(strip) == list(TITLES)
    assert moves == []


def test_single_and_empty_strips_are_noops(qapp):
    empty = _strip(titles=())
    bar = empty.tab_bar
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=QPoint(20, 10))
    QTest.mouseMove(bar, QPoint(60, 10))
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(60, 10))
    qapp.processEvents()
    assert empty.count() == 0
    assert bar._drag_active is False

    single = _strip(titles=("Only",))
    moves = []
    single.tabMoved.connect(lambda a, b: moves.append((a, b)))
    bar = single.tab_bar
    rect = bar.tabRect(0)
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=_press_point(single, 0))
    QTest.mouseMove(bar, QPoint(rect.right() - 2, rect.center().y()))
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(rect.right() - 2, rect.center().y()))
    qapp.processEvents()

    assert single.count() == 1
    assert _titles(single) == ["Only"]
    assert moves == []


# -- programmatic path ---------------------------------------------------------


def test_move_tab_is_the_single_implementation_and_keeps_content(qapp):
    strip = _strip()
    moves = []
    strip.tabMoved.connect(lambda a, b: moves.append((a, b)))
    strip.setCurrentIndex(1)  # Beta is active
    beta_slot = strip.tabButton(1, RS)
    assert beta_slot is not None

    strip.moveTab(1, 2)
    qapp.processEvents()

    assert _titles(strip) == ["Alpha", "Gamma", "Beta"]
    # Text and data travel together with the active tab's identity.
    assert _data(strip) == ["data:Alpha", "data:Gamma", "data:Beta"]
    assert strip.currentIndex() == 2
    assert strip.tabText(strip.currentIndex()) == "Beta"
    assert moves == [(1, 2)]
    # The close slot is a child widget: it must travel with its tab and be
    # re-placed inside the moved tab's painted rect.
    assert strip.tabButton(2, RS) is beta_slot
    tab_rect = strip.tab_bar._painted_tab_rect(strip.tabRect(2))
    assert tab_rect.contains(beta_slot.geometry().center())

    # Out-of-range and self-moves emit nothing.
    strip.moveTab(2, 2)
    strip.moveTab(5, 0)
    strip.moveTab(0, 9)
    assert moves == [(1, 2)]
    assert _titles(strip) == ["Alpha", "Gamma", "Beta"]


def test_moving_another_tab_keeps_the_active_tab_current(qapp):
    strip = _strip()
    strip.setCurrentIndex(0)  # Alpha is active
    strip.moveTab(2, 0)
    qapp.processEvents()

    assert _titles(strip) == ["Gamma", "Alpha", "Beta"]
    assert strip.currentIndex() == 1
    assert strip.tabText(strip.currentIndex()) == "Alpha"


def test_move_tab_works_when_not_movable(qapp):
    strip = _strip(movable=False)
    strip.moveTab(0, 2)
    assert _titles(strip) == ["Beta", "Gamma", "Alpha"]


def test_tab_moved_forwards_from_the_bar(qapp):
    strip = _strip()
    bar_moves = []
    strip_moves = []
    strip.tab_bar.tabMoved.connect(lambda a, b: bar_moves.append((a, b)))
    strip.tabMoved.connect(lambda a, b: strip_moves.append((a, b)))

    strip.tab_bar.moveTab(0, 1)

    assert bar_moves == [(0, 1)]
    assert strip_moves == [(0, 1)]


# -- the insertion indicator ---------------------------------------------------


def test_drop_indicator_is_painted_only_while_dragging(qapp):
    strip = _strip()
    bar = strip.tab_bar
    palette = {
        "strip": "#303030",
        "background": "#f0f0f0",
        "border": "#888888",
        "hover": "#404040",
        "text": "#ffffff",
        "accent": "#ff00ff",
    }
    bar._palette = lambda: palette  # type: ignore[method-assign]
    accent = QColor(palette["accent"])
    assert bar._drop_indicator_rect().isEmpty()

    target = _drop_point(strip, 2, right_half=True)
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=_press_point(strip, 0))
    QTest.mouseMove(bar, target)
    assert bar._drag_active is True

    rect = bar._drop_indicator_rect()
    assert not rect.isEmpty()
    assert bar._viewport_rect().contains(rect)

    image = QImage(bar.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    bar.render(image)
    sample = image.pixelColor(rect.center())
    assert sample == accent, f"indicator painted {sample.name()}, expected {accent.name()}"

    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=target)
    qapp.processEvents()
    assert bar._drop_indicator_rect().isEmpty()
