from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import QImage, QPainter

from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers.background import (
    is_uniform_radii,
    rounded_rect_path,
)
from sli_ui_toolkit.ui.widgets.buttons.specs import (
    ShapeSpec,
    normalize_corner_radii,
)


def _render(widget) -> QImage:
    widget.resize(48, 36)
    widget.show()
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image, QPoint(0, 0))
    return image


def test_normalize_radii_uniform():
    assert normalize_corner_radii(10, None) == (10, 10, 10, 10)


def test_normalize_radii_explicit():
    assert normalize_corner_radii(10, (0, 10, 0, 0)) == (0, 10, 0, 0)


def test_normalize_radii_fallback():
    assert normalize_corner_radii(None, None, fallback=4) == (4, 4, 4, 4)


def test_is_uniform_helper():
    assert is_uniform_radii((6, 6, 6, 6))
    assert not is_uniform_radii((0, 10, 0, 0))


def test_rounded_rect_path_uniform_matches_addRoundedRect_geometry():
    """When all 4 radii are equal, the manually-built path should fully
    contain the same points as Qt's drawRoundedRect output, i.e. the rect
    interior should still be inside the path."""
    rect = QRectF(0, 0, 40, 30)
    path = rounded_rect_path(rect, (6, 6, 6, 6))
    # Center is always inside.
    assert path.contains(rect.center())
    # Far corner is OUTSIDE (since corner is rounded).
    assert not path.contains(rect.topLeft())


def test_rounded_rect_path_per_corner_only_one_rounded():
    rect = QRectF(0, 0, 40, 30)
    # Only top-right rounded.
    path = rounded_rect_path(rect, (0, 8, 0, 0))
    # Top-left corner has 0 radius, must be inside.
    assert path.contains(rect.topLeft() + (rect.center() - rect.topLeft()) * 0.01)
    # Top-right corner is rounded, the extreme top-right point is outside.
    assert not path.contains(rect.topRight())


def test_rounded_rect_path_clamps_radii_to_half_size():
    rect = QRectF(0, 0, 10, 10)
    # Radius larger than half — should clamp without crashing.
    path = rounded_rect_path(rect, (100, 100, 100, 100))
    assert not path.isEmpty()
    assert path.contains(rect.center())


def test_button_accepts_corner_radii_kwarg(qapp):
    btn = Button(corner_radii=(0, 10, 0, 0), size=(46, 36))
    assert btn._corner_radii_px == (0, 10, 0, 0)
    # Rendering should not raise.
    _render(btn)


def test_button_corner_radius_alone_still_works(qapp):
    btn = Button(corner_radius=4, size=(46, 36))
    assert btn._corner_radii_px is None
    _render(btn)


def test_shape_spec_resolves_explicit_radii():
    spec = ShapeSpec(corner_radius=6, corner_radii=(0, 10, 0, 0))
    assert spec.resolved_corner_radii() == (0, 10, 0, 0)


def test_shape_spec_resolves_uniform_from_corner_radius():
    spec = ShapeSpec(corner_radius=6)
    assert spec.resolved_corner_radii() == (6, 6, 6, 6)
