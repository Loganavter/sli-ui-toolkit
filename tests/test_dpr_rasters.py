"""HiDPI rasters: allocate in DEVICE px, tag the ratio, paint in logical px.

The defect class this guards: a raster allocated in LOGICAL px and then tagged
with ``setDevicePixelRatio(dpr)`` gets a logical canvas of ``size / dpr``, so at
DPR 2 it covers a quarter of its widget (button static snapshot), the marquee
strip draws native-size glyphs into a half-size canvas (clipped + offset), an
icon recolour that drops the tag paints twice as large, and a "scaled" cover is
a half-resolution raster the painter upsamples. ``QPainter`` scales every
command by the paint device's ratio, so the fix is always arithmetic: allocate
``round(logical * dpr)`` and let the tagged ratio carry the logical geometry.

Cheap guard used throughout (pure arithmetic, no window): the returned raster's
``deviceIndependentSize()`` equals the intended LOGICAL rect, at DPR 1, 1.25
and 2. The live ratio comes from the environment, so the file runs under each
``QT_SCALE_FACTOR``; per-call ratios are passed explicitly where the API has a
``dpr`` parameter.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.widgets.helpers.marquee_text import (
    _render_marquee_strip,
    marquee_cycle_px,
)

DPRS = (1.0, 1.25, 2.0)
LONG_TEXT = "Comparison gallery filename number 12345 " * 3


def _ink_pixels(image: QImage) -> int:
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 40
    )


# -- marquee strip (helpers/marquee_text.py) --------------------------------


@pytest.mark.parametrize("dpr", DPRS)
def test_marquee_strip_geometry_is_logical_at_device_resolution(qapp, dpr) -> None:
    """Strip raster is ``cycle x height`` logical, allocated at ``dpr``."""
    text_width = 300
    height = 20
    gap = 40
    cycle = marquee_cycle_px(text_width, gap=gap)
    strip = _render_marquee_strip(
        font=QFont("Sans", 11),
        pen=QColor("white"),
        text=LONG_TEXT,
        text_width=text_width,
        height=height,
        gap=gap,
        dpr=dpr,
    )
    assert not strip.isNull()
    assert strip.devicePixelRatio() == pytest.approx(dpr)
    logical = strip.deviceIndependentSize()
    assert logical.width() == pytest.approx(cycle, abs=1.0)
    assert logical.height() == pytest.approx(height, abs=1.0)
    assert strip.width() == int(round(cycle * dpr))


@pytest.mark.parametrize("dpr", DPRS)
def test_marquee_strip_glyphs_match_direct_draw_text(qapp, dpr) -> None:
    """The strip paints the same glyph run the direct ``drawText`` path does."""
    text_width = 300
    height = 20
    gap = 40
    cycle = marquee_cycle_px(text_width, gap=gap)
    font = QFont("Sans", 11)
    strip = _render_marquee_strip(
        font=font,
        pen=QColor("white"),
        text=LONG_TEXT,
        text_width=text_width,
        height=height,
        gap=gap,
        dpr=dpr,
    )

    reference = QImage(
        max(1, int(round(cycle * dpr))),
        max(1, int(round(height * dpr))),
        QImage.Format.Format_ARGB32,
    )
    reference.setDevicePixelRatio(dpr)
    reference.fill(0)
    painter = QPainter(reference)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(
        QRect(0, 0, cycle, height),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        LONG_TEXT,
    )
    painter.end()

    strip_image = strip.toImage()
    strip_ink = _ink_pixels(strip_image)
    ref_ink = _ink_pixels(reference)
    # A half-size canvas clips the run and draws it at the wrong scale; both
    # show up as a large ink deficit against the direct path.
    assert strip_ink >= ref_ink * 0.8, (
        f"strip ink {strip_ink} vs direct drawText {ref_ink} at dpr {dpr}"
    )
    # The run must reach the text width, not stop at half the cycle.
    rightmost = max(
        x
        for y in range(strip_image.height())
        for x in range(strip_image.width())
        if strip_image.pixelColor(x, y).alpha() > 40
    )
    assert rightmost >= int(round(text_width * dpr)) - 8
