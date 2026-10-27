"""HiDPI rasters: allocate in DEVICE px, tag the ratio, paint in logical px.

The defect class this guards: a raster allocated in LOGICAL px and then tagged
with ``setDevicePixelRatio(dpr)`` gets a logical canvas of ``size / dpr``, so at
DPR 2 it covers a quarter of its widget (button static snapshot), the marquee
strip draws native-size glyphs into a half-size canvas (clipped + offset), an
icon recolour that drops the tag paints twice as large, and a "scaled" cover is
a half-resolution raster the painter upsamples. ``QPainter`` scales every
command by the paint device's ratio (``combinedTransform`` = dpr,
``worldTransform`` = identity), so the fix is always arithmetic: allocate
``round(logical * dpr)`` and let the tagged ratio carry the logical geometry.

Cheap guard used throughout (pure arithmetic, no window): the returned raster's
``deviceIndependentSize()`` equals the intended LOGICAL rect, at DPR 1, 1.25
and 2. The live ratio comes from the environment, so the file runs under each
``QT_SCALE_FACTOR``; per-call ratios are passed explicitly where the API has a
``dpr`` parameter.

The rounded-CSD mask is the one raster that was already device-resolution (its
QImage is allocated at ``round(logical * dpr)`` and tagged), so its case is a
regression guard rather than a fix: a mask built at logical resolution and
upscaled would reach the corner edge in ``radius`` device rows instead of
``radius * dpr``.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.icon_manager import _recolor_pixmap
from sli_ui_toolkit.ui.windows.rounded_body import apply_rounded_window_mask
from sli_ui_toolkit.ui.widgets.buttons import (
    Button,
    ButtonRegion,
    ButtonRow,
    VerticalSplit,
)
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


# -- button static snapshot (buttons/button.py) -----------------------------


def _live_dpr() -> float:
    app = QApplication.instance() or QApplication([])
    return max(1.0, float(app.primaryScreen().devicePixelRatio() or 1.0))


def _device_image(widget) -> QImage:
    dpr = _live_dpr()
    image = QImage(
        max(1, int(round(widget.width() * dpr))),
        max(1, int(round(widget.height() * dpr))),
        QImage.Format.Format_ARGB32,
    )
    image.setDevicePixelRatio(dpr)
    image.fill(0)
    return image


def _make_card() -> Button:
    """Card whose cover pixmap fills the region + a crawling filename row."""
    cover = QPixmap(120, 40)
    cover.fill(Qt.GlobalColor.darkGray)
    btn = Button(
        regions=[
            ButtonRegion(id="cover", pixmap=cover),
            ButtonRegion(
                id="text",
                rows=[
                    ButtonRow(text="2m ago", size=11),
                    ButtonRow(
                        text=LONG_TEXT,
                        size=11,
                        h_align=Qt.AlignmentFlag.AlignLeft,
                        marquee=True,
                    ),
                ],
            ),
        ],
        split=VerticalSplit(),
        size=(120, 64),
        content_padding=(8, 4, 8, 4),
    )
    btn.resize(120, 64)
    return btn


def test_static_snapshot_covers_the_whole_widget(qapp) -> None:
    """The marquee snapshot is device-sized, not a quarter-size quadrant."""
    btn = _make_card()
    dpr = _live_dpr()
    try:
        btn.show()
        qapp.processEvents()
        image = _device_image(btn)
        btn.render(image, QPoint(0, 0))
        qapp.processEvents()
        snapshot = btn._static_cache  # noqa: SLF001 — the raster under test
        assert snapshot is not None, "cache must warm on a full paint"
        assert snapshot.deviceIndependentSize() == QSizeF(btn.size()), (
            "snapshot logical size must equal the widget: allocating in logical "
            "px and tagging dpr shrinks the canvas to size/dpr"
        )
        assert snapshot.width() == int(round(btn.width() * dpr))
        assert snapshot.height() == int(round(btn.height() * dpr))
        # Ink density: a quadrant-sized snapshot renders roughly dpr^2 less
        # ink than the same frame painted full.
        full_ink = _ink_pixels(image)
        snap_ink = _ink_pixels(snapshot.toImage())
        assert snap_ink >= full_ink * 0.9, (
            f"snapshot ink {snap_ink} vs full frame {full_ink}: the snapshot "
            "does not cover the widget"
        )
    finally:
        btn.deleteLater()


def test_fast_frame_matches_full_frame_at_device_pixels(qapp) -> None:
    """Blitting the snapshot back reproduces the full frame byte for byte."""
    btn = _make_card()
    try:
        btn.show()
        qapp.processEvents()
        image = _device_image(btn)
        btn.render(image, QPoint(0, 0))
        qapp.processEvents()
        driver = btn._marquee_driver  # noqa: SLF001
        driver.phase = 7.0
        btn._marquee_phase = 7.0  # noqa: SLF001 — mirror the tick write

        full_image = _device_image(btn)
        btn.render(full_image, QPoint(0, 0))

        dirty = driver.dirty_rect()
        assert dirty is not None and not dirty.isEmpty()
        region = QRegion(dirty)
        fast_image = full_image.copy()
        btn.render(fast_image, region.boundingRect().topLeft(), region)

        scale = _live_dpr()
        dev_dirty = QRect(
            int(dirty.left() * scale),
            int(dirty.top() * scale),
            int(dirty.width() * scale),
            int(dirty.height() * scale),
        )
        mismatches = [
            (x, y)
            for y in range(dev_dirty.top(), dev_dirty.bottom() + 1)
            for x in range(dev_dirty.left(), dev_dirty.right() + 1)
            if full_image.pixel(x, y) != fast_image.pixel(x, y)
        ]
        assert mismatches == [], (
            f"{len(mismatches)} device pixels differ, e.g. {mismatches[:5]}"
        )
    finally:
        btn.deleteLater()


# -- rounded CSD mask (windows/rounded_body.py) -----------------------------


def _mask_left_edges(region, rows: int, span: int) -> list[int | None]:
    edges: list[int | None] = []
    for y in range(rows):
        edge = None
        for x in range(span):
            if region.contains(QPoint(x, y)):
                edge = x
                break
        edges.append(edge)
    return edges


def test_rounded_mask_covers_the_widget_at_device_resolution(qapp) -> None:
    """Mask is one device px per device px — never a quadrant, never half-res."""
    dpr = _live_dpr()
    widget = QWidget()
    try:
        widget.resize(120, 60)
        apply_rounded_window_mask(widget, radius=12.0)
        region = widget.mask()
        assert not region.isEmpty()
        assert region.boundingRect() == QRect(
            0, 0, int(round(120 * dpr)), int(round(60 * dpr))
        ), "mask must cover the whole widget in device px"

        radius = 12.0
        edges = _mask_left_edges(region, int(round(radius * dpr * 2.5)), 120)
        first_zero = next(
            (i for i, edge in enumerate(edges) if edge == 0), None
        )
        assert first_zero is not None, "corner arc never reaches the edge"
        # A device-resolution arc spans ~radius*dpr rows; a raster built at
        # logical resolution and upscaled reaches x=0 at ~radius rows.
        assert first_zero >= 0.6 * radius * dpr, (
            f"corner arc spans {first_zero} device rows for radius "
            f"{radius} at dpr {dpr}: rasterized below device resolution"
        )
        # Interior stays unmasked.
        assert region.contains(QPoint(int(60 * dpr), int(30 * dpr)))
    finally:
        widget.deleteLater()


def test_rounded_mask_excludes_the_corner_outside_the_arc(qapp) -> None:
    """The guard above must not pass on a mask that clips nothing."""
    dpr = _live_dpr()
    widget = QWidget()
    try:
        widget.resize(120, 60)
        apply_rounded_window_mask(widget, radius=12.0)
        region = widget.mask()
        assert not region.contains(QPoint(0, 0))
        assert region.contains(QPoint(int(60 * dpr), int(30 * dpr)))
    finally:
        widget.deleteLater()
