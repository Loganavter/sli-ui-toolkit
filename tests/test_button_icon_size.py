"""`setIconSize` must move the PAINTED icon box, not only Qt's stored QSize."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

from sli_ui_toolkit.widgets import Button


def test_set_icon_size_moves_the_painted_box(qapp):
    button = Button()
    pixmap = QPixmap(64, 64)
    pixmap.fill()
    button.setIcon(QIcon(pixmap))
    button.setIconSize(QSize(35, 35))
    assert button.iconSize() == QSize(35, 35)
    assert button.property("iconSizePx") == 35


def test_a_square_is_taken_from_the_smaller_side(qapp):
    button = Button()
    button.setIconSize(QSize(40, 24))
    assert button.iconSize() == QSize(24, 24)
