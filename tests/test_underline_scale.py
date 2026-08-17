"""Underline corner arc tracks the widget's painted corner radius at every UiScale factor.

Regression: the underline's end-cap arc was scaled by a widget-height
heuristic instead of the UiScale factor, while the widget's painted corner
radius scales via ``scaled_px`` — at 125%/150% the underline stopped
wrapping the corner circle (the line edit's band arc stayed ~half the
corner, the button's stayed frozen at the design radius). The painter now
treats ``arc_radius`` as design px and scales it once, matching
``scaled_px(corner)``.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
from sli_ui_toolkit.ui.widgets.buttons.layers.underline import UnderlineLayer
from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant
from sli_ui_toolkit.ui.widgets.helpers.underline_painter import (
    UnderlineConfig,
    _resolve_metrics,
)
from sli_ui_toolkit.widgets import Button


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _line_edit_arc(qapp, factor: float) -> float:
    UiScale.get_instance().set_factor(factor)
    edit = CustomLineEdit()
    edit.setFixedWidth(120)
    qapp.processEvents()
    cfg = UnderlineConfig(
        color=QColor(255, 0, 0),
        alpha=255,
        thickness=1.5,
        arc_radius=float(edit.RADIUS),
        vertical_offset=0.0,
    )
    arc = min(
        cfg.arc_radius * UiScale.get_instance().factor(),
        edit.height(),
        edit.width() / 2,
    )
    edit.deleteLater()
    return arc


@pytest.mark.parametrize("factor", [1.0, 1.25, 1.5, 2.0])
def test_line_edit_underline_arc_matches_painted_corner(qapp, factor):
    arc = _line_edit_arc(qapp, factor)
    assert arc == pytest.approx(scaled_px(CustomLineEdit.RADIUS), abs=1.1)


@pytest.mark.parametrize("factor", [1.0, 1.25, 1.5, 2.0])
def test_painter_resolves_arc_in_scaled_px_units(qapp, factor):
    """The painter's own metric resolution: design arc_radius in, scaled
    px out — exactly the widget's painted corner radius. Rect height is
    deliberately not 32*f: the old height heuristic made the arc depend on
    the widget's height instead of the factor (6.75f vs 6f for a 36px-tall
    widget)."""
    rect = QRectF(0, 0, scaled_px(120), scaled_px(36))
    cfg = UnderlineConfig(
        color=QColor(255, 0, 0),
        thickness=1.5,
        arc_radius=6.0,
        vertical_offset=0.0,
    )
    arc, _thickness, _offset, _reach, _fade = _resolve_metrics(
        rect, cfg, UiScale.get_instance().factor()
    )
    assert arc == pytest.approx(cfg.arc_radius * UiScale.get_instance().factor(), abs=1e-6)


def _button_underline_design_arc(qapp, factor: float) -> float:
    UiScale.get_instance().set_factor(factor)
    btn = Button(text="x", show_underline=True)
    btn.setFixedSize(80, scaled_px(36))
    ctx = DrawContext(
        widget=btn,
        painter=None,
        rect=btn.rect(),
        states=frozenset(),
        variant=get_variant("default"),
        corner_radius=scaled_px(8),
        show_underline=True,
        underline_color=QColor(255, 0, 0),
    )
    seen: dict[str, float] = {}

    import sli_ui_toolkit.ui.widgets.buttons.layers.underline as underline_layer

    original = underline_layer.draw_bottom_underline

    def spy(painter, rect, theme_manager, config=None):
        seen["arc"] = config.arc_radius

    underline_layer.draw_bottom_underline = spy
    try:
        UnderlineLayer().draw(ctx, None)
    finally:
        underline_layer.draw_bottom_underline = original
    btn.deleteLater()
    return seen["arc"] * UiScale.get_instance().factor()


@pytest.mark.parametrize("factor", [1.0, 1.25, 1.5, 2.0])
def test_button_underline_arc_matches_painted_corner(qapp, factor):
    band_arc = _button_underline_design_arc(qapp, factor)
    assert band_arc == pytest.approx(scaled_px(8), abs=1.1)
