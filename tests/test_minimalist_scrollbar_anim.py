"""MinimalistScrollBar visual interpolation tests.

Thickness (idle/hover/drag) and opacity ease toward their targets instead of
switching instantly; animated visibility fades in/out; idle auto-hide fades
the bar out after inactivity and re-shows it on scroll activity.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import MinimalistScrollBar, OverlayScrollArea


def _make_bar(qtbot):
    bar = MinimalistScrollBar(Qt.Orientation.Vertical)
    qtbot.addWidget(bar)
    bar.resize(10, 300)
    bar.setRange(0, 100)
    bar.setPageStep(50)
    bar.show()
    # The hover coordinator may reconcile the (0,0) offscreen cursor over the
    # unparented bar; tests drive hover explicitly.
    bar.setHoverActive(False)
    return bar


def _press(bar, pos, release=False):
    typ = (
        QMouseEvent.Type.MouseButtonRelease
        if release
        else QMouseEvent.Type.MouseButtonPress
    )
    return QMouseEvent(
        typ,
        QPointF(pos),
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton if release else Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_thickness_eases_on_hover(qtbot):
    bar = _make_bar(qtbot)
    assert bar._anim_thickness == 4.0
    bar.setHoverActive(True)
    qtbot.wait(40)
    assert 4.0 < bar._anim_thickness < 6.0  # eased, not jumped
    qtbot.waitUntil(lambda: bar._anim_thickness == 6.0, timeout=1500)
    bar.setHoverActive(False)
    qtbot.waitUntil(lambda: bar._anim_thickness == 4.0, timeout=1500)


def test_thickness_eases_on_drag(qtbot):
    bar = _make_bar(qtbot)
    handle = bar._get_handle_rect()
    bar.mousePressEvent(_press(bar, handle.center()))
    assert bar._is_dragging
    qtbot.waitUntil(lambda: bar._anim_thickness == 10.0, timeout=1500)
    bar.mouseReleaseEvent(_press(bar, handle.center(), release=True))
    qtbot.waitUntil(lambda: bar._anim_thickness == 4.0, timeout=1500)


def test_animated_visible_fades_out_then_hides(qtbot):
    bar = _make_bar(qtbot)
    bar.set_animated_visible(False)
    qtbot.wait(40)
    assert bar.isVisible()  # fading, not hidden yet
    assert bar._anim_alpha < 1.0
    qtbot.waitUntil(lambda: not bar.isVisible(), timeout=1500)


def test_animated_visible_fades_in(qtbot):
    bar = _make_bar(qtbot)
    bar.set_animated_visible(False)
    qtbot.waitUntil(lambda: not bar.isVisible(), timeout=1500)
    bar.set_animated_visible(True)
    assert bar.isVisible()
    assert bar._anim_alpha == 0.0
    qtbot.waitUntil(lambda: bar._anim_alpha == 1.0, timeout=1500)


def test_auto_hide_fades_after_idle(qtbot):
    bar = _make_bar(qtbot)
    bar.set_auto_hide(0.2)
    bar._poke()
    qtbot.wait(50)
    assert bar.isVisible()
    qtbot.waitUntil(lambda: not bar.isVisible(), timeout=2000)


def test_scroll_activity_reshows_hidden_bar(qtbot):
    bar = _make_bar(qtbot)
    bar.set_auto_hide(0.2)
    bar._poke()
    qtbot.waitUntil(lambda: not bar.isVisible(), timeout=2000)
    bar.setValue(20)  # scroll activity
    assert bar.isVisible()
    qtbot.waitUntil(lambda: bar._anim_alpha == 1.0, timeout=1500)


def test_overlay_area_bar_autohides_and_reshows(qtbot):
    area = OverlayScrollArea()
    qtbot.addWidget(area)
    content = QWidget()
    content.setMinimumHeight(600)
    area.setWidget(content)
    area.resize(300, 200)
    area.show()
    qtbot.waitExposed(area)
    bar = area.custom_v_scrollbar
    assert bar.isVisible()
    qtbot.waitUntil(lambda: not bar.isVisible(), timeout=3000)
    area.verticalScrollBar().setValue(100)  # scroll activity re-shows
    assert bar.isVisible()