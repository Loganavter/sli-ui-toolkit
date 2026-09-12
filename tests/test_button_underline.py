from __future__ import annotations

import pytest

from PySide6.QtGui import QColor, QPainter, QPixmap

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
from sli_ui_toolkit.ui.widgets.buttons.layers.underline import UnderlineLayer
from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant
from sli_ui_toolkit.ui.widgets.helpers import underline_painter
from sli_ui_toolkit.widgets import Button


def test_button_underline_thickness_is_clamped_to_three(qapp, monkeypatch):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    seen = {}

    def fake_draw_bottom_underline(painter, rect, theme_manager, config=None):
        seen["thickness"] = config.thickness

    monkeypatch.setattr(underline_painter, "draw_bottom_underline", fake_draw_bottom_underline)
    import sli_ui_toolkit.ui.widgets.buttons.layers.underline as underline_layer

    monkeypatch.setattr(
        underline_layer,
        "draw_bottom_underline",
        fake_draw_bottom_underline,
    )

    with pytest.warns(RuntimeWarning, match="capped at 3.0px"):
        button = Button(
            text="",
            show_underline=True,
            underline_color=QColor("#ff0000"),
            underline_thickness=6.0,
        )
    pixmap = QPixmap(button.size())
    painter = QPainter(pixmap)
    try:
        ctx = DrawContext(
            widget=button,
            painter=painter,
            rect=button.rect(),
            states=frozenset(),
            variant=get_variant("default"),
            corner_radius=6,
            show_underline=True,
            underline_color=QColor("#ff0000"),
            underline_thickness=6.0,
        )
        with pytest.warns(RuntimeWarning, match="capped at 3.0px"):
            UnderlineLayer().draw(ctx, tm)
    finally:
        painter.end()
        button.deleteLater()

    assert seen["thickness"] == 3.0


def test_button_underline_requires_show_flag(qapp, monkeypatch):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    calls = []

    def fake_draw_bottom_underline(painter, rect, theme_manager, config=None):
        calls.append(config)

    monkeypatch.setattr(underline_painter, "draw_bottom_underline", fake_draw_bottom_underline)
    import sli_ui_toolkit.ui.widgets.buttons.layers.underline as underline_layer

    monkeypatch.setattr(
        underline_layer,
        "draw_bottom_underline",
        fake_draw_bottom_underline,
    )

    button = Button(text="")
    pixmap = QPixmap(button.size())
    painter = QPainter(pixmap)
    try:
        ctx = DrawContext(
            widget=button,
            painter=painter,
            rect=button.rect(),
            states=frozenset(),
            variant=get_variant("default"),
            corner_radius=6,
            show_underline=False,
            underline_color=QColor("#ff0000"),
        )
        assert not UnderlineLayer().applies(ctx)
        UnderlineLayer().draw(ctx, tm)
    finally:
        painter.end()
        button.deleteLater()

    assert calls == []


def test_explicit_underline_color_keeps_alpha(qapp, monkeypatch):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    seen = {}

    def fake_draw_bottom_underline(painter, rect, theme_manager, config=None):
        seen["alpha"] = config.alpha

    monkeypatch.setattr(underline_painter, "draw_bottom_underline", fake_draw_bottom_underline)
    import sli_ui_toolkit.ui.widgets.buttons.layers.underline as underline_layer

    monkeypatch.setattr(
        underline_layer,
        "draw_bottom_underline",
        fake_draw_bottom_underline,
    )

    button = Button(text="", show_underline=True)
    pixmap = QPixmap(button.size())
    painter = QPainter(pixmap)
    try:
        ctx = DrawContext(
            widget=button,
            painter=painter,
            rect=button.rect(),
            states=frozenset(),
            variant=get_variant("default"),
            corner_radius=6,
            show_underline=True,
            underline_color=QColor(12, 34, 56, 230),
        )
        UnderlineLayer().draw(ctx, tm)
    finally:
        painter.end()
        button.deleteLater()

    assert seen["alpha"] == 230
