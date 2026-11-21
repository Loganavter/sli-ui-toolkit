"""A flat selected tab's plate must not run into the strip's bottom edge.

A plate drawn on the button's full rect has its bottom corners cut by the pane below, so a flat tab style reads as
"rounded on top, square at the bottom" (owner report 2026-11-22). `TabStyle.plate_margin` insets the plate, which keeps
the radius visible and gives the strip air under the buttons.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.tab_button import plate_rect
from sli_ui_toolkit.widgets import TabStyle


def _button(width: int, height: int) -> QWidget:
    button = QWidget()
    button.resize(width, height)
    return button


def test_the_plate_is_inset_on_every_side():
    button = _button(120, 32)
    rect = plate_rect(button, TabStyle(flat=True, plate_margin=4))
    assert rect.left() == 4 and rect.top() == 4
    assert rect.right() == 120 - 4 - 1 + 1 or rect.right() == 115, rect.right()
    assert rect.bottom() == 32 - 4 - 1 + 1 or rect.bottom() == 27, rect.bottom()
    assert rect.height() < button.height(), "a plate of the full height has its bottom radius cut"


def test_no_margin_keeps_the_whole_button():
    button = _button(120, 32)
    rect = plate_rect(button, TabStyle(flat=True))
    assert (rect.left(), rect.top()) == (0, 0)
    assert (rect.width(), rect.height()) == (120, 32)
