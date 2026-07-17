"""ComboBox showDropdown focus_index + pulse Hide isolation."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import ComboBox


def test_show_dropdown_focus_index_does_not_change_current(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = ComboBox(parent=host)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    combo.move(40, 160)
    host.show()
    qtbot.waitExposed(host)

    combo.showDropdown(focus_index=2)
    assert combo._expanded is True
    assert combo.currentIndex() == 0
    assert combo._dropdown_focus_index == 2
    assert combo.currentText() == "A"
    row = combo.dropdown_row_widget(2)
    assert row is not None
    assert row._item_index == 2

    combo.hideDropdown()
    assert combo._dropdown_focus_index is None
    assert combo.currentIndex() == 0


def test_unrelated_overlay_hide_does_not_close_dropdown(qtbot):
    """Pulse-style overlays hide after a timer; that Hide must not dismiss us."""
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = ComboBox(parent=host)
    combo.addItems(["A", "B", "C"])
    combo.setCurrentIndex(0)
    combo.move(40, 160)
    host.show()
    qtbot.waitExposed(host)

    combo.showDropdown(focus_index=2)
    assert combo._expanded is True

    decoy = QWidget(host)
    decoy.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    decoy.setGeometry(0, 0, 80, 80)
    decoy.show()
    qtbot.wait(10)
    decoy.hide()
    qtbot.wait(10)

    assert combo._expanded is True
    assert combo._overlay is not None and combo._overlay.isVisible()
