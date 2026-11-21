"""ImageLabel: pixmap set/clear, scaled vs native draw, alignment, background, DPR hint."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPixmap

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import ImageLabel

_RED = QColor(220, 40, 40, 255)


def _solid_pixmap(width: int, height: int, color: QColor = _RED) -> QPixmap:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)
    return QPixmap.fromImage(image)


def _render(widget: ImageLabel, size: tuple[int, int]) -> QImage:
    widget.resize(*size)
    widget.show()
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image, QPoint(0, 0))
    return image


def _assert_transparent(image: QImage, x: int, y: int) -> None:
    assert image.pixelColor(x, y).alpha() == 0


def test_set_and_clear_pixmap(qapp):
    label = ImageLabel()
    assert label.pixmap().isNull()
    assert label.has_pixmap() is False

    source = _solid_pixmap(40, 20)
    label.setPixmap(source)
    assert label.has_pixmap() is True
    assert label.pixmap().size() == QSize(40, 20)

    label.clear()
    assert label.pixmap().isNull()
    assert label.has_pixmap() is False


def test_unscaled_size_hint_is_the_pixmap_size(qapp):
    label = ImageLabel()
    label.setPixmap(_solid_pixmap(40, 20))
    assert label.sizeHint() == QSize(40, 20)
    # QLabel's scaledContents does not change the hint either: the image's
    # native size stays the preferred size, the widget may still shrink.
    label.setScaledContents(True)
    assert label.sizeHint() == QSize(40, 20)


def test_dpr_tagged_pixmap_hint_divides_out_the_ratio(qapp):
    label = ImageLabel()
    pixmap = _solid_pixmap(64, 64)
    # A deliberately non-live ratio: the offscreen run is 1x, so 2x here only
    # exercises the deviceIndependentSize division, not an assumption about
    # the screen.
    pixmap.setDevicePixelRatio(2.0)
    label.setPixmap(pixmap)
    assert label.sizeHint() == QSize(32, 32)


def test_unscaled_pixmap_is_centred_with_transparent_corners(qapp):
    label = ImageLabel()
    label.setPixmap(_solid_pixmap(20, 20))
    image = _render(label, (100, 100))

    _assert_transparent(image, 0, 0)
    _assert_transparent(image, 99, 99)
    assert image.pixelColor(50, 50) == _RED


def test_scaled_contents_fills_the_widget(qapp):
    label = ImageLabel()
    label.setPixmap(_solid_pixmap(40, 20))
    label.setScaledContents(True)
    image = _render(label, (100, 50))

    assert image.pixelColor(0, 0) == _RED
    assert image.pixelColor(99, 49) == _RED


def test_scaled_contents_stretches_like_qlabel(qapp):
    # QLabel semantics: `setScaledContents(True)` fills the whole contents rect and does NOT preserve the aspect ratio.
    # The widget's first behaviour letterboxed a 1:2 image in a square widget; a host replacing QLabel measures that as
    # a 1-2% page difference, so the widget follows QLabel (measured against the host's stock build).
    label = ImageLabel()
    label.setPixmap(_solid_pixmap(20, 40))
    label.setScaledContents(True)
    image = _render(label, (100, 100))

    assert image.pixelColor(0, 50) == _RED
    assert image.pixelColor(99, 50) == _RED
    assert image.pixelColor(50, 50) == _RED


def test_alignment_places_the_unscaled_pixmap(qapp):
    label = ImageLabel()
    label.setPixmap(_solid_pixmap(20, 20))
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    image = _render(label, (100, 100))

    assert image.pixelColor(0, 0) == _RED
    _assert_transparent(image, 50, 50)


def test_corner_is_transparent_by_default(qapp):
    label = ImageLabel()
    label.setPixmap(_solid_pixmap(20, 20))
    image = _render(label, (100, 100))
    _assert_transparent(image, 0, 0)


def test_background_token_paints_the_surface(qapp):
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    expected = manager.get_color("surface.background")

    label = ImageLabel(background_token="surface.background")
    image = _render(label, (20, 20))

    assert image.pixelColor(0, 0) == expected
    assert image.pixelColor(19, 19) == expected


def test_text_is_empty_and_settext_is_a_no_op(qapp):
    label = ImageLabel()
    label.setText("ignored")
    assert label.text() == ""
    assert label.pixmap().isNull()
