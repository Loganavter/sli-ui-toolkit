"""Icon pixmaps and the ratio helpers the app imports from this package.

The app's icon fix (app PR #769) imports three names from ``sli_ui_toolkit.widgets``:
``normalized_icon_pixmap`` (now with a ``dpr=`` keyword), ``painter_dpr`` and
``widget_dpr``. None of them existed at the package root, and the last two did not
exist at all — the app could not even import its title-bar module
(``ui/main_window/csd_menu_strip.py``) on ``main``, so the whole CSD strip was dead.
These tests pin the contract the app calls into.

The rule they encode: the ratio is applied ONCE, to the pixmap. ``QPainter`` already
scales commands by the paint device's ratio, so a caller that also multiplies its
geometry scales twice — which is why the helpers read a ratio instead of letting each
call site invent one.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    normalized_icon_pixmap,
    painter_dpr,
    widget_dpr,
)


def _icon() -> QIcon:
    # 128 px source: QIcon.pixmap() never upscales beyond the source, so a small
    # source would silently clamp the device-pixel request (measured here).
    source = QPixmap(128, 128)
    source.fill(QColor("#336699"))
    return QIcon(source)


@pytest.mark.parametrize("dpr", [None, 1.0, 1.25, 2.0])
def test_the_pixmap_covers_the_requested_logical_size(qapp, dpr):
    pixmap = normalized_icon_pixmap(_icon(), 16, dpr=dpr) if dpr else normalized_icon_pixmap(_icon(), 16)
    ratio = float(pixmap.devicePixelRatio())
    assert pixmap.deviceIndependentSize() == QSize(16, 16), (
        "the caller asked for 16 logical px; the pixmap must paint at 16"
    )
    assert pixmap.width() == max(1, int(round(16 * ratio)))
    assert ratio == (dpr or 1.0)


def test_qsize_targets_work_the_same_way(qapp):
    # Square on purpose: QIcon.pixmap() aspect-fits and never upscales, so a
    # non-square target comes back smaller by Qt's own contract.
    pixmap = normalized_icon_pixmap(_icon(), QSize(24, 24), dpr=2.0)
    assert pixmap.deviceIndependentSize() == QSize(24, 24)


def test_the_cache_does_not_serve_one_ratio_for_another(qapp):
    plain = normalized_icon_pixmap(_icon(), 16)
    hidpi = normalized_icon_pixmap(_icon(), 16, dpr=2.0)
    assert plain.cacheKey() != hidpi.cacheKey()
    assert plain.devicePixelRatio() != hidpi.devicePixelRatio()


def test_painter_dpr_reads_the_paint_device(qapp):
    hidpi = QPixmap(64, 64)
    hidpi.setDevicePixelRatio(2.0)
    painter = QPainter(hidpi)
    try:
        assert painter_dpr(painter) == 2.0
    finally:
        painter.end()

    plain = QPixmap(64, 64)
    painter = QPainter(plain)
    try:
        assert painter_dpr(painter) == 1.0
    finally:
        painter.end()


@pytest.mark.parametrize("value", [None, object(), "not a painter"])
def test_painter_dpr_falls_back_to_one(value):
    assert painter_dpr(value) == 1.0


def test_widget_dpr_reads_the_widget_and_falls_back(qapp):
    widget = QWidget()
    assert widget_dpr(widget) == 1.0
    assert widget_dpr(None) == 1.0
    assert widget_dpr(object()) == 1.0
