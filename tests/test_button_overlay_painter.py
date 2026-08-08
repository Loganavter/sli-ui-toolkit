from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    BackgroundLayer,
    Button,
    ButtonRegion,
    DrawContext,
    Layer,
    OverlayPainterLayer,
    RippleLayer,
    default_layers,
)


def test_button_overlay_painter_callback(qtbot):
    called = []

    def my_overlay(painter: QPainter, rect: QRectF):
        called.append(rect)

    btn = Button(text="Test", overlay_painter=my_overlay, size=(100, 40))
    qtbot.addWidget(btn)

    img = QImage(btn.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    ctx = btn._make_context(painter)
    btn._painter.paint(ctx)
    painter.end()

    assert len(called) >= 1
    assert called[0].width() == 100
    assert called[0].height() == 40


def test_button_extra_layers(qtbot):
    class CustomExtraLayer(Layer):
        scope = "widget"

        def __init__(self):
            self.draw_count = 0

        def draw(self, ctx: DrawContext, tm: ThemeManager):
            self.draw_count += 1

    extra = CustomExtraLayer()
    btn = Button(text="Extra", extra_layers=[extra], size=(80, 30))
    qtbot.addWidget(btn)

    img = QImage(btn.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    ctx = btn._make_context(painter)
    btn._painter.paint(ctx)
    painter.end()

    assert extra.draw_count >= 1


def test_public_layers_exports():
    import sli_ui_toolkit.widgets as w
    import sli_ui_toolkit.ui.widgets.buttons as b

    for symbol in (
        "Layer",
        "DrawContext",
        "default_layers",
        "OverlayPainterLayer",
        "OverlayPainterCallback",
        "BackgroundLayer",
        "RippleLayer",
        "ContentLayer",
    ):
        assert hasattr(w, symbol), f"sli_ui_toolkit.widgets missing {symbol}"
        assert hasattr(b, symbol), f"sli_ui_toolkit.ui.widgets.buttons missing {symbol}"
