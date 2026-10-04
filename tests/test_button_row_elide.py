"""ButtonRow elide: overflowing static rows truncate with an ellipsis."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter

from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow


class _Ctx:
    def __init__(self, widget, painter):
        self.widget = widget
        self.painter = painter


def _paint_row(row: ButtonRow, width: int = 120) -> QImage:
    """Render one row through the real resolved path used by paints."""
    from sli_ui_toolkit.ui.managers.theme_manager import ThemeManager
    from sli_ui_toolkit.ui.widgets.buttons.content import RowsContent
    from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

    host = Button(text="x")
    host.resize(width, 24)
    host.show()
    image = QImage(width, 24, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    style = read_widget_style(host)
    tm = ThemeManager.get_instance()
    resolved = RowsContent._resolve_row(
        row, _Ctx(host, painter), style, tm,
        padded_x=0, padded_w=width, full_x=0, full_w=width, y=0, height=24,
    )
    assert not resolved.marquee_active
    RowsContent._draw_resolved(painter, resolved, 0.0)
    painter.end()
    host.deleteLater()
    return image


def test_elide_flag_defaults_off() -> None:
    row = ButtonRow(text="a.png", size=12)
    assert row.elide is False and row.marquee is False


def test_elided_text_ends_with_ellipsis() -> None:
    fm = QFontMetrics(QFont())
    long_text = "very_long_filename_that_overflows_the_row_0123456789.png"
    elided = fm.elidedText(long_text, Qt.TextElideMode.ElideRight, 120)
    assert elided.endswith("…")
    assert len(elided) < len(long_text)
    assert fm.elidedText("a.png", Qt.TextElideMode.ElideRight, 120) == "a.png"


def test_elide_renders_ellipsis_pixels(qapp) -> None:
    """Elided rows paint the … glyph; plain rows clip without it."""
    del qapp
    long_text = "very_long_filename_that_overflows_the_row_0123456789.png"
    elided_img = _paint_row(ButtonRow(text=long_text, size=12, marquee=False, elide=True))
    clipped_img = _paint_row(ButtonRow(text=long_text, size=12, marquee=False, elide=False))
    assert elided_img != clipped_img
