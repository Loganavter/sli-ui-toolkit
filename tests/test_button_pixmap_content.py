"""PixmapContent cover/contain + corner_radii crop clip."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPixmap

from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRegion, ButtonSpec, ShapeSpec
from sli_ui_toolkit.ui.widgets.buttons.content import (
    PixmapContent,
    _scaled_pixmap_rect,
    coerce_pixmap,
    normalize_image_fill,
)
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path


def _solid_pixmap(w: int, h: int, color: QColor) -> QPixmap:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(color)
    return QPixmap.fromImage(img)


def _render(widget, size=(80, 48)) -> QImage:
    widget.resize(*size)
    widget.show()
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image, QPoint(0, 0))
    return image


def test_normalize_image_fill():
    assert normalize_image_fill("cover") == "cover"
    assert normalize_image_fill("CONTAIN") == "contain"
    assert normalize_image_fill("nope") == "cover"


def test_coerce_pixmap_from_qimage(qapp):
    img = QImage(8, 8, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 0, 0))
    pix = coerce_pixmap(img)
    assert pix is not None and not pix.isNull()
    assert pix.width() == 8


def test_scaled_cover_fills_target(qapp):
    src = _solid_pixmap(40, 10, QColor(0, 0, 255))
    target = QRect(0, 0, 20, 20)
    scaled, dest = _scaled_pixmap_rect(src, target, "cover")
    assert dest.width() >= 20 or dest.height() >= 20
    assert scaled.width() >= 20 and scaled.height() >= 20


def test_scaled_contain_fits_inside(qapp):
    src = _solid_pixmap(40, 10, QColor(0, 255, 0))
    target = QRect(0, 0, 20, 20)
    scaled, dest = _scaled_pixmap_rect(src, target, "contain")
    assert scaled.width() <= 20 and scaled.height() <= 20
    assert dest.width() == scaled.width()
    assert dest.height() == scaled.height()


def test_button_region_pixmap_builds_pixmap_content(qapp):
    thumb = _solid_pixmap(32, 18, QColor(40, 120, 200))
    btn = Button(
        regions=[
            ButtonRegion(
                id="cover",
                pixmap=thumb,
                image_fill="cover",
                corner_radii=(8, 8, 0, 0),
            )
        ],
        size=(80, 48),
    )
    content = btn._build_region_content(btn.regions()[0])
    assert isinstance(content, PixmapContent)
    assert content.image_fill == "cover"
    _render(btn)


def test_update_region_pixmap_and_radii(qapp):
    thumb_a = _solid_pixmap(16, 16, QColor(255, 0, 0))
    thumb_b = _solid_pixmap(16, 16, QColor(0, 255, 0))
    btn = Button(
        regions=[ButtonRegion(id="cover", pixmap=thumb_a, corner_radii=(4, 4, 0, 0))],
        size=(64, 40),
    )
    btn.update_region("cover", pixmap=thumb_b, corner_radii=(10, 10, 0, 0))
    region = btn.regions()[0]
    assert region.pixmap is thumb_b
    assert region.corner_radii == (10, 10, 0, 0)
    _render(btn)


def test_button_from_spec_carries_pixmap(qapp):
    thumb = _solid_pixmap(24, 12, QColor(10, 10, 10))
    spec = ButtonSpec(
        regions=(
            ButtonRegion(
                id="cover",
                pixmap=thumb,
                image_fill="contain",
                corner_radii=(6, 6, 6, 6),
            ),
        ),
        shape=ShapeSpec(size=(60, 40), corner_radius=6),
    )
    btn = Button.from_spec(spec)
    region = btn.regions()[0]
    assert region.image_fill == "contain"
    assert coerce_pixmap(region.pixmap) is not None
    _render(btn, size=(60, 40))


def test_pixmap_content_clips_to_corner_radii(qapp):
    """Extreme corner of a rounded cover should not keep opaque photo pixels."""
    thumb = _solid_pixmap(80, 48, QColor(255, 0, 0))
    btn = Button(
        regions=[
            ButtonRegion(
                id="cover",
                pixmap=thumb,
                image_fill="stretch",
                corner_radii=(16, 16, 16, 16),
                override_bg_color=QColor(0, 0, 0, 0),
                bg_locked=True,
            )
        ],
        size=(80, 48),
        corner_radius=16,
        variant="ghost",
    )
    image = _render(btn)
    corner = image.pixelColor(0, 0)
    path = rounded_rect_path(btn.rect(), (16, 16, 16, 16))
    assert not path.contains(QPoint(0, 0))
    # Cover is solid red; clipped corner must not be that photo pixel.
    assert not (corner.red() > 240 and corner.green() < 40 and corner.blue() < 40)
    center = image.pixelColor(40, 24)
    assert center.red() > 200 and center.green() < 40
