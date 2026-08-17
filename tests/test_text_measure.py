"""Toolkit text normalizer: measure_text_width + ButtonRow default-font sizing."""

from __future__ import annotations

from PySide6.QtGui import QFontMetrics, QImage, QPainter

from sli_ui_toolkit.ui.managers.ui_font import measure_text_width, ui_font
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow


def _glyph_bbox_width(button, qtbot) -> int:
    """Width of the painted glyph pixels (alpha > 0) of a ghost button."""
    from PySide6.QtCore import QRect

    img = QImage(button.size(), QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    button._painter.paint(button._make_context(painter))
    painter.end()

    left = right = None
    for x in range(img.width()):
        has = any(img.pixelColor(x, y).alpha() > 40 for y in range(img.height()))
        if has:
            if left is None:
                left = x
            right = x
    if left is None:
        return 0
    return right - left + 1


def test_measure_text_width_adds_fudge(qtbot):
    fm = QFontMetrics(ui_font(pixel_size=13))
    text = "Save Project As…"
    expected = max(fm.horizontalAdvance(text), fm.boundingRect(text).width()) + 8
    assert measure_text_width(fm, text) == expected
    # A panel sized to raw horizontalAdvance clips (boundingRect can exceed it);
    # the normalizer always leaves the +8px fudge.
    assert measure_text_width(fm, text) > fm.horizontalAdvance(text)
    assert measure_text_width(fm, "") == 0


def test_button_row_size_none_uses_default_ui_font(qtbot):
    """ButtonRow(size=None) renders at the default UI font, not a pixel override."""
    from PySide6.QtCore import QRect

    def _show_button(qtbot, row_size):
        btn = Button(
            rows=[ButtonRow(text="WWWW", size=row_size)],
            variant="ghost",
            size=(240, 36),
        )
        qtbot.addWidget(btn)
        btn.show()
        qtbot.waitExposed(btn)
        return btn

    default_btn = _show_button(qtbot, None)
    small_btn = _show_button(qtbot, 8)

    default_w = _glyph_bbox_width(default_btn, qtbot)
    small_w = _glyph_bbox_width(small_btn, qtbot)

    # "WWWW" at the default UI font is clearly wider than at 8px.
    assert default_w > small_w + 8
    # And it matches the default font's advance (within the painted tolerance).
    expected = QFontMetrics(ui_font()).horizontalAdvance("WWWW")
    assert abs(default_w - expected) <= 6
