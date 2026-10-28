"""A LIVE UiScale change re-derives the row pitch and the Button's content sections.

Owner report 2026-10-19 (Settings → OK): after the interface scale grew, a
context-menu / flyout looked cramped (rows did not grow with the font) and
every chip built on the Button API (icon + text + badge — e.g. the gallery
card's "Анализ" pill) kept design-px internal padding while the font grew.

Two distinct bugs, both about a value derived once instead of at USE time:

- ``ContextMenuRow``'s own fixed height followed the scale (``Button``
  re-applies it on ``scale_changed``), but the section-title / separator
  heights, the check gutter, the trailing shortcut/arrow width and the
  rasterized row icon were construction-time snapshots, and the cached menu
  never re-fit itself through the appearance bus;
- ``content_padding`` and the icon↔label ``gap`` were applied in raw design
  px inside the paint / sizeHint paths, so a chip's internal sections stayed
  put while the (already scale-resolved) font grew.

Every number below is asserted against ``scaled_px(design)`` at the new
factor, not just "it changed".
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    Button,
    ContextMenu,
    ContextMenuAction,
    ContextMenuSeparator,
    ContextMenuSection,
)


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _sectioned_menu(qtbot) -> ContextMenu:
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(640, 480)
    menu = ContextMenu(
        parent,
        entries=(
            ContextMenuSection(
                (
                    ContextMenuAction("rename", "Rename entry"),
                    ContextMenuAction("copy", "Copy entry", shortcut="Ctrl+C"),
                ),
                title="Section",
            ),
            ContextMenuSeparator(),
            ContextMenuAction("del", "Delete entry", children=(ContextMenuAction("perm", "Permanently"),)),
        ),
    )
    qtbot.addWidget(menu)
    return menu


def test_context_menu_row_pitch_re_derives_on_live_scale(qtbot):
    """Build at 1.0, scale to 1.5 live → row/section/separator pitch grows."""
    menu = _sectioned_menu(qtbot)
    widgets = [
        menu.content_layout.itemAt(i).widget()
        for i in range(menu.content_layout.count())
    ]
    title_row = next(w for w in widgets if type(w).__name__ == "SectionTitleRow")
    separator_row = next(w for w in widgets if type(w).__name__ == "SeparatorRow")
    shortcut_row = next(r for r in menu._rows if r._shortcut_text)
    submenu_row = next(r for r in menu._rows if r._has_children)
    container_height_before = menu.container.height()

    # Anchored baseline at 1.0.
    assert title_row.height() == 24
    assert separator_row.height() == 9
    assert menu._rows[0].sizeHint().height() == 32
    assert shortcut_row._check_gutter == 12
    assert shortcut_row._trailing_width == (
        QFontMetrics(shortcut_row.font()).horizontalAdvance("Ctrl+C") + 8
    )
    assert submenu_row._trailing_width == 20

    UiScale.get_instance().set_factor(1.5)
    qtbot.wait(20)  # the appearance bus coalesces through a zero-timer

    # Every chrome metric grew by exactly the factor, not "a bit".
    assert title_row.height() == pytest.approx(24 * 1.5, abs=1)
    assert title_row.height() == 36
    assert separator_row.height() == 14  # scaled_px(9)
    assert menu._rows[0].sizeHint().height() == 48  # scaled_px(32)
    assert shortcut_row._check_gutter == 18  # scaled_px(12)
    assert shortcut_row._trailing_width == pytest.approx(
        QFontMetrics(shortcut_row.font()).horizontalAdvance("Ctrl+C") + 12, abs=2
    )
    assert submenu_row._trailing_width == 30  # scaled_px(20)
    # The cached menu re-fits its own geometry, so the taller rows fit.
    assert menu.container.height() > container_height_before


def test_context_menu_row_icon_re_derives_on_live_scale(qtbot, monkeypatch):
    """A row's icon is re-rasterized at the new factor, not left at 16 px.

    The raster is produced in the row's paint pass (with the painter's own
    device ratio, so a fractional-scaling session cannot resample it), not at
    construction: the row is built before it is shown on any screen.
    """
    from PySide6.QtGui import QIcon, QPixmap

    import sli_ui_toolkit.ui.widgets.composite.context_menu.rows as rows_mod

    sizes: list[int] = []
    ratios: list[float] = []
    real = rows_mod.normalized_icon_pixmap

    def _spy(source, size, **kwargs):
        sizes.append(int(size))
        ratios.append(float(kwargs.get("dpr") or 0.0))
        return real(source, size, **kwargs)

    monkeypatch.setattr(rows_mod, "normalized_icon_pixmap", _spy)

    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.red)
    parent = QWidget()
    qtbot.addWidget(parent)
    menu = ContextMenu(
        parent, entries=(ContextMenuAction("with-icon", "With icon", icon=QIcon(pixmap)),)
    )
    qtbot.addWidget(menu)
    assert menu._rows[0]._icon_source is not None
    menu.container.grab()  # one paint pass
    assert sizes[-1] == 16  # scaled_px(ICON_SIZE) at 1.0
    assert ratios[-1] > 0.0, "the paint pass must pass an explicit device ratio"

    UiScale.get_instance().set_factor(1.5)
    try:
        qtbot.wait(20)
        menu.container.grab()
        assert sizes[-1] == 24  # scaled_px(16) — re-derived on the live change
    finally:
        UiScale.get_instance().set_factor(1.0)


def _painter_context(button: Button, width: int, height: int):
    from sli_ui_toolkit.ui.widgets.buttons.painter import make_draw_context

    button.resize(width, height)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    return painter, image, make_draw_context(button, painter)


def test_chip_content_insets_follow_live_scale(qtbot):
    """The chip's design-px ``content_padding`` grows with the factor."""
    from sli_ui_toolkit.ui.widgets.buttons.content import _rect

    button = Button(
        text="Анализ",
        size=(0, 40),
        content_padding=(8, 4, 8, 4),
        gap=6,
    )
    qtbot.addWidget(button)

    painter, _image, ctx = _painter_context(button, 120, 40)
    try:
        inner = _rect(ctx)
    finally:
        painter.end()
    assert (inner.left(), inner.top()) == (8, 4)
    assert (inner.right(), inner.bottom()) == (120 - 1 - 8, 40 - 1 - 4)

    UiScale.get_instance().set_factor(1.5)
    qtbot.wait(20)

    painter, _image, ctx = _painter_context(button, 180, 60)
    try:
        inner = _rect(ctx)
    finally:
        painter.end()
    # design 8/4 → scaled_px: 12/6 at 1.5 (not the raw 8/4 the bug left).
    assert (inner.left(), inner.top()) == (12, 6)
    assert (inner.right(), inner.bottom()) == (180 - 1 - 12, 60 - 1 - 6)


def _rendered_icon_label_gap(button: Button, width: int, height: int, text: str) -> int:
    """Recover the painted icon↔label gap from a real render of the chip.

    The chip is right-aligned (``content_align``), so ``start_x`` is
    ``inner.left + inner.width - total_w`` with no floor-division — the icon
    bbox (a solid-red pixmap, no antialias) recovers ``total_w`` exactly, and
    the label advance is read from the *same painter* the content draws with
    so a host font landing from a neighbouring test cannot skew it.
    """
    from sli_ui_toolkit.ui.managers.ui_font import paint_font
    from sli_ui_toolkit.ui.widgets.buttons.content import IconTextContent, _rect

    painter, image, ctx = _painter_context(button, width, height)
    painter.setFont(paint_font(button))
    text_w = painter.fontMetrics().horizontalAdvance(text)
    try:
        IconTextContent(icon=button._icon_unchecked, text=text).draw(
            ctx, ThemeManager.get_instance()
        )
    finally:
        painter.end()
    inner = _rect(ctx)
    icon_xs = [
        x
        for y in range(height)
        for x in range(width)
        if (lambda c: c.red() > 200 and c.green() < 60 and c.blue() < 60)(
            image.pixelColor(x, y)
        )
    ]
    assert icon_xs, "the chip icon was not painted"
    icon_left = min(icon_xs)
    icon_w = max(icon_xs) - min(icon_xs) + 1
    total_w = inner.left() + inner.width() - icon_left
    return total_w - icon_w - text_w


def test_chip_icon_label_gap_follows_live_scale(qtbot):
    """The icon↔label ``gap`` design px is resolved through the live factor."""
    from PySide6.QtGui import QIcon, QPixmap

    pixmap = QPixmap(64, 64)  # large source: QIcon renders it at any request
    pixmap.fill(Qt.GlobalColor.red)
    button = Button(
        text="Анализ",
        icon=QIcon(pixmap),
        size=(0, 40),
        icon_size=16,
        gap=6,
        content_align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
    )
    qtbot.addWidget(button)

    assert _rendered_icon_label_gap(button, 120, 40, "Анализ") == 6

    UiScale.get_instance().set_factor(1.5)
    qtbot.wait(20)

    # design 6 → scaled_px: 9 at 1.5 (was still 6 before the fix).
    assert _rendered_icon_label_gap(button, 180, 60, "Анализ") == 9


def _badge_bbox(button: Button, width: int, height: int) -> tuple[int, int, int, int]:
    from sli_ui_toolkit.ui.widgets.buttons.layers.badge import BadgeLayer

    painter, image, ctx = _painter_context(button, width, height)
    try:
        BadgeLayer().draw(ctx, ThemeManager.get_instance())
    finally:
        painter.end()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 0:
                xs.append(x)
                ys.append(y)
    assert xs, "BadgeLayer painted nothing"
    return min(xs), min(ys), max(xs), max(ys)


def test_chip_badge_box_follows_live_scale(qtbot):
    """The badge's design-px box (14 high) grows with the live factor."""
    button = Button(text="Анализ", badge="12", size=(0, 40))
    button.setBadgeStyle(filled=True, bordered=False)
    qtbot.addWidget(button)

    x0, y0, x1, y1 = _badge_bbox(button, 200, 40)
    assert x1 - x0 + 1 == 18  # scaled_px(14) rounded box + antialias fringe
    assert y1 - y0 + 1 == 14  # scaled_px(14) at 1.0

    UiScale.get_instance().set_factor(1.5)
    qtbot.wait(20)

    x0, y0, x1, y1 = _badge_bbox(button, 300, 60)
    assert y1 - y0 + 1 == 21  # scaled_px(14) at 1.5 — was still 14 before
