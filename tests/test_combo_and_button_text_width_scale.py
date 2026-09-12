"""ComboBox/Button width hints track the painted (scale-aware) font.

Regression: the field and text-button size hints measured text with the
widget's raw design font, while every paint path draws through
``paint_font`` (design size x UiScale factor). At interface scale > 1.0 the
combo's width hint under-measured long labels ("Сбалансированное (0.75x)"
in the video editor) and the field elided them; text buttons overflowed the
same way.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.widgets import Button, ComboBox

LONG_ITEMS = [
    "Полное (1.0x)",
    "Сбалансированное (0.75x)",
    "Производительное (0.5x)",
    "Черновое (0.25x)",
]


@pytest.fixture(autouse=True)
def _reset_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _paint_text_width(widget, text: str) -> int:
    return QFontMetrics(paint_font(widget)).horizontalAdvance(text)


def _host(widgets) -> tuple[QWidget, list]:
    host = QWidget()
    layout = QHBoxLayout(host)
    for widget in widgets:
        layout.addWidget(widget)
    host.show()
    return host, layout


def test_combo_width_hint_fits_painted_longest_item(qapp):
    combo = ComboBox()
    for item in LONG_ITEMS:
        combo.addItem(item)
    combo.setCurrentIndex(1)
    host, _ = _host([combo])
    qapp.processEvents()

    for factor in (1.0, 1.5, 2.0):
        UiScale.get_instance().set_factor(factor)
        qapp.processEvents()

        longest = max(LONG_ITEMS, key=lambda t: _paint_text_width(combo, t))
        needed = _paint_text_width(combo, longest) + scaled_combo_padding(combo)
        assert combo.sizeHint().width() >= needed, (
            f"scale {factor}: sizeHint {combo.sizeHint().width()} < painted "
            f"text width {needed} — field elides the longest label"
        )
        assert combo.width() >= combo.sizeHint().width()

    host.close()


def scaled_combo_padding(combo) -> int:
    from sli_ui_toolkit.managers import scaled_px

    return scaled_px(combo.TEXT_HORIZONTAL_PADDING) * 2


def test_text_button_width_hint_fits_painted_text(qapp):
    button = Button(text="Set as Favorite")
    host, _ = _host([button])
    qapp.processEvents()

    for factor in (1.0, 1.5, 2.0):
        UiScale.get_instance().set_factor(factor)
        qapp.processEvents()

        painted = _paint_text_width(button, "Set as Favorite")
        assert button.sizeHint().width() >= painted, (
            f"scale {factor}: sizeHint {button.sizeHint().width()} < "
            f"painted text width {painted}"
        )
        assert button.width() >= button.sizeHint().width()

    host.close()
