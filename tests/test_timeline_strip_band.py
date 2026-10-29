"""StripBand plumbing — the GPU filmstrip band, proven without a GPU or window.

What is testable offscreen (and what this module pins):

* the view store: ``set_view`` is synchronous, one ``update()`` per call, and
  the same view is idempotent (no settle gate exists to wait for);
* renderer/release injection: Qt's callbacks reach the host callbacks, and a
  missing pair is a silent no-op rather than a crash;
* placement: ``place``/``band_rect`` follow the parent's band area and the
  widget's geometry, without showing or re-showing anything;
* the device ratio is read from the widget and passed through unrounded;
* the module owns no timer and no readback (source-level assertion);
* the timeline hook: ``enable_strip_band`` creates/places/syncs the child and
  the paint path stops drawing tiles while the band is visible.

The QRhi path itself (``initialize``/``render`` against a real ``QRhi``) needs
a mapped window with an RHI backend — not available in the cell, so it is not
asserted here.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    render as timeline_render,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.widgets import StripBand, TimelineWidget


class _CountingBand(StripBand):
    """Counts ``update()`` calls so "exactly one per view change" is visible."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.update_calls = 0

    def update(self, *args) -> None:
        self.update_calls += 1
        super().update(*args)


class _FractionalDprBand(StripBand):
    """A fractional ratio the offscreen platform never reports (150 % screen).

    The module must pass the live ratio through *unrounded*: rounding collapses
    125 %/150 % to 1 and the host renders at a quarter/third of the pixels it
    should. The double overrides Qt's accessor instead of rewriting the
    module's ratio source — ``tests/test_dpr_contract.py`` (``ratio-hardcoded``)
    exists to keep production code reading the device.
    """

    def devicePixelRatioF(self) -> float:
        return 1.5


# -- view plumbing ---------------------------------------------------------


def test_set_view_stores_and_updates_once_per_call(qtbot):
    band = _CountingBand()
    qtbot.addWidget(band)
    band.update_calls = 0

    band.set_view(120, 1.5)
    assert band.view() == (120, 1.5)
    assert band.update_calls == 1

    band.set_view(300, 2.0)
    assert band.view() == (300, 2.0)
    assert band.update_calls == 2


def test_same_view_is_idempotent(qtbot):
    band = _CountingBand()
    qtbot.addWidget(band)
    band.set_view(64, 1.25)
    band.update_calls = 0

    for _ in range(5):
        band.set_view(64, 1.25)

    # No extra work beyond the single update per call (no gate, no timer).
    assert band.view() == (64, 1.25)
    assert band.update_calls == 5


def test_view_coerces_to_int_scroll_and_float_zoom(qtbot):
    band = StripBand()
    qtbot.addWidget(band)
    band.set_view(10, 2)
    scroll_x, zoom = band.view()
    assert scroll_x == 10 and isinstance(scroll_x, int)
    assert zoom == 2.0 and isinstance(zoom, float)


# -- renderer injection ----------------------------------------------------


def test_renderer_and_release_are_injected(qtbot):
    band = StripBand()
    qtbot.addWidget(band)
    calls: list = []

    band.set_renderer(
        render=lambda command_buffer, b: calls.append((command_buffer, b)),
        release=lambda: calls.append("release"),
    )
    assert band.renderer() is not None

    band.render(None)
    assert calls == [(None, band)]

    band.releaseResources()
    assert calls[-1] == "release"
    assert len(calls) == 2


def test_missing_callbacks_are_silent(qtbot):
    band = StripBand()
    qtbot.addWidget(band)

    # Never injected: both Qt callbacks must be no-ops, not AttributeError.
    band.render(None)
    band.releaseResources()

    calls: list = []
    band.set_renderer(render=lambda cb, b: calls.append(b))
    band.releaseResources()  # release was not given -> nothing to call
    assert calls == []

    band.set_renderer()  # clears the pair
    band.render(None)
    assert calls == []


# -- placement -------------------------------------------------------------


def test_place_follows_the_parent_band_area(qtbot):
    host = QWidget()
    host.resize(640, 360)
    qtbot.addWidget(host)
    band = StripBand(host)
    qtbot.addWidget(band)
    assert band.band_rect().isEmpty()

    area = QRect(180, 0, 460, 72)  # right of the gutter, strip row only
    band.place(area)
    assert band.band_rect() == area
    assert band.geometry() == area
    assert band.parent() is host
    assert host.rect().contains(area)
    # Placement never shows the band; the host decides when it is on screen.
    assert not band.isVisible()

    band.place(QRectF(180, 0, 400, 72))  # QRectF accepted, stored as QRect
    assert band.band_rect() == QRect(180, 0, 400, 72)
    assert band.geometry().width() == 400

    band.place(area)
    assert band.band_rect() == area


def test_place_unchanged_rect_does_not_renavigate(qtbot):
    host = QWidget()
    host.resize(640, 360)
    qtbot.addWidget(host)
    band = _CountingBand(host)
    qtbot.addWidget(band)
    area = QRect(180, 0, 460, 72)
    band.place(area)
    band.update_calls = 0
    band.setGeometry(area)  # keep geometry honest if Qt moved it
    band.place(area)
    assert band.update_calls == 0
    assert band.band_rect() == area


# -- device ratio ----------------------------------------------------------


def test_device_ratio_is_read_from_the_widget(qtbot):
    band = StripBand()
    qtbot.addWidget(band)
    band.set_band_rect(QRect(0, 0, 200, 50))

    ratio = band.device_pixel_ratio()
    assert isinstance(ratio, float)
    # Live read, never a constant: same value Qt reports for this widget.
    assert ratio == band.devicePixelRatioF()

    size = band.device_pixel_size()
    assert size.width() == 200 * ratio
    assert size.height() == 50 * ratio


def test_device_ratio_is_not_rounded(qtbot):
    band = _FractionalDprBand()
    qtbot.addWidget(band)
    band.set_band_rect(QRect(0, 0, 200, 50))

    assert band.device_pixel_ratio() == pytest.approx(1.5)
    size = band.device_pixel_size()
    # Unrounded: 200 * 1.5 stays 300 device px (int(ratio) would give 200).
    assert size.width() == pytest.approx(300.0)
    assert size.height() == pytest.approx(75.0)


# -- no timer, no readback -------------------------------------------------


def test_module_owns_no_timer_or_readback():
    source = Path(inspect.getsourcefile(StripBand)).read_text(encoding="utf-8")
    for forbidden in (
        "QTimer",
        "SettleGate",
        "singleShot",
        "QImage",
        "grabFramebuffer",
    ):
        assert forbidden not in source, f"strip_band.py must not use {forbidden}"


# -- timeline wiring -------------------------------------------------------


def test_enable_and_disable_strip_band_on_timeline(qtbot):
    timeline = TimelineWidget()
    qtbot.addWidget(timeline)
    timeline.resize(640, 360)

    assert timeline.strip_band() is None
    assert timeline.strip_band_active() is False

    band = timeline.enable_strip_band(render=lambda cb, b: None)
    assert isinstance(band, StripBand)
    assert band.parent() is timeline
    assert timeline.strip_band() is band
    assert timeline.strip_band_active() == band.isVisible()

    area = timeline.strip_band_rect()
    assert area.left() == timeline.LEFT_GUTTER
    assert area.top() == 0
    assert area.height() == timeline.STRIP_HEIGHT
    assert band.band_rect() == area
    assert band.geometry() == area
    scroll_x, zoom = band.view()
    assert scroll_x == timeline_viewport.strip_band_view(timeline)[0]
    assert zoom == pytest.approx(timeline_viewport.strip_band_view(timeline)[1])

    # No renderer -> the QPainter thumbnail path is the fail-closed fallback.
    band.set_renderer(None, None)
    assert timeline.strip_band_active() is False

    timeline.disable_strip_band()
    assert timeline.strip_band() is None
    assert timeline.strip_band_active() is False
    timeline.disable_strip_band()  # idempotent


def test_strip_band_rect_keeps_the_footer_clear(qtbot):
    timeline = TimelineWidget()
    qtbot.addWidget(timeline)
    timeline.resize(640, 360)

    area = timeline.strip_band_rect()
    footer_top = timeline.height() - timeline_viewport.footer_height(timeline)
    assert area.bottom() < footer_top
    assert area.right() <= timeline.width()


def test_paint_skips_tiles_while_the_band_covers_the_strip(qtbot, monkeypatch):
    timeline = TimelineWidget()
    qtbot.addWidget(timeline)
    layout_calls: list = []
    monkeypatch.setattr(
        timeline_viewport,
        "strip_block_layout",
        lambda *args, **kwargs: layout_calls.append(args) or [],
    )

    pixmap = QPixmap(64, 64)
    painter = QPainter(pixmap)
    try:
        timeline_render.draw_thumbnail_strip(
            timeline,
            painter,
            canvas_bg=QColor("black"),
            content_start_x=0.0,
            strip_top=0.0,
            width=64,
            start_x=0.0,
            end_x=64.0,
            logical_width=64.0,
            slot_width=10.0,
            draw_tiles=False,
        )
    finally:
        painter.end()
    assert layout_calls == []

    painter = QPainter(pixmap)
    try:
        timeline_render.draw_thumbnail_strip(
            timeline,
            painter,
            canvas_bg=QColor("black"),
            content_start_x=0.0,
            strip_top=0.0,
            width=64,
            start_x=0.0,
            end_x=64.0,
            logical_width=64.0,
            slot_width=10.0,
        )
    finally:
        painter.end()
    assert layout_calls != []
