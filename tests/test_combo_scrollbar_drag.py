"""ComboBox dropdown scrollbar: drag must track the cursor even when the
press lands on the overlay's boundary and gets forwarded to the scrollbar
via QApplication.sendEvent instead of arriving as a real grab."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import ComboBox


def _make_combo(host, qtbot):
    combo = ComboBox(parent=host)
    combo.addItems([f"item-{i}" for i in range(40)])
    combo.setMaxVisibleItems(8)
    combo.setCurrentIndex(0)
    combo.move(40, 160)
    combo.resize(220, 33)
    host.show()
    qtbot.waitExposed(host)
    combo.showDropdown()
    qtbot.waitUntil(lambda: combo._overlay is not None and combo._overlay.custom_v_scrollbar.isVisible())
    return combo


def _event(typ, pos, buttons):
    return QMouseEvent(
        typ,
        QPointF(pos),
        pos,
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_dropdown_scrollbar_drag_after_boundary_press_tracks_cursor(qtbot):
    """Regression: a press at the scrollbar's left edge is routed to the
    overlay (not the scrollbar), so the scrollbar gets a synthesized press
    and never owns the mouse grab. The overlay must keep forwarding moves and
    the release so the drag follows the cursor outside the 10px column and
    the scrollbar's internal dragging state resets on release."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(600, 600)
    combo = _make_combo(host, qtbot)

    overlay = combo._overlay
    sb = overlay.custom_v_scrollbar

    # Press exactly on the scrollbar's left edge (x=0 in scrollbar coords).
    press_global = sb.mapToGlobal(QPoint(0, sb.height() // 2))
    press_pos = overlay.mapFromGlobal(press_global)
    overlay.mousePressEvent(
        _event(QMouseEvent.Type.MouseButtonPress, press_pos, Qt.MouseButton.LeftButton)
    )
    assert sb._is_dragging is True
    assert overlay._sb_dragging is True
    value_after_press = sb.value()

    # Drag far outside the scrollbar column — the value must keep tracking.
    far_global = sb.mapToGlobal(QPoint(0, sb.height() // 2)) + QPoint(-100, 60)
    overlay.mouseMoveEvent(
        _event(QMouseEvent.Type.MouseMove, overlay.mapFromGlobal(far_global), Qt.MouseButton.LeftButton)
    )
    assert sb.value() != value_after_press

    # Release outside the scrollbar — the drag state must reset everywhere.
    overlay.mouseReleaseEvent(
        _event(
            QMouseEvent.Type.MouseButtonRelease,
            overlay.mapFromGlobal(far_global),
            Qt.MouseButton.NoButton,
        )
    )
    assert sb._is_dragging is False
    assert overlay._sb_dragging is False

    combo.hideDropdown()