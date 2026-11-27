"""ConsoleView paints through the text engine, and the pixels did not move.

The console used to keep its own wrap table and draw every visual row with
``painter.drawText`` plus a per-line ``QFont``. It now holds one engine
``QTextLayout`` per source line (``build_text_layout``) and paints the body
with the engine's ``paint_layout``. This file pins the two things that
re-home must not change: the rendered image for the same content, and the
point <-> character mapping selection and copying ride on.
"""

from __future__ import annotations

import hashlib

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleLine, ConsoleView
from sli_ui_toolkit.ui.widgets.text.engine.layout.paint import paint_layout

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
] * 8


@pytest.fixture(scope="module", autouse=True)
def _palettes():
    ThemeManager.get_instance().register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    yield


def _make_view(*, height: int = HEIGHT, width: int = WIDTH) -> ConsoleView:
    view = ConsoleView()
    view.resize(width, height)
    view.append_console_lines(LINES)
    view._ensure_layout()
    return view


def _image(width: int = WIDTH, height: int = HEIGHT, dpr: float = 1.0) -> QImage:
    image = QImage(
        int(width * dpr), int(height * dpr), QImage.Format.Format_ARGB32_Premultiplied
    )
    image.fill(QColor("#ffffff"))
    image.setDevicePixelRatio(dpr)
    return image


def _digest(image: QImage) -> str:
    return hashlib.sha256(bytes(image.bits())).hexdigest()


def _paint_body(view: ConsoleView, dpr: float = 1.0) -> QImage:
    """The console's glyphs through the engine, on a known background."""
    image = _image(dpr=dpr)
    painter = QPainter(image)
    painter.scale(dpr, dpr)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(QRect(0, 0, WIDTH, HEIGHT), view._bg_color)
    start, end = view._selection_globals()
    paint_layout(
        painter,
        view._visible_body(0, HEIGHT),
        selection_start=start,
        selection_end=end,
        theme=view.theme_manager,
        selection_color=view._selection_wash(),
    )
    painter.end()
    return image


def _paint_draw_text_reference(view: ConsoleView, dpr: float = 1.0) -> QImage:
    """The console's pre-re-home paint rule, over the same rows."""
    image = _image(dpr=dpr)
    painter = QPainter(image)
    painter.scale(dpr, dpr)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(QRect(0, 0, WIDTH, HEIGHT), view._bg_color)
    fm = QFontMetrics(view._font)
    for row, visual in enumerate(view.visual_lines()):
        line = view.lines()[visual.source_index]
        colour = line.color if line.color is not None and line.color.isValid() else view._text_color
        painter.setPen(QColor(colour))
        font = view._font if not (line.bold or line.italic) else QFont(view._font)
        if line.bold or line.italic:
            font.setBold(line.bold)
            font.setItalic(line.italic)
        painter.setFont(font)
        painter.drawText(
            QPointF(float(view._pad), float(view._pad + row * view._row_height + fm.ascent())),
            visual.text,
        )
    painter.end()
    return image


@pytest.mark.parametrize("dpr", [1.0, 2.0])
def test_engine_paint_is_pixel_identical_to_draw_text(qtbot, dpr):
    view = _make_view()
    qtbot.addWidget(view)

    engine = _paint_body(view, dpr)
    reference = _paint_draw_text_reference(view, dpr)

    assert _digest(engine) == _digest(reference)


def test_widget_paint_is_stable_across_repeats(qtbot):
    view = _make_view()
    qtbot.addWidget(view)

    def render() -> str:
        image = _image()
        painter = QPainter(image)
        view.render(painter, QPoint(0, 0), QRect(0, 0, WIDTH, HEIGHT))
        painter.end()
        return _digest(image)

    first = render()
    assert render() == first


def test_selection_paints_over_the_body(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    before = _digest(_paint_body(view))
    view._sel_anchor = (0, 0)
    view._sel_cursor = (2, 10)
    start, end = view._selection_globals()
    assert start is not None and end is not None and end > start
    assert _digest(_paint_body(view)) != before


def test_line_layouts_are_reused_and_keyed_by_line_data(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    plain = ConsoleLine("same text")
    red = ConsoleLine("same text", QColor("#ff0000"))
    bold = ConsoleLine("same text", bold=True)

    first = view._line_layout(plain, 300)
    assert view._line_layout(plain, 300) is first
    assert view._line_layout(red, 300) is not first, "the line's ink is part of its layout"
    assert view._line_layout(bold, 300) is not first, "emphasis is part of its layout"


def test_font_change_drops_the_line_layouts(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    assert view._row_cache

    other = QFont("DejaVu Sans")
    other.setPixelSize(15)
    view.set_font(other)

    # The layouts are re-derived from the new face, not kept from the old one.
    assert all(
        layout.font().pixelSize() == 15
        for layout, _rows, _ascent in view._row_cache.values()
    )
    assert view.line_index_at(view._pad + view._row_height // 2) == 0


def test_wrap_width_change_relays_out(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    before = [visual.text for visual in view.visual_lines()]

    view.resize(WIDTH - 120, HEIGHT)
    view._mark_dirty()
    view._ensure_layout()

    after = [visual.text for visual in view.visual_lines()]
    assert after != before, "a narrower console must re-wrap"
    assert "".join(after) == "".join(before), "no characters lost in the re-wrap"


def test_layout_cache_is_bounded(qtbot):
    view = ConsoleView()
    view.resize(WIDTH, HEIGHT)
    qtbot.addWidget(view)
    view.append_console_lines(
        ConsoleLine(f"unique log row {index} with some payload text") for index in range(6000)
    )
    view._ensure_layout()

    assert len(view._row_cache) <= 4096


def test_point_maps_through_the_layout(qtbot):
    view = ConsoleView()
    view.resize(300, 160)
    qtbot.addWidget(view)
    view.append_console_lines([ConsoleLine(f"line-{index} abcdefghijklmnop") for index in range(20)])
    view._ensure_layout()

    for row in (0, 1, 5, 12):
        y = view._pad + row * view._row_height + 1
        assert view._point_at(view._pad, y) == (row, 0)
        assert view._point_at(view._pad + 3, y)[0] == row
    # past the last glyph of the first row: end of that line
    assert view._point_at(WIDTH, view._pad + 1) == (0, len("line-0 abcdefghijklmnop"))
    # above and below the body clamp to its first/last row
    assert view._point_at(view._pad, -40)[0] == 0
    assert view._point_at(view._pad, 4000)[0] == 19


def test_drag_selection_across_rows_copies_the_span(qtbot):
    view = ConsoleView()
    view.resize(300, 160)
    qtbot.addWidget(view)
    view.append_console_lines([ConsoleLine("alpha"), ConsoleLine("beta"), ConsoleLine("gamma")])
    view._ensure_layout()

    view._sel_anchor = view._point_at(view._pad, view._pad + 1)
    view._sel_cursor = view._point_at(view._pad + 2, view._pad + 2 * view._row_height + 1)

    assert view._sel_cursor == (2, 0)
    assert view.selected_text() == "alpha\nbeta\n"


def test_mousedown_past_the_text_still_starts_a_selection(qtbot):
    view = ConsoleView()
    view.resize(300, 160)
    qtbot.addWidget(view)
    view.append_console_lines([ConsoleLine("one"), ConsoleLine("two")])
    view._ensure_layout()

    point = view._point_at(WIDTH - 2, view._pad + 1)
    assert point is not None
    assert point[0] == 0
    assert point[1] == len("one")


def test_selected_text_matches_select_all(qtbot):
    view = _make_view()
    qtbot.addWidget(view)
    view.select_all()
    assert view.selected_text() == "\n".join(line.text for line in LINES)
    assert view.text() == "\n".join(line.text for line in LINES)
