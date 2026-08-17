"""Timeline lane/group labels resolve their font through ui_font().

Regression: the track titles and channel labels in the left gutter were
painted with the raw painter font (design-sized, unscaled), so at UI
scale > 1.0 the lane names stayed small while the ruler and group headers
grew. The label painters now go through ui_font() like
draw_group_header_label, applying the UiScale factor exactly once.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.primitives import (
    draw_channel_label,
    draw_track_title_label,
)


def _paint_labels(factor: float) -> list[float]:
    """Paint both label functions, returning every font size set on the painter."""
    import sys

    from PySide6.QtGui import QFont

    # managers/__init__ re-exports ui_font as an attribute, shadowing the
    # submodule; reach the real module through sys.modules.
    uf_mod = sys.modules["sli_ui_toolkit.ui.managers.ui_font"]

    calls: list[float] = []

    def _fake_ui_font(**overrides):
        # Mirrors UiFont.resolve(point_size=...): design pt * factor.
        design = overrides.get("point_size")
        font = QFont()
        if design is not None:
            font.setPointSizeF(float(design) * factor)
        return font

    original = uf_mod.ui_font
    uf_mod.ui_font = _fake_ui_font
    try:
        image = QImage(400, 200, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        real_set_font = painter.setFont

        def _tracking_set_font(font):
            calls.append(font.pointSizeF())
            return real_set_font(font)

        painter.setFont = _tracking_set_font
        host = QWidget()
        rect = QRectF(0, 0, 180, 30)
        draw_track_title_label(host, painter, rect, "Position", QColor("white"))
        draw_channel_label(host, painter, rect, "Value", QColor("white"), QColor("red"))
        painter.end()
    finally:
        uf_mod.ui_font = original
    return calls


def test_lane_labels_font_scales_with_ui_scale(qtbot):
    """Track/channel labels must paint with pointSize * factor."""
    from PySide6.QtGui import QFont

    # The label painters derive their design size from the painter font
    # (the widget's inherited font, design-sized) floored at 8pt.
    design_pt = max(8, QFont().pointSize())

    try:
        UiScale.get_instance().set_factor(1.0)
        calls_1x = _paint_labels(1.0)
        UiScale.get_instance().set_factor(2.0)
        calls_2x = _paint_labels(2.0)
    finally:
        UiScale.get_instance().set_factor(1.0)

    assert len(calls_1x) == 2 and len(calls_2x) == 2
    # Each label painter must resolve its font through ui_font() (i.e. the
    # font it sets carries the scale factor), not paint the raw design font.
    assert calls_1x[0] == design_pt, calls_1x
    assert calls_2x[0] == design_pt * 2.0, (
        f"track title font did not scale: 1.0x={calls_1x[0]} 2.0x={calls_2x[0]}"
    )
    assert calls_2x[1] == design_pt * 2.0, (
        f"channel label font did not scale: 1.0x={calls_1x[1]} 2.0x={calls_2x[1]}"
    )
