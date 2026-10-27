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
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.managers.icon_manager import _recolor_pixmap
from sli_ui_toolkit.ui.widgets.buttons.content import _scaled_pixmap_rect
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


# -- icon recolour (managers/icon_manager.py) -------------------------------


@pytest.mark.parametrize("dpr", DPRS)
def test_recolor_pixmap_keeps_device_pixel_ratio(qapp, dpr) -> None:
    """Tinting must not drop the ratio: the icon would paint ``dpr``x larger."""
    source = QPixmap(64, 64)
    source.setDevicePixelRatio(dpr)
    source.fill(QColor(200, 30, 30))

    result = _recolor_pixmap(source)

    assert result.size() == source.size()
    assert result.devicePixelRatio() == pytest.approx(dpr)
    assert result.deviceIndependentSize() == source.deviceIndependentSize()
    # SourceIn fill: the opaque source coverage comes out tinted, and the
    # glyph keeps its place instead of drifting to the top-left corner.
    assert _ink_pixels(result.toImage()) == 64 * 64


# -- cover/contain/stretch (buttons/content.py) -----------------------------


@pytest.mark.parametrize("dpr", DPRS)
def test_scaled_pixmap_rect_rasters_at_device_resolution(qapp, dpr) -> None:
    """The scaled cover is allocated in device px and tagged with the ratio."""
    source = QPixmap(40, 20)
    source.fill(QColor(10, 60, 200))
    target = QRect(5, 7, 20, 20)

    for fill in ("stretch", "cover", "contain"):
        scaled, dest = _scaled_pixmap_rect(source, target, fill, dpr=dpr)
        assert scaled.devicePixelRatio() == pytest.approx(dpr), fill
        assert scaled.deviceIndependentSize().width() == pytest.approx(
            dest.width(), abs=1.0
        ), fill
        assert scaled.deviceIndependentSize().height() == pytest.approx(
            dest.height(), abs=1.0
        ), fill
        assert scaled.width() == int(round(dest.width() * dpr)), fill

    # Contain fits inside the target; cover fills it.
    _, contain_dest = _scaled_pixmap_rect(source, target, "contain", dpr=dpr)
    assert contain_dest.width() <= target.width()
    assert contain_dest.height() <= target.height()
    _, cover_dest = _scaled_pixmap_rect(source, target, "cover", dpr=dpr)
    assert cover_dest.width() >= target.width()
    assert cover_dest.height() >= target.height()


def test_scaled_pixmap_rect_cache_is_dpr_aware(qapp) -> None:
    """One entry per ratio: a screen move must not reuse the old raster."""
    source = QPixmap(40, 20)
    source.fill(QColor(10, 60, 200))
    target = QRect(0, 0, 20, 20)
    one, _ = _scaled_pixmap_rect(source, target, "cover", dpr=1.0)
    two, _ = _scaled_pixmap_rect(source, target, "cover", dpr=2.0)
    assert one.cacheKey() != two.cacheKey()
    assert two.width() == one.width() * 2


def test_scaled_pixmap_rect_defaults_to_source_ratio(qapp) -> None:
    """Standalone callers (no painter) keep the source's own ratio."""
    source = QPixmap(40, 20)
    source.setDevicePixelRatio(2.0)
    source.fill(QColor(10, 60, 200))
    scaled, dest = _scaled_pixmap_rect(source, QRect(0, 0, 20, 20), "stretch")
    assert scaled.devicePixelRatio() == pytest.approx(2.0)
    assert dest.size().width() == 20
    assert scaled.deviceIndependentSize().height() == pytest.approx(
        dest.height(), abs=1.0
    )
