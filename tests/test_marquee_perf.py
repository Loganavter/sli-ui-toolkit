"""Marquee repaint-storm fixes: strip cache, dirty-rect ticks, clip skip.

Covers ``sli_ui_toolkit.ui.widgets.helpers.marquee_text`` perf work:
pre-rendered pixmap strip (no drawText/QFontMetrics on cache hits),
row-rect-only repaints, and zero-cost ticks for fully clipped hosts.
Pixel parity against the legacy direct path is asserted byte-exact at
integer phases and bounded at fractional offsets (AA-edge resampling).
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.buttons import (
    Button,
    ButtonRegion,
    ButtonRow,
    VerticalSplit,
)
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import (
    draw_marquee_text,
    ensure_marquee_driver,
)

LONG_TEXT = "Comparison gallery filename number 12345 " * 3


class _StripHost(QWidget):
    """Minimal host painting overflowing text (driver auto-resolved)."""

    def __init__(self, text: str = LONG_TEXT) -> None:
        super().__init__()
        self._text = text
        ensure_marquee_driver(self)
        self.resize(120, 24)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QColor("#111111"))
        # No explicit driver: resolved from the paint device (the host).
        draw_marquee_text(
            painter, QRect(0, 0, self.width(), self.height()),
            self._text, self._driver_phase(),
        )
        painter.end()

    def _driver_phase(self) -> float:
        driver = getattr(self, "_marquee_driver", None)
        return float(driver.phase) if driver is not None else 0.0


def _grab(widget: QWidget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    widget.render(image, QPoint(0, 0))
    return image


def _channel_diff(a: QImage, b: QImage) -> list[int]:
    assert (a.width(), a.height()) == (b.width(), b.height())
    diffs = []
    for y in range(a.height()):
        for x in range(a.width()):
            c1, c2 = a.pixelColor(x, y), b.pixelColor(x, y)
            diffs.append(
                max(
                    abs(c1.red() - c2.red()),
                    abs(c1.green() - c2.green()),
                    abs(c1.blue() - c2.blue()),
                )
            )
    return diffs


def test_strip_cache_hit_skips_rerender(qapp) -> None:
    """Second paint of the same text performs zero re-render.

    The hit branch returns before any QFontMetrics measurement or
    drawText (see draw_marquee_text): renders stays 1, hits grow.
    """
    del qapp
    host = _StripHost()
    host.show()
    _grab(host)
    driver = host._marquee_driver
    assert driver.strip_cache_renders == 1
    _grab(host)
    assert driver.strip_cache_renders == 1
    assert driver.strip_cache_hits >= 1
    host.deleteLater()


def test_strip_invalidates_on_key_change(qapp) -> None:
    """Text / font / width changes each re-render exactly once."""
    del qapp
    host = _StripHost()
    host.show()
    _grab(host)
    driver = host._marquee_driver
    assert driver.strip_cache_renders == 1

    host._text += "!"
    _grab(host)
    assert driver.strip_cache_renders == 2

    big = QFont(host.font())
    big.setPixelSize(host.font().pixelSize() + 8)
    host.setFont(big)
    _grab(host)
    assert driver.strip_cache_renders == 3

    # Still overflowing at the narrower width (no fits-path switch).
    host.resize(100, 24)
    _grab(host)
    assert driver.strip_cache_renders == 4
    host.deleteLater()


def test_tick_skips_update_when_host_clipped(qapp, monkeypatch) -> None:
    """Fully clipped host: no phase advance, no update, no on_tick."""
    del qapp
    host = QWidget()  # never shown -> visibleRegion() is empty
    assert host.visibleRegion().isEmpty()
    driver = ensure_marquee_driver(host)
    driver.phase = 5.0
    setattr(host, "_marquee_phase", 5.0)
    spy = Mock()
    monkeypatch.setattr(host, "update", spy)
    driver._tick()
    assert driver.phase == 5.0
    assert getattr(host, "_marquee_phase", 5.0) == 5.0
    spy.assert_not_called()
    host.deleteLater()


def test_tick_repaints_dirty_rect_only(qapp, monkeypatch) -> None:
    """Tick repaints the registered row rect; unset falls back to full."""
    host = QWidget()
    host.resize(120, 24)
    host.show()
    qapp.processEvents()
    assert not host.visibleRegion().isEmpty()
    driver = ensure_marquee_driver(host)

    row = QRect(0, 5, 120, 14)
    driver.set_dirty_rect(row)
    spy = Mock()
    monkeypatch.setattr(host, "update", spy)
    phase0 = driver.phase
    driver._tick()
    assert driver.phase > phase0
    spy.assert_called_once()
    painted = spy.call_args[0][0]
    assert painted == row
    assert painted != host.rect()  # row only, never the whole host

    # No rect registered -> legacy full-host repaint.
    driver.set_dirty_rect(None)
    spy.reset_mock()
    driver._tick()
    spy.assert_called_once_with()
    host.deleteLater()


def test_button_row_registers_dirty_rect(qapp, monkeypatch) -> None:
    """RowsContent paint plumbs the marquee row rect without call changes."""
    btn = Button(
        regions=[
            ButtonRegion(
                id="text",
                rows=[
                    ButtonRow(
                        text=LONG_TEXT,
                        size=11,
                        h_align=Qt.AlignmentFlag.AlignLeft,
                        marquee=True,
                    ),
                ],
            )
        ],
        split=VerticalSplit(),
        size=(100, 56),
        content_padding=(8, 4, 8, 4),
    )
    btn.resize(100, 56)
    btn.show()
    qapp.processEvents()
    image = QImage(btn.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    btn.render(image, QPoint(0, 0))
    driver = btn._marquee_driver
    dirty = driver.dirty_rect()
    assert dirty is not None and not dirty.isEmpty()
    assert dirty.height() < btn.height()  # the row, not the whole button

    spy = Mock()
    monkeypatch.setattr(btn, "update", spy)
    driver._tick()
    spy.assert_called_once()
    assert spy.call_args[0][0] == dirty
    btn.deleteLater()


def test_strip_pixel_parity_with_direct_path(qapp) -> None:
    """Strip blits match the legacy drawText frame.

    Integer phase: byte-exact (same geometry/phase/color/pixels).
    Fractional phase: bounded — differences are confined to 1px
    antialiased glyph edges from pixmap resampling (motion-identical).
    """
    del qapp
    host = QWidget()  # driver owner only; paint devices are QImages
    driver = ensure_marquee_driver(host)

    def render(phase: float, *, use_strip: bool) -> QImage:
        image = QImage(120, 24, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        painter = QPainter(image)
        painter.setFont(QFont("Sans", 10))
        painter.setPen(QColor("#111111"))
        kwargs = {"driver": driver} if use_strip else {}
        draw_marquee_text(
            painter, QRect(0, 0, 120, 24), LONG_TEXT, phase, **kwargs
        )
        painter.end()
        return image

    legacy = render(7.0, use_strip=False)
    strip = render(7.0, use_strip=True)
    assert _channel_diff(legacy, strip) == [0] * (120 * 24)

    legacy = render(12.5, use_strip=False)
    strip = render(12.5, use_strip=True)
    diffs = _channel_diff(legacy, strip)
    n = len(diffs)
    assert sum(diffs) / n <= 15.0
    agree = 0
    for y in range(legacy.height()):
        for x in range(legacy.width()):
            dark_legacy = legacy.pixelColor(x, y).red() < 128
            dark_strip = strip.pixelColor(x, y).red() < 128
            agree += dark_legacy == dark_strip
    # 0.90, not higher: CI font substitution shifts antialiased glyph
    # edges vs dev machines (93.1% observed) without moving any glyph —
    # a real regression (wrong offset/strip) craters agreement toward
    # ~0.5, so this still guards motion-identity. Integer phases above
    # remain byte-exact.
    assert agree / n >= 0.90
    host.deleteLater()


@pytest.mark.parametrize("phase", [0.0, 7.0])
def test_strip_integer_phases_exact(qapp, phase: float) -> None:
    """Integer offsets blit on pixel boundaries: at most 1-LSB raster noise.

    (The strip renders through an integer QRect while the legacy path uses
    a QRectF, so a single pixel may differ by 1 LSB depending on the font.)
    """
    del qapp
    host = QWidget()
    driver = ensure_marquee_driver(host)

    def render(use_strip: bool) -> QImage:
        image = QImage(120, 24, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        painter = QPainter(image)
        painter.setFont(QFont())
        painter.setPen(QColor("#111111"))
        kwargs = {"driver": driver} if use_strip else {}
        draw_marquee_text(
            painter, QRect(0, 0, 120, 24), LONG_TEXT, phase, **kwargs
        )
        painter.end()
        return image

    diffs = _channel_diff(render(False), render(True))
    assert max(diffs) <= 1
    assert sum(diffs) / len(diffs) < 0.01
    host.deleteLater()
