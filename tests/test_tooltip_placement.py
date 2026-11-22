"""The tooltip's PLATE sits at the cursor offset - its shadow margin is not part of the gap.

The bubble's rect carries a transparent shadow margin on every side. Placing the RECT at the offset put the visible plate a
shadow-width further away, so the gap read as 28 px instead of the stated 20 (owner report 2026-11-22).
"""
from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip


def test_the_visible_plate_lands_at_the_cursor_offset(qapp=None):
    app = qapp or QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(600, 400)
    host.show()
    app.processEvents()

    tip = PathTooltip.get_instance()
    local = QPoint(100, 100)
    cursor = host.mapToGlobal(local)
    tip.show_tooltip(cursor, "hello", delay_ms=0)
    for _ in range(10):
        app.processEvents()

    bubbles = [w for w in host.findChildren(QWidget) if type(w).__name__ == "_TooltipBubble"]
    assert bubbles, "no tooltip bubble was created"
    bubble = bubbles[-1]
    plate = bubble.mapToGlobal(QPoint(bubble.SHADOW_RADIUS, bubble.SHADOW_RADIUS))
    assert plate.y() - cursor.y() == 20, f"the plate sits {plate.y() - cursor.y()} px below the cursor, not 20"
