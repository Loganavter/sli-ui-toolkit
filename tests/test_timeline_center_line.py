"""Phase 1 center-line regression tests for TimelineWidget.

Covers the single-geometry work in
``src/sli_ui_toolkit/ui/widgets/composite/timeline_widget/``:

1. ``layout.row_center_y`` keeps ``.5`` centers from odd scaled heights
   (``UiScale`` rounds design px to whole px, so factors like 1.1 turn a
   30px lane into 33px with a ``.5`` center).
2. ``primitives.draw_center_line`` paints a 1px ``QRectF`` fill with no
   ``int()`` truncation of the span or the center (the old
   ``drawLine(int(...))`` floored both).
3. An end-to-end pixel check: the painted center row carries the line
   color while its neighbors do not.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    layout as timeline_layout,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    primitives as timeline_primitives,
)


@pytest.fixture
def _restore_scale():
    scale = UiScale.get_instance()
    old = scale.factor()
    try:
        yield scale
    finally:
        scale.set_factor(old)


def test_row_center_y_half_px_for_odd_heights():
    """Odd heights (from odd UiScale products) keep their .5 center."""
    assert timeline_layout.row_center_y(0.0, 33.0) == 16.5
    assert timeline_layout.row_center_y(72.0, 31.0) == 87.5
    assert timeline_layout.row_center_y(0.0, 30.0) == 15.0
    assert timeline_layout.row_center_y(0.0, 28.0) == 14.0


def test_row_center_y_under_odd_uiscale_factor(_restore_scale):
    """Factor 1.1 turns the 30px track lane odd — center stays .5."""
    _restore_scale.set_factor(1.1)
    track_h = scaled_px(30)
    channel_h = scaled_px(28)
    assert track_h % 2 == 1, track_h
    assert timeline_layout.row_center_y(0.0, track_h) * 2 == 2 * 0.0 + track_h
    assert (timeline_layout.row_center_y(0.0, track_h) % 1) == pytest.approx(0.5)
    assert (timeline_layout.row_center_y(0.0, channel_h) % 1) == pytest.approx(0.5)


def _fill_spy(monkeypatch):
    """Record ``QPainter.fillRect`` rects; forbid ``drawLine`` centers."""
    rects: list[QRectF] = []

    def _fill(self, *args):
        if args and isinstance(args[0], QRectF):
            rects.append(QRectF(args[0]))
        return QPainter.fillRect(self, *args)

    def _no_line(self, *args, **kwargs):
        raise AssertionError("center line must not use drawLine")

    monkeypatch.setattr(QPainter, "fillRect", _fill)
    monkeypatch.setattr(QPainter, "drawLine", _no_line)
    return rects


def _paint_center(monkeypatch, x0, x1, center_y):
    image = QImage(400, 60, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    try:
        rects = _fill_spy(monkeypatch)
        timeline_primitives.draw_center_line(
            painter, x0, x1, center_y, QColor("#ff0000")
        )
    finally:
        painter.end()
    return image, rects


def test_draw_center_line_fills_1px_qrectf(monkeypatch):
    """The primitive fills exactly ``[x0, x1) x [cy-0.5, cy+0.5)``."""
    _image, rects = _paint_center(monkeypatch, 10.0, 50.0, 20.5)
    assert len(rects) == 1, rects
    rect = rects[0]
    assert (rect.left(), rect.top(), rect.width(), rect.height()) == pytest.approx(
        (10.0, 20.0, 40.0, 1.0)
    )


def test_draw_center_line_no_int_truncation(monkeypatch):
    """Fractional spans survive: ``int()`` used to floor both edges."""
    _image, rects = _paint_center(monkeypatch, 180.7, 300.2, 44.5)
    assert len(rects) == 1, rects
    rect = rects[0]
    assert rect.left() == pytest.approx(180.7)
    assert rect.right() == pytest.approx(300.2)
    assert rect.top() == pytest.approx(44.0)
    assert rect.height() == pytest.approx(1.0)


def test_draw_center_line_empty_span_is_noop(monkeypatch):
    _image, rects = _paint_center(monkeypatch, 50.0, 50.0, 20.5)
    assert rects == []
    _image, rects = _paint_center(monkeypatch, 60.0, 50.0, 20.5)
    assert rects == []


def test_draw_center_line_pixel_row(monkeypatch):
    """End to end: the .5-center row is painted, neighbors are clean."""
    image, _rects = _paint_center(monkeypatch, 10.0, 100.0, 20.5)
    line = QColor("#ff0000")
    plain = QColor("#ffffff")
    assert image.pixelColor(30, 20).rgb() == line.rgb()
    assert image.pixelColor(30, 19).rgb() == plain.rgb()
    assert image.pixelColor(30, 21).rgb() == plain.rgb()
    assert image.pixelColor(30, 20 - 5).rgb() == plain.rgb()


def test_center_line_tokens_only():
    """The primitive takes its color as an argument: no ``QColor(`` built
    in the paint path, no theme branches, no stylesheets."""
    import inspect

    source = inspect.getsource(timeline_primitives.draw_center_line)
    assert "QColor(" not in source
    assert "is_dark" not in source
    assert "setStyleSheet" not in source
    params = inspect.signature(timeline_primitives.draw_center_line).parameters
    assert list(params) == ["painter", "x0", "x1", "center_y", "color"]
