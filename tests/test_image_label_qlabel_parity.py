"""Parity with QLabel — the widget this one replaces, measured instead of assumed.

The host that migrated off stock ``QLabel`` measured a 1-2 % whole-page deviation from placement details that no
unit test here would have caught: a float centring that lands one pixel below QLabel's integer one, a default
alignment that was ``AlignCenter`` where QLabel's is ``AlignLeft|AlignVCenter``. So the oracle is QLabel itself:
render both widgets with the same pixmap, size and alignment, and diff the images.

Unscaled painting must be byte-identical. Scaled painting is asserted with a tolerance: QLabel's stretch goes through
``QStyle`` and resamples with a slightly different kernel than ``QPixmap.scaled`` - on a synthetic hard edge that is
0.3 % of the pixels differing by <= 40 colour levels, and nothing at all on real smooth artwork. What is asserted
exactly there is coverage: the whole contents rect is painted (no letterboxing, no aspect preservation).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QLabel

from sli_ui_toolkit.widgets import ImageLabel

ALIGNMENTS = (
    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    Qt.AlignmentFlag.AlignCenter,
    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
    Qt.AlignmentFlag.AlignJustify | Qt.AlignmentFlag.AlignTop,
)
SIZES = ((40, 20), (39, 19), (37, 17), (47, 27), (48, 28), (41, 33))
SCALED_SIZES = ((40, 20), (60, 60), (90, 20), (20, 90))


def _pixmap() -> QPixmap:
    pixmap = QPixmap(40, 20)
    pixmap.fill(QColor(230, 60, 90))
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, 8, 6, QColor(20, 240, 30))
    painter.end()
    return pixmap


def _render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    return image


def _diff(a: QImage, b: QImage) -> tuple[int, int]:
    """Mismatching pixel count and the largest single-channel delta."""
    assert a.size() == b.size()
    count = 0
    worst = 0
    for y in range(a.height()):
        for x in range(a.width()):
            left = a.pixelColor(x, y)
            right = b.pixelColor(x, y)
            if left != right:
                count += 1
                worst = max(
                    worst,
                    abs(left.red() - right.red()),
                    abs(left.green() - right.green()),
                    abs(left.blue() - right.blue()),
                    abs(left.alpha() - right.alpha()),
                )
    return count, worst


def _pair(size: tuple[int, int], alignment: Qt.AlignmentFlag | None, scaled: bool) -> tuple[QImage, QImage]:
    reference = QLabel()
    # QLabel fills its palette window colour behind the pixmap; in a host that colour comes from the page's
    # stylesheet, so the oracle drops the fill and compares the image placement itself.
    reference.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    widget = ImageLabel()
    for candidate in (reference, widget):
        candidate.setPixmap(_pixmap())
        candidate.setScaledContents(scaled)
        if alignment is not None:
            candidate.setAlignment(alignment)
        candidate.resize(*size)
    return _render(reference), _render(widget)


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("alignment", ALIGNMENTS)
def test_unscaled_placement_is_identical_to_qlabel(qapp, size, alignment):
    reference, widget = _pair(size, alignment, scaled=False)
    count, worst = _diff(reference, widget)
    assert (count, worst) == (0, 0), f"{size} {int(alignment)}: {count} px differ, worst {worst}"


@pytest.mark.parametrize("size", SIZES)
def test_default_alignment_matches_qlabel(qapp, size):
    # No setAlignment call at all: the Designer's default, and the case the host's pages actually hit.
    reference, widget = _pair(size, None, scaled=False)
    count, worst = _diff(reference, widget)
    assert (count, worst) == (0, 0), f"{size}: default alignment differs by {count} px, worst {worst}"


@pytest.mark.parametrize("size", SCALED_SIZES)
def test_scaled_coverage_and_filter_are_close_to_qlabel(qapp, size):
    reference, widget = _pair(size, None, scaled=True)
    count, worst = _diff(reference, widget)
    total = size[0] * size[1]
    # A stretch, not a letterbox: the corners of the contents rect are painted.
    for x, y in ((0, 0), (size[0] - 1, 0), (0, size[1] - 1), (size[0] - 1, size[1] - 1)):
        assert widget.pixelColor(x, y).alpha() == 255, f"{size}: corner ({x},{y}) not painted"
    assert worst <= 64, f"{size}: filter kernel deviates by {worst} colour levels"
    assert count <= total * 0.05, f"{size}: {count}/{total} px differ from QLabel"
