"""`setIconSize` must move the PAINTED icon box, not only a field.

The box lives in the main region spec (the painter takes `ctx.region_icon_size_px` first), so a setter that writes
`_icon_size_px` alone changes nothing on screen: measured 2026-11-22, a host asking for a 35 px nav icon got 22 px.
These tests measure the rendered pixels, because the field and the property were both already correct while the
picture was not.
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPixmap

from sli_ui_toolkit.widgets import Button


def _white_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#ffffff"))
    return QIcon(pixmap)


def _painted_box(button: Button) -> tuple[int, int]:
    """Size of the pure-white area the button painted (the icon; the plate is dark)."""
    image = button.grab().toImage()
    points = [
        (x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).red() > 240
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def test_set_icon_size_moves_the_painted_box(qapp):
    button = Button(size=(55, 45))
    button.setIcon(_white_icon())
    button.resize(55, 45)
    assert _painted_box(button) == (22, 22)          # the spec default, untouched

    button.setIconSize(QSize(35, 35))
    assert _painted_box(button) == (35, 35)


def test_a_non_square_request_takes_the_smaller_side(qapp):
    button = Button(size=(55, 45))
    button.setIcon(_white_icon())
    button.resize(55, 45)
    button.setIconSize(QSize(40, 20))
    assert _painted_box(button) == (20, 20)


def test_the_construction_time_size_still_wins(qapp):
    button = Button(size=(55, 45), icon_size=35)
    button.setIcon(_white_icon())
    button.resize(55, 45)
    assert _painted_box(button) == (35, 35)


def test_an_icon_only_button_sizes_to_its_icon_plus_padding(qapp):
    """Qt's QToolButton rule: an icon-only control is the icon plus margins, floored at 36.

    The old rule returned 36x36 whatever the icon was, so a host stating 35 px glyphs in a 55x45 slot got 36x36 and every
    icon row shifted (owner report: the nav rail buttons shrank).
    """
    button = Button(size=(0, 0), content_padding=(10, 5, 10, 5))
    button.setIcon(_white_icon())
    button.setIconSize(QSize(35, 35))
    assert (button.sizeHint().width(), button.sizeHint().height()) == (55, 45)


def test_a_small_icon_keeps_the_standalone_floor(qapp):
    button = Button(size=(0, 0))
    button.setIcon(_white_icon())
    button.setIconSize(QSize(10, 10))
    assert button.sizeHint().width() >= 36 and button.sizeHint().height() >= 36
