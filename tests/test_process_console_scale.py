"""ProcessConsoleWidget monospace text scales with UiScale.

Regression: the console painted its output with the raw system FixedFont
(design-sized), so the log text stayed small at UI scale > 1.0 while the
rest of the interface grew. The fixed font is now re-derived with the
factor applied (family preserved, size multiplied) and re-applied on
``scale_changed``.
"""

from __future__ import annotations

from PySide6.QtGui import QFontMetrics

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.widgets.composite.process_console_widget import (
    ProcessConsoleWidget,
)


def test_console_font_scales_with_ui_scale(qtbot):
    widget = ProcessConsoleWidget(max_entries=10)
    qtbot.addWidget(widget)

    base_pt = widget._fixed_font.pointSizeF()
    base_px = widget._fixed_font.pixelSize()
    assert base_pt > 0 or base_px > 0

    try:
        UiScale.get_instance().set_factor(1.0)
        widget._apply_fixed_font()
        size_1x = widget._fixed_font.pointSizeF() or widget._fixed_font.pixelSize()

        UiScale.get_instance().set_factor(2.0)
        widget._apply_fixed_font()
        size_2x = widget._fixed_font.pointSizeF() or widget._fixed_font.pixelSize()
    finally:
        UiScale.get_instance().set_factor(1.0)
        widget._apply_fixed_font()

    assert size_2x == 2.0 * size_1x, (
        f"console font did not scale: 1.0x={size_1x} 2.0x={size_2x}"
    )
    # The monospace family must survive the scale pass.
    assert widget.output.font() == widget._fixed_font
    assert widget.input_edit.font() == widget._fixed_font
