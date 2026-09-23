"""Outer outline (BorderLayer) for region-composed buttons.

``BackgroundLayer`` skips the border stroke for any region whose rect differs
from the button rect, so ``setBorderColor()`` on a region-composed button was
a silent no-op. ``BorderLayer`` (widget scope) strokes one outer rounded rect
when — and only when — the host sets an explicit widget-level override.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage, QPainter

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.layers._base import outline_width
from sli_ui_toolkit.ui.widgets.buttons.painter import default_layers
from sli_ui_toolkit.widgets import (
    BackgroundLayer,
    BorderLayer,
    Button,
    ButtonRegion,
    VerticalSplit,
)


def _tm() -> ThemeManager:
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    return tm


def _paint(btn: Button) -> QImage:
    img = QImage(btn.size(), QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    painter = QPainter(img)
    ctx = btn._make_context(painter)
    btn._painter.paint(ctx)
    painter.end()
    return img


def _card_like() -> Button:
    white = QColor("#ffffff")
    return Button(
        regions=[
            ButtonRegion(id="top", override_bg_color=white),
            ButtonRegion(id="bottom", override_bg_color=white),
        ],
        split=VerticalSplit(),
        size=(60, 40),
        corner_radius=6,
    )


def _chan_dist(a: QColor, b: QColor) -> int:
    return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())


def test_default_layers_stroke_border_after_background(qtbot):
    layers = default_layers()
    names = [type(layer).__name__ for layer in layers]
    assert "BorderLayer" in names
    assert names.index("BorderLayer") > names.index("BackgroundLayer")


def test_region_button_outline_paints_on_override(qtbot):
    _tm()
    btn = _card_like()
    qtbot.addWidget(btn)
    border = QColor("#e2e4e8")
    btn.setBorderColor(border)
    img = _paint(btn)
    edge = img.pixelColor(0, 20)
    middle = img.pixelColor(30, 20)
    assert middle.name().lower() == "#ffffff"
    assert _chan_dist(edge, border) < _chan_dist(edge, middle), (
        f"edge {edge.name()} not near border, fill {middle.name()}"
    )
    assert _chan_dist(edge, border) < 90


def test_region_button_no_outline_without_override(qtbot):
    _tm()
    btn = _card_like()
    qtbot.addWidget(btn)
    assert btn.borderColor() is None
    img = _paint(btn)
    assert img.pixelColor(0, 20) == img.pixelColor(30, 20)


def test_outline_width_two_paints_band(qtbot):
    _tm()
    btn = _card_like()
    qtbot.addWidget(btn)
    border = QColor("#0096ff")
    btn.setBorderColor(border)
    btn.setProperty("borderWidth", 2)
    img = _paint(btn)
    assert _chan_dist(img.pixelColor(0, 20), border) < 90
    assert _chan_dist(img.pixelColor(1, 20), border) < 120


def test_outline_override_wins_when_disabled(qtbot):
    """Parity with BackgroundLayer: an explicit override strokes even disabled.

    (BackgroundLayer._resolve applies params.override_border unconditionally,
    so a plain button keeps its override edge when disabled; BorderLayer
    matches that semantic — clear with setBorderColor(None) to follow the
    disabled wash instead.)
    """
    _tm()
    btn = _card_like()
    qtbot.addWidget(btn)
    border = QColor("#e2e4e8")
    btn.setBorderColor(border)
    btn.setEnabled(False)
    img = _paint(btn)
    assert _chan_dist(img.pixelColor(0, 20), border) < 90


def test_outline_width_helper_defaults(qtbot):
    _tm()
    btn = _card_like()
    qtbot.addWidget(btn)
    assert outline_width(btn) == 1.0
    btn.setProperty("borderWidth", 2)
    assert outline_width(btn) == 2.0
    btn.setProperty("borderWidth", "nonsense")
    assert outline_width(btn) == 1.0
    btn.setProperty("borderWidth", 0)
    assert outline_width(btn) == 1.0
