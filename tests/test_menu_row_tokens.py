"""ContextMenu rows paint with the menu family's own keys.

Before the migration the row label (and the section title) read `dialog.text`
— the menu strip had no family of its own — and a disabled row faked its
disabled state by fading that borrowed colour through layer opacity. `menu.text`
and `menu.text.disabled` now own both, and the hover/current plate is
`menu.background.hover` — the palette ships it at the exact value the rows used
to borrow from `list_item.background.hover`, so a host that restyles menus no
longer repaints list rows (or the other way round).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import ContextMenuAction
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import ContextMenuRow

#: Unmistakable inks: `dialog.text` is the token the rows used to borrow, so a
#: blue pixel would mean the migration regressed. The two hover plates are
#: sentinels too, so "the row paints *this* plate" is decidable by pixel.
_INK_LIGHT = {
    "dialog.text": QColor("#0000ff"),
    "menu.text": QColor("#00ff00"),
    "menu.text.disabled": QColor("#ff0000"),
    "menu.background.hover": QColor("#00ffff"),
    "list_item.background.hover": QColor("#ffff00"),
}
_INK_DARK = {
    "dialog.text": QColor("#0000ff"),
    "menu.text": QColor("#ffff00"),
    "menu.text.disabled": QColor("#ff00ff"),
    "menu.background.hover": QColor("#00ffff"),
    "list_item.background.hover": QColor("#ffff00"),
}


def _theme(qapp, theme: str) -> ThemeManager:
    manager = ThemeManager.get_instance()
    light = dict(FLUENT_LIGHT)
    light.update(_INK_LIGHT)
    dark = dict(FLUENT_DARK)
    dark.update(_INK_DARK)
    manager.register_palettes(light, dark)
    manager.set_theme(theme, qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]
    return manager


def _row(*, enabled: bool = True, text: str = "MMMM") -> ContextMenuRow:
    action = ContextMenuAction("probe", text, enabled=enabled)
    row = ContextMenuRow(action, check_gutter=12, parent=None)
    row.resize(row.sizeHint())
    return row


def _render(row: ContextMenuRow, background: str = "#000000") -> QImage:
    image = QImage(row.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(background))
    painter = QPainter(image)
    try:
        # `DrawChildren` alone drops `DrawWindowBackground`, so `render()` does
        # not pre-fill the widget's palette Window role: that colour follows the
        # app palette (not the row plate) and made the sample order-dependent.
        row.render(painter, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
    finally:
        painter.end()
    return image


def _pixels_matching(image: QImage, colour: QColor, tolerance: int = 60) -> int:
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - colour.red()) <= tolerance
                and abs(pixel.green() - colour.green()) <= tolerance
                and abs(pixel.blue() - colour.blue()) <= tolerance
            ):
                count += 1
    return count


@pytest.mark.parametrize(
    ("theme", "ink", "disabled_ink"),
    [
        ("light", QColor("#00ff00"), QColor("#ff0000")),
        ("dark", QColor("#ffff00"), QColor("#ff00ff")),
    ],
)
def test_row_label_reads_the_menu_family_ink(qapp, theme, ink, disabled_ink):
    _theme(qapp, theme)

    enabled = _render(_row())
    assert _pixels_matching(enabled, ink) > 0, f"{theme}: enabled row ink is `menu.text`"
    assert _pixels_matching(enabled, QColor("#0000ff")) == 0  # `dialog.text` no longer paints the row

    disabled = _render(_row(enabled=False))
    assert _pixels_matching(disabled, disabled_ink) > 0, (
        f"{theme}: disabled row ink is `menu.text.disabled`, not a faded borrowed token"
    )
    assert _pixels_matching(disabled, ink) == 0


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_row_hover_plate_is_the_menu_familys_own(qapp, qtbot, theme):
    """`menu.background.hover` owns the hover/current plate, not the list plate."""
    manager = _theme(qapp, theme)

    # A real hover: move the cursor onto a shown row. `Button.moveEvent` drops
    # HOVERED when the cursor is elsewhere, and `render()` sends a move event —
    # so a state set behind the cursor's back is cleared before it paints.
    host = QWidget()  # keeps the row's C++ object alive (qtbot tracks it weakly)
    qtbot.addWidget(host)
    host.resize(240, 160)
    host.show()
    qapp.processEvents()
    row = ContextMenuRow(
        ContextMenuAction("probe", "MMMM"), check_gutter=12, parent=host
    )
    row.resize(row.sizeHint())
    row.move(16, 16)
    row.show()
    qapp.processEvents()
    QTest.mouseMove(row, row.rect().center())
    qapp.processEvents()
    assert row._hovered, "the cursor move must light the row"

    plate = manager.get_color("menu.background.hover")
    borrowed = manager.get_color("list_item.background.hover")
    assert plate.name() != borrowed.name(), "the sentinels must differ to be decidable"

    image = row.grab().toImage()
    sample = image.pixelColor(row.width() - 4, row.height() // 2)
    assert sample.name() == plate.name(), (
        f"{theme}: the hover plate is the menu family's own key"
    )
    assert sample.name() != borrowed.name(), (
        f"{theme}: the row no longer borrows the list family's hover plate"
    )
