"""A clipped scroll edge fades the CONTENT out by alpha, not with a coloured strip.

The owner's correction (2026-11-22): "the fade must be by alpha". A gradient of the surface colour painted over the
content only looks right when that colour is exactly what sits behind it; on a pane whose plate differs by a few levels it
shows as a band. The fade is therefore a `QGraphicsEffect` on the content: the content's own alpha is multiplied by a ramp,
so the text fades into whatever the host paints behind it and there is no colour to guess.

Assertions: the sides follow the scroll position, the effect exists only while enabled, and the pixels agree - a glyph in
the bottom band is measurably lighter with the fade on than with it off.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea


def _area(app, rows: int = 40, row_height: int = 20):
    host = QWidget()
    host.resize(320, 220)
    host.setAutoFillBackground(True)
    palette = host.palette()
    palette.setColor(palette.ColorRole.Window, QColor("#ff00ff"))
    host.setPalette(palette)

    area = OverlayScrollArea(host)
    area.setGeometry(10, 10, 300, 200)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setSpacing(0)
    layout.setContentsMargins(0, 0, 0, 0)
    for _ in range(rows):
        label = QLabel("HHHH HHHH HHHH")
        label.setStyleSheet("color: #000000; background: transparent;")
        layout.addWidget(label)
    content.setMinimumHeight(rows * row_height)
    area.setWidget(content)
    host.show()
    for _ in range(8):
        app.processEvents()
    return host, area


def _darkest_glyph(host, band: int = 22) -> int:
    image = host.grab().toImage()
    bottom = image.height() - 12
    darkest = 255
    for y in range(bottom - band, bottom):
        for x in range(20, 280):
            darkest = min(darkest, QColor(image.pixelColor(x, y)).lightness())
    return darkest


def test_the_continuing_side_is_faded(qapp):
    _host, area = _area(qapp)
    assert area.edge_fade_sides() == (False, True), "the content continues below, nothing above"

    bar = area.verticalScrollBar()
    bar.setValue(bar.maximum())
    for _ in range(4):
        qapp.processEvents()
    assert area.edge_fade_sides() == (True, False)


def test_content_that_fits_has_no_fade(qapp):
    _host, area = _area(qapp, rows=2)
    assert area.edge_fade_sides() == (False, False)


def test_the_fade_is_an_overlay_and_is_opt_in(qapp):
    """An overlay, not a graphics effect: an effect renders the WHOLE widget into a pixmap per paint, which is seconds per
    frame on a render log (that froze the GUI thread, py-spy: setPlainText -> _wrap_line)."""
    _host, area = _area(qapp)
    assert area.edge_fade_enabled() is False
    assert area._edge_fade is None

    area.set_edge_fade_enabled(True)
    assert area._edge_fade is not None
    assert area._edge_fade.parent() is area
    assert area.viewport().graphicsEffect() is None, "no widget effect - it must stay a cheap overlay"

    area.set_edge_fade_enabled(False)
    assert area._edge_fade is None


def test_the_fade_works_by_alpha(qapp):
    """The decisive one: with the fade on, a glyph in the bottom band is visibly lighter (blended into the host colour)."""
    host, area = _area(qapp)
    without = _darkest_glyph(host)

    area.set_edge_fade_enabled(True)
    for _ in range(8):
        qapp.processEvents()
    with_fade = _darkest_glyph(host)

    assert with_fade > without + 10, (
        f"the fade did not modulate the content's alpha: darkest glyph {without} -> {with_fade}")


def test_the_fade_follows_the_scroll_position(qapp):
    """The bands must move with the scroll - the failure the owner reported was a ramp pinned to the first frame."""
    host, area = _area(qapp)
    area.set_edge_fade_enabled(True)
    for _ in range(8):
        qapp.processEvents()

    def bands() -> tuple[int, int]:
        image = host.grab().toImage()
        height = image.height()

        def darkest(y0: int, y1: int) -> int:
            return min(QColor(image.pixelColor(x, y)).lightness()
                       for y in range(y0, y1) for x in range(20, 280))

        return darkest(20, 40), darkest(height - 30, height - 12)

    top_band, bottom_band = bands()
    assert bottom_band > top_band, "at the top only the bottom edge may be faded"

    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
    for _ in range(8):
        qapp.processEvents()
    top_band, bottom_band = bands()
    assert top_band > bottom_band, "at the end only the top edge may be faded"
