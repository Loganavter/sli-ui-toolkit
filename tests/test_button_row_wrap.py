"""ButtonRow word wrap: long rows break across lines and grow the card.

Mirrors the ``ButtonRow`` elide/marquee tests: paint through the real resolved
path (``RowsContent._resolve_row`` / ``_draw_resolved``) so the assertions
exercise the production painter, not a reimplementation.
"""

from __future__ import annotations

from PySide6.QtGui import QImage

from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRegion, ButtonRow
from sli_ui_toolkit.ui.widgets.buttons.content import RowsContent, wrapped_line_count

_LONG = (
    "The quick brown fox jumps over the lazy dog and keeps running far away "
    "and further still through the winding valley."
)


class _Ctx:
    def __init__(self, widget, painter):
        self.widget = widget
        self.painter = painter


def test_wrap_flag_defaults_off() -> None:
    row = ButtonRow(text="a long description", size=12)
    assert row.wrap is False


def test_wrapped_line_count_splits_at_narrow_width() -> None:
    font = ui_font(pixel_size=12)
    assert wrapped_line_count(font, _LONG, 80) >= 2
    # Wide enough for the whole sentence: one line.
    assert wrapped_line_count(font, _LONG, 10_000) == 1
    # Empty text is a single (empty) line regardless of width.
    assert wrapped_line_count(font, "", 80) == 1


def test_wrap_false_is_single_line_parity() -> None:
    """``wrap=False`` keeps the historic one-line metrics exactly."""
    rows = [ButtonRow(text=_LONG, size=12, wrap=False)]
    content = RowsContent(rows=rows)
    assert content.has_wrap is False
    single = ui_font(pixel_size=12)
    from PySide6.QtGui import QFontMetrics

    assert content.measure_height(80) == QFontMetrics(single).lineSpacing()
    assert content.measure_height(10_000) == QFontMetrics(single).lineSpacing()


def test_wrapped_row_reports_more_height_than_single_line() -> None:
    single = RowsContent(rows=[ButtonRow(text=_LONG, size=12, wrap=False)])
    wrapped = RowsContent(rows=[ButtonRow(text=_LONG, size=12, wrap=True)])
    assert wrapped.has_wrap is True
    assert wrapped.measure_height(80) > single.measure_height(80)


def _ink_bands(row: ButtonRow, width: int, height: int) -> int:
    """Contiguous vertical bands of text pixels for one row at ``width``.

    Renders the row over the real painter twice — once with the text and once
    blank — and counts contiguous y-ranges where the two differ, so the
    background fill cancels out and only glyphs remain.
    """
    from sli_ui_toolkit.ui.managers.theme_manager import ThemeManager
    from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

    def render(text: str) -> QImage:
        host = Button(text="x")
        host.resize(width, height)
        host.show()
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(0)
        from PySide6.QtGui import QPainter

        p = QPainter(image)
        style = read_widget_style(host)
        tm = ThemeManager.get_instance()
        paint_row = ButtonRow(
            text=text,
            size=row.size,
            weight=row.weight,
            h_align=row.h_align,
            wrap=row.wrap,
        )
        resolved = RowsContent._resolve_row(
            paint_row,
            _Ctx(host, p),
            style,
            tm,
            padded_x=0,
            padded_w=width,
            full_x=0,
            full_w=width,
            y=0,
            height=height,
        )
        RowsContent._draw_resolved(p, resolved, 0.0)
        p.end()
        host.deleteLater()
        return image

    with_text = render(row.text)
    blank = render("")
    bands = 0
    in_band = False
    for y in range(height):
        differs = any(
            with_text.pixel(x, y) != blank.pixel(x, y) for x in range(width)
        )
        if differs and not in_band:
            bands += 1
            in_band = True
        elif not differs:
            in_band = False
    return bands


def test_wrapped_row_paints_multiple_lines(qapp) -> None:
    """A wrapped row puts ink on ≥2 separate line bands; plain clips to one."""
    del qapp
    wrapped_bands = _ink_bands(ButtonRow(text=_LONG, size=12, wrap=True), 90, 120)
    plain_bands = _ink_bands(ButtonRow(text=_LONG, size=12, wrap=False), 90, 120)
    assert wrapped_bands >= 2
    assert plain_bands == 1


def test_button_height_for_width_grows_for_wrapped_region(qapp) -> None:
    """The Button reports (and can grow to) the wrapped height."""
    del qapp
    card = Button(
        regions=[ButtonRegion(id="text", rows=[ButtonRow(text=_LONG, size=12, wrap=True)])],
        size=(0, 76),
    )
    assert card.hasHeightForWidth() is True
    assert card.heightForWidth(90) > card.heightForWidth(10_000)
    # The fixed design height is relaxed into a floor so a layout can stretch it.
    assert card.minimumHeight() == 76
    assert card.maximumHeight() > 76
    card.deleteLater()


def test_button_single_line_card_is_unchanged(qapp) -> None:
    """A non-wrapping card keeps the historic fixed-size behaviour."""
    del qapp
    card = Button(
        regions=[ButtonRegion(id="text", rows=[ButtonRow(text="Short", size=12)])],
        size=(0, 76),
    )
    assert card.hasHeightForWidth() is False
    assert card.minimumHeight() == 76
    assert card.maximumHeight() == 76
    card.deleteLater()
