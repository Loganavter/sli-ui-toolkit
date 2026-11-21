"""`SurfacePanel` — a token-painted container, the toolkit's answer to a page's `background-color` rule."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import SurfacePanel


@pytest.fixture(autouse=True)
def _dark_theme(qapp):
    # Registering the palettes is the step that makes tokens resolve at all; without it every token falls back to black
    # and the colour assertions below would compare black to black.
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme(FLUENT_DARK)
    yield
    manager.set_theme(FLUENT_LIGHT)


def _render(widget, size=(40, 30)) -> QImage:
    widget.resize(*size)
    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    return image


def _token(name: str):
    return ThemeManager.get_instance().get_color(name)


def test_it_fills_with_the_token_colour(qapp):
    panel = SurfacePanel(background_token="surface.list")
    image = _render(panel)
    assert image.pixelColor(20, 15) == _token("surface.list")


def test_none_paints_nothing(qapp):
    panel = SurfacePanel(background_token=None)
    image = _render(panel)
    assert image.pixelColor(20, 15).alpha() == 0


def test_radius_keeps_the_corner_transparent(qapp):
    square = _render(SurfacePanel(background_token="surface.list"))
    rounded = _render(SurfacePanel(background_token="surface.list", radius=8))
    assert square.pixelColor(0, 0).alpha() == 255
    assert rounded.pixelColor(0, 0).alpha() == 0
    assert rounded.pixelColor(20, 15) == _token("surface.list")


def test_border_draws_on_an_empty_panel(qapp):
    panel = SurfacePanel(background_token=None, border_token="button.dialog.default.background")
    image = _render(panel)
    assert image.pixelColor(0, 15).alpha() == 255
    assert image.pixelColor(20, 15).alpha() == 0


def test_an_unknown_token_paints_nothing_instead_of_raising(qapp):
    panel = SurfacePanel(background_token="surface.no.such.token")
    image = _render(panel)
    assert image.pixelColor(20, 15).alpha() == 0


def test_switching_the_token_repaints(qapp):
    panel = SurfacePanel(background_token="surface.list")
    _render(panel)
    panel.set_background_token("surface.background")
    image = _render(panel)
    assert image.pixelColor(20, 15) == _token("surface.background")


def test_no_stylesheet_is_used(qapp):
    panel = SurfacePanel(background_token="surface.list", radius=4, border_token="surface.background")
    assert panel.styleSheet() == ""
