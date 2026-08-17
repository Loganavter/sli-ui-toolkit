"""Context menu rows/menu scale with UiScale.

Regression: row text went through ui_font() (scale-resolved) but every other
dimension stayed fixed — ROW_HEIGHT/ICON_SIZE, paddings, check gutter,
trailing shortcut/arrow widths. At UI scale > 1.0 the menu width only grew
by the text delta (padding/icon/gutter stayed put), the fixed 32px row
height clipped the scaled text, and the section-title sizeHint
re-pinned its font to unscaled 11px, under-sizing the menu.

All row/menu dimensions are now derived through scaled_px().
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _build_menu(qtbot, *, factor: float):
    UiScale.get_instance().set_factor(factor)
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(640, 480)
    parent.show()
    menu = ContextMenu(
        parent,
        entries=(
            ContextMenuAction("rename", "Rename entry"),
            ContextMenuAction("del", "Delete entry", shortcut="Ctrl+D"),
        ),
    )
    qtbot.addWidget(menu)
    return menu


def test_row_draw_does_not_double_the_scale(qtbot, monkeypatch):
    """Row paint must NOT multiply the factor a second time.

    The row font is already scale-resolved (ui_font() set by the menu's
    _relayout_widths); the content layer used to paint through paint_font(),
    which re-multiplies the factor on top of the resolved size — at 150% the
    label painted ~2.25x and never fit the row width.
    """
    import sys

    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter

    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.ui.managers.ui_font import ui_font
    from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
    from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction

    uf_mod = sys.modules["sli_ui_toolkit.ui.managers.ui_font"]
    rebase_called = []

    def _bomb(*_args, **_kwargs):
        rebase_called.append(1)
        raise AssertionError("draw must not re-scale an already resolved font")

    monkeypatch.setattr(uf_mod.UiFont, "rebase", _bomb)

    try:
        UiScale.get_instance().set_factor(2.0)
        parent = QWidget()
        qtbot.addWidget(parent)
        menu = ContextMenu(
            parent,
            entries=(ContextMenuAction("rename", "Rename entry"),),
        )
        qtbot.addWidget(menu)
        row = menu._rows[0]
        # Mirror _relayout_widths: the row's font is scale-resolved.
        row.setFont(ui_font())

        image = QImage(400, 100, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        from sli_ui_toolkit.theme import ThemeManager

        layer = next(
            layer
            for layer in row._painter.layers
            if layer.__class__.__name__ == "_RowContentLayer"
        )
        ctx = DrawContext(
            widget=row,
            painter=painter,
            rect=QRectF(row.rect()),
            states=frozenset(),
            variant="default",
            corner_radius=6,
        )
        layer.draw(ctx, ThemeManager.get_instance())
        painter.end()
    finally:
        UiScale.get_instance().set_factor(1.0)

    assert not rebase_called, (
        "row paint re-scaled the already scale-resolved font (paint_font/rebase)"
    )
    menu_1x = _build_menu(qtbot, factor=1.0)
    rows_1x = [row.sizeHint() for row in menu_1x._rows]
    menu_2x = _build_menu(qtbot, factor=2.0)
    rows_2x = [row.sizeHint() for row in menu_2x._rows]
    assert len(rows_1x) == 2 and len(rows_2x) == 2

    for hint_1x, hint_2x in zip(rows_1x, rows_2x):
        assert hint_2x.height() == 2.0 * hint_1x.height(), (
            f"row height did not scale: {hint_1x.height()} -> {hint_2x.height()}"
        )
        assert hint_2x.width() > hint_1x.width(), (
            f"row width did not grow with scale: {hint_1x.width()} -> {hint_2x.width()}"
        )

    # The fixed chrome (gutter + padding + trailing) must grow too, not just
    # the text: a shortcut row at 2x must be wider than 2x the text-only delta.
    row_1x = rows_1x[1]
    row_2x = rows_2x[1]
    from PySide6.QtGui import QFontMetrics

    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    text_1x = QFontMetrics(ui_font()).horizontalAdvance("Delete entry")
    text_2x = QFontMetrics(ui_font()).horizontalAdvance("Delete entry")
    chrome_delta = (row_2x.width() - text_2x) - (row_1x.width() - text_1x)
    assert chrome_delta > 0, (
        f"gutter/padding/trailing chrome did not scale: {chrome_delta}"
    )
