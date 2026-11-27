"""ConsoleView paint path: the prepared-row cache must not change the pixels.

`ConsoleView` used to allocate a ``QFont`` per bold/italic row and call
``drawText`` per visual line on every paint. The cache that replaced it
(fixed emphasis variants + a prepared ``QStaticText`` per row) is only
acceptable while the rendered image stays identical, so the golden test here
renders the same content through both bodies and compares the bytes.
"""

from __future__ import annotations

import hashlib

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QImage, QPainter

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleLine, ConsoleView

WIDTH = 420
HEIGHT = 300

LINES = [
    ConsoleLine("frame 0042/0500 n=87 t=1.84s eta=1.9m"),
    ConsoleLine("PHASE 2/4: upscale (lanczos3, 8 workers)", QColor("#8ab4f8"), bold=True),
    ConsoleLine("WARNING tile 5,4 decode fallback: nv12 -> rgba8", QColor("#e0b050"), bold=True),
    ConsoleLine("italic note: cache hit for frame 0041 (tile 7,3) 0.3ms", None, False, True),
    ConsoleLine("ERROR worker 6 stalled 3.0s on barrier", QColor("#e05c5c"), bold=True),
    ConsoleLine(
        "a long wrapped row that has to be sliced into several visual lines "
        "so the wrap path is exercised as well as the short one",
    ),
] * 12


@pytest.fixture(scope="module", autouse=True)
def _palettes():
    ThemeManager.get_instance().register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    yield


def _make_view() -> ConsoleView:
    view = ConsoleView()
    view.resize(WIDTH, HEIGHT)
    view.append_console_lines(LINES)
    view._ensure_layout()
    return view


def _legacy_paint(view: ConsoleView) -> None:
    """The paint body from before the cache (per-row QFont + ``drawText``)."""

    def paint(painter: QPainter, visual_index: int, y: int, fm: QFontMetrics) -> None:
        visual = view._visual[visual_index]
        view._paint_selection(painter, visual, y, fm)
        line = view._lines[visual.source_index]
        color = line.color
        painter.setPen(QColor(color) if color is not None and color.isValid() else view._text_color)
        if not line.bold and not line.italic:
            font = view._font
        else:
            font = QFont(view._font)
            font.setBold(line.bold)
            font.setItalic(line.italic)
        painter.setFont(font)
        painter.drawText(QPointF(float(view._pad), float(y + fm.ascent())), visual.text)

    view._paint_visual_line = paint  # type: ignore[method-assign]


def _render(view: ConsoleView, dpr: float = 1.0) -> QImage:
    image = QImage(
        int(WIDTH * dpr), int(HEIGHT * dpr), QImage.Format.Format_ARGB32_Premultiplied
    )
    image.fill(QColor("#ffffff"))
    image.setDevicePixelRatio(dpr)
    painter = QPainter(image)
    painter.scale(dpr, dpr)
    view.render(painter, QPoint(0, 0), QRect(0, 0, WIDTH, HEIGHT))
    painter.end()
    return image


def _digest(image: QImage) -> str:
    return hashlib.sha256(bytes(image.bits())).hexdigest()


@pytest.mark.parametrize("dpr", [1.0, 2.0])
def test_cached_paint_is_pixel_identical_to_draw_text(qtbot, dpr):
    cached = _make_view()
    legacy = _make_view()
    qtbot.addWidget(cached)
    qtbot.addWidget(legacy)

    cached.set_scroll_value(40)
    legacy.set_scroll_value(40)
    cached.select_all()
    legacy.select_all()
    _legacy_paint(legacy)

    assert _digest(_render(cached, dpr)) == _digest(_render(legacy, dpr))


def test_cached_paint_is_stable_across_repeats(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    first = _digest(_render(view))
    assert view._static_lines, "a paint must populate the prepared-row cache"
    second = _digest(_render(view))
    assert first == second


def test_emphasis_fonts_are_cached_per_variant(qtbot):
    view = ConsoleView()
    qtbot.addWidget(view)
    plain = ConsoleLine("text")
    bold = ConsoleLine("text", bold=True)
    italic = ConsoleLine("text", italic=True)

    assert view._line_font(plain) is view._font
    assert view._line_font(bold) is view._line_font(bold)
    assert view._line_font(italic) is view._line_font(italic)
    assert view._line_font(bold) is not view._line_font(italic)
    assert view._line_font(bold).bold() is True
    assert view._line_font(italic).italic() is True
    assert view._line_font(bold) is not view._font


def test_cached_ascent_matches_the_font_metrics(qtbot):
    view = ConsoleView()
    qtbot.addWidget(view)
    for line in (ConsoleLine("text"), ConsoleLine("text", bold=True)):
        font, ascent = view._line_style(line)
        assert ascent == pytest.approx(QFontMetricsF(font).ascent())


def test_font_change_invalidates_the_row_caches(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    _render(view)
    assert view._font_variants and view._static_lines

    other = QFont("DejaVu Sans")
    other.setPixelSize(15)
    view.set_font(other)

    assert view._font_variants == {}
    assert view._static_lines == {}
    assert view._line_font(ConsoleLine("text")) is view._font
    assert view._line_font(ConsoleLine("text", bold=True)).pixelSize() == 15


def test_wrap_width_change_drops_the_prepared_rows(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    _render(view)
    assert view._static_lines

    # A hidden widget's resize event is queued until it is shown, so drive the
    # invalidation the way a repaint does: mark stale, then re-lay out.
    view.resize(WIDTH - 80, HEIGHT)
    view._mark_dirty()
    view._ensure_layout()

    assert view._static_lines == {}


def test_prepared_row_cache_is_bounded(qtbot):
    view = ConsoleView()
    view.resize(WIDTH, HEIGHT)
    qtbot.addWidget(view)
    view.append_console_lines(
        ConsoleLine(f"unique log row {index} with some payload text") for index in range(900)
    )
    for value in range(0, 4000, 25):
        view.set_scroll_value(value)
        _render(view)
        assert len(view._static_lines) <= 512


def test_row_cache_ignores_colour(qtbot):
    view = ConsoleView()
    view.resize(WIDTH, HEIGHT)
    qtbot.addWidget(view)
    view.append_console_lines(
        [
            ConsoleLine("same row text", QColor("#ff0000")),
            ConsoleLine("same row text", QColor("#00ff00"), bold=True),
        ]
    )
    _render(view)
    keys = [key for key in view._static_lines if key[0] == "same row text"]
    assert len(keys) == 2, "one per emphasis variant, not one per colour"
