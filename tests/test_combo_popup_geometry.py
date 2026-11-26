"""The combo popup's geometry reads ONE source per quantity, at any height.

The popup's height is configurable (``setMaxVisibleItems``) and its row height
is font-driven (``_item_height`` = max(scaled 28, font height + scaled
padding)), so a hardcoded second copy of either number anywhere in the parking
/ row-layout / scrollbar paths would desync as soon as a host leaves the
default 12 x 29 px. The owner's hypothesis (2026-11-24): "the height at which a
ComboBox opens is configurable, but some parameters in the geometry calculation
are hardcoded by height, so they can desync."

What is pinned here, all with a NON-DEFAULT visible count (3) and a SCALED
font (``UiScale`` 2.0):

- the popup card is exactly ``visible_items * item_height`` plus the field's
  row offset (the blank strip that keeps the anchored row on the field's text
  line while the card's top edge stays flush with the drawn field) plus the
  flyout shadow, and the container / viewport / row pitch agree with it;
- the last visible row's rect (its hit area) lies inside the popup, and a click
  on it commits that row — a row half outside the card would still be painted
  but not reachable;
- the scrollbar's range covers every row (max offset = count - visible) and its
  thumb is proportional to the page;
- an OPEN list re-derives all of that when its visible row count changes (the
  filter typing mode) or when items are added — the card used to keep the
  height it had at open while the rows/viewport read the new numbers;
- the flip decision (``calculate_anchored_dropdown_geometry``, the toolkit's
  only above/below placement helper) compares the space below with the FULL
  popup height, never with one row.

Note on the plain popup's own placement: it has no above/below flip at all.
``_DropdownOverlay._reposition`` parks the anchor row under the field (the
field-centric model, owner report 2026-10-22) and clamps the card inside the
window; that parity is pinned by ``tests/test_combo_focus_reveal.py``. The
"flip only on the full height" property belongs to the anchored helper, which
hosts use for dropdowns that really hang below a field.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.ui.widgets.helpers import (
    calculate_anchored_dropdown_geometry,
    field_row_offset,
)
from sli_ui_toolkit.widgets import ComboBox

SCALE = 2.0
VISIBLE = 3
ITEMS = 20


def _settle(app: QApplication, rounds: int = 8) -> None:
    for _ in range(rounds):
        app.processEvents()


def _open_popup(
    qtbot,
    *,
    items: int = ITEMS,
    max_visible: int = VISIBLE,
    factor: float = SCALE,
    typing_mode: str = "jump",
    texts: list[str] | None = None,
    host_size: tuple[int, int] = (460, 700),
    field_y: int = 140,
):
    """Host + combo with the popup open, at a non-default height and scale."""
    app = QApplication.instance()
    UiScale.get_instance().set_factor(factor)
    _settle(app)
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(*host_size)
    combo = ComboBox(parent=host, typing_mode=typing_mode)
    combo.setGeometry(20, field_y, 220, scaled_px(combo.BASE_HEIGHT))
    combo.addItems(texts if texts is not None else [str(i) for i in range(items)])
    combo.setMaxVisibleItems(max_visible)
    combo.setCurrentIndex(0)
    host.show()
    qtbot.waitExposed(host)
    combo.showDropdown()
    _settle(app)
    assert combo._expanded and combo._overlay is not None and combo._overlay.isVisible()
    return host, combo


def _row_rect_in(overlay, slot) -> QRect:
    """The slot's rect in overlay coordinates (its painted / hit area).

    ``slot.geometry()`` is already in the viewport's coordinate system, so
    translate the mapped origin — never the rect with its own y.
    """
    top_left = slot.mapTo(overlay, QPoint(0, 0))
    return QRect(top_left, slot.size())


def test_popup_height_is_visible_rows_times_the_one_row_height(qtbot):
    app = QApplication.instance()
    host, combo = _open_popup(qtbot)
    overlay = combo._overlay

    item_h = combo._item_height()
    assert item_h == max(
        scaled_px(28),
        QFontMetrics(paint_font(combo)).height() + scaled_px(combo.ITEM_VERTICAL_PADDING),
    ), "the row height must be the font-driven formula, not a literal"
    assert item_h > scaled_px(28), "fixture must exercise the font-driven branch, not the 28 px floor"
    assert combo.maxVisibleItems() == VISIBLE, "fixture must leave the default 12"

    list_h = VISIBLE * item_h
    pad = field_row_offset(combo.field_rect(), item_h)
    assert overlay._visible_items() == VISIBLE
    assert overlay._list_height() == list_h
    assert overlay._card_top_pad() == pad
    assert overlay.height() == list_h + pad + 2 * overlay.SHADOW_RADIUS, (
        "the popup card must be the list's content height, the field's row "
        "offset and the flyout shadow"
    )
    assert overlay.container.height() == list_h + pad, (
        "the painted card must be the list's content height plus the field's row offset"
    )
    assert overlay._list_viewport.height() == list_h

    rows = [(s._item_index, s.geometry()) for s in overlay._slots if s.isVisible()]
    assert [idx for idx, _ in rows] == [0, 1, 2]
    for visible_pos, (_, rect) in enumerate(rows):
        assert rect.y() == visible_pos * item_h, "row pitch must be the row height"
        assert rect.height() == item_h, "a row must fill one pitch, not the 33 px field height"
    assert rows[-1][1].bottom() + 1 == list_h, "the last row must end at the list's bottom edge"

    host.close()


def test_the_last_visible_row_is_clickable_inside_the_popup(qtbot):
    app = QApplication.instance()
    host, combo = _open_popup(qtbot)
    overlay = combo._overlay

    row = combo.dropdown_row_widget(VISIBLE - 1)
    assert row is not None, "the last visible row must be bound"
    rect = _row_rect_in(overlay, row)
    assert overlay.rect().contains(rect), (
        f"last row {rect.getRect()} escapes popup {overlay.rect().getRect()}: its hit area is outside the card"
    )
    assert overlay.container.rect().contains(
        rect.translated(-overlay.container.geometry().topLeft())
    )

    QTest.mouseClick(row, Qt.MouseButton.LeftButton, pos=row.rect().center())
    _settle(app)

    assert combo.currentIndex() == VISIBLE - 1, "a click on the last visible row must commit it"
    assert not combo._expanded, "committing a row closes the list"

    host.close()


def test_scrollbar_range_covers_every_row_and_the_thumb_is_proportional(qtbot):
    app = QApplication.instance()

    # (a) 20 rows, 3 visible: the proportional thumb (3/20) is under the bar's
    # minimum handle length, so the floor must apply — never a second height.
    host, combo = _open_popup(qtbot)
    overlay = combo._overlay
    sb = overlay.custom_v_scrollbar

    assert sb.isVisible()
    assert (sb.minimum(), sb.maximum()) == (0, ITEMS - VISIBLE), (
        "the range must reach the last row's offset (count - visible rows)"
    )
    assert sb.pageStep() == VISIBLE

    groove = sb.height() - 2 * 8  # MinimalistScrollBar's handle padding
    proportion = sb.pageStep() / (sb.maximum() - sb.minimum() + sb.pageStep())
    expected = max(proportion * groove, sb._minimum_handle_length)
    handle = sb._get_handle_rect()
    assert abs(handle.height() - expected) <= 1, (
        f"thumb {handle.height()} px is not {expected:.1f} px for an {sb.height()} px bar"
    )

    sb.setValue(sb.maximum())
    _settle(app)
    assert combo._scroll_offset == ITEMS - VISIBLE
    last = combo.dropdown_row_widget(ITEMS - 1)
    assert last is not None, "scrolling to the end must materialise the last item"
    assert last.geometry().bottom() + 1 == overlay._list_viewport.height(), (
        "at max offset the last row sits exactly at the viewport's bottom edge"
    )
    handle = sb._get_handle_rect()
    assert handle.bottom() < sb.height(), "the thumb must stay inside its own bar at max offset"
    host.close()

    # (b) 10 rows, 3 visible: 3/10 of the groove is above the floor, so this is
    # the proportional regime the floor must not distort.
    host, combo = _open_popup(qtbot, items=10)
    overlay = combo._overlay
    sb = overlay.custom_v_scrollbar
    assert (sb.minimum(), sb.maximum(), sb.pageStep()) == (0, 7, VISIBLE)
    proportion = sb.pageStep() / (sb.maximum() - sb.minimum() + sb.pageStep())
    groove = sb.height() - 2 * 8
    assert proportion * groove > sb._minimum_handle_length, (
        "fixture (b) must exercise the proportional regime, not the floor"
    )
    handle = sb._get_handle_rect()
    assert abs(handle.height() - proportion * groove) <= 1, (
        f"thumb {handle.height()} px is not the proportional {proportion * groove:.1f} px"
    )
    assert handle.bottom() < sb.height()
    host.close()


def test_an_open_popup_follows_a_filter_that_changes_the_row_count(qtbot):
    """The card's height is derived, not frozen at open time."""
    app = QApplication.instance()
    host, combo = _open_popup(
        qtbot,
        max_visible=6,
        typing_mode="filter",
        factor=1.0,
        texts=["apple", "apricot", "banana", "cherry", "date", "elder", "fig", "grape"],
    )
    overlay = combo._overlay
    item_h = combo._item_height()

    pad = field_row_offset(combo.field_rect(), item_h)
    assert overlay._visible_items() == 6
    assert overlay.height() == 6 * item_h + pad + 2 * overlay.SHADOW_RADIUS

    combo._set_search_text("ap")  # apple, apricot, grape
    _settle(app)
    narrowed = len(combo._visible_indices())
    assert 0 < narrowed < 6, "the fixture query must narrow the rows"
    assert overlay._visible_items() == narrowed
    assert overlay.height() == narrowed * item_h + pad + 2 * overlay.SHADOW_RADIUS, (
        "the popup must shrink with the filtered rows, not keep its open-time height"
    )
    assert overlay.container.height() == narrowed * item_h + pad
    assert overlay._list_viewport.height() == narrowed * item_h
    last = combo.dropdown_row_widget(combo._visible_indices()[-1])
    if last is not None:
        assert last.geometry().bottom() + 1 <= overlay._list_viewport.height(), (
            "the last filtered row must stay inside the shrunk viewport"
        )

    combo.clearSearch()
    _settle(app)
    pad = field_row_offset(combo.field_rect(), item_h)
    assert overlay._visible_items() == 6
    assert overlay.height() == 6 * item_h + pad + 2 * overlay.SHADOW_RADIUS, (
        "clearing the filter must grow the popup back"
    )

    host.close()


def test_adding_items_while_open_grows_the_popup(qtbot):
    app = QApplication.instance()
    host, combo = _open_popup(qtbot, items=2, max_visible=6, factor=1.0)
    overlay = combo._overlay
    item_h = combo._item_height()

    pad = field_row_offset(combo.field_rect(), item_h)
    assert overlay.height() == 2 * item_h + pad + 2 * overlay.SHADOW_RADIUS
    combo.addItem("two")
    combo.addItem("three")
    _settle(app)

    assert overlay._visible_items() == 4
    assert overlay.height() == 4 * item_h + pad + 2 * overlay.SHADOW_RADIUS, (
        "an item added while the list is open must reach the popup's own height"
    )
    visible_rows = [s._item_index for s in overlay._slots if s.isVisible()]
    assert visible_rows == [0, 1, 2, 3], "the added rows must be materialised, not just counted"

    host.close()


def test_the_flip_compares_the_space_below_with_the_full_popup_height(qtbot):
    """A dropdown may hang above only when the FULL popup does not fit below.

    One row fitting below is not enough: that is the desync the owner's
    hypothesis predicts when a single row height is mistaken for the popup's.
    """
    app = QApplication.instance()
    UiScale.get_instance().set_factor(1.0)
    _settle(app)
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(320, 600)
    combo = ComboBox(parent=host)
    combo.setGeometry(20, 100, 220, 33)
    host.show()
    qtbot.waitExposed(host)

    row_h = combo._item_height()
    content = QSize(220, VISIBLE * row_h)
    shadow = BaseFlyout.SHADOW_RADIUS
    full_height = content.height() + 2 * shadow
    field_h = combo.height()

    def place(field_y: int) -> tuple[QRect, int, int]:
        """Outer rect (host coords) + the field's top/bottom edges."""
        combo.setGeometry(20, field_y, 220, field_h)
        _settle(app)
        rect = calculate_anchored_dropdown_geometry(
            anchor_widget=combo,
            field_rect=combo.field_rect(),
            owner_window=host,
            content_size=content,
            shadow_radius=shadow,
            gap=4,
        )
        field_top = combo.mapTo(host, QPoint(0, 0)).y()
        return rect, field_top, field_top + field_h

    def content_top(rect: QRect) -> int:
        return rect.top() + shadow

    def content_bottom(rect: QRect) -> int:
        return rect.bottom() - shadow

    # (a) room below for the whole popup -> hangs below the field.
    rect, field_top, field_bottom = place(300)
    assert 600 - field_bottom >= full_height, "fixture (a) must have room for the full popup"
    assert content_top(rect) >= field_bottom, (
        f"a fitting popup must open below the field, got content top {content_top(rect)} < {field_bottom}"
    )

    # (b) room below for ONE row but not the full popup -> flips above.
    space_below = row_h + 10
    assert row_h < space_below < full_height
    rect, field_top, field_bottom = place(600 - field_h - space_below)
    assert content_bottom(rect) <= field_top, (
        "with less than the full popup height below, one row's worth of space must not "
        f"keep the list under the field: content bottom {content_bottom(rect)} vs field top {field_top}"
    )
    assert rect.top() < field_top

    # (c) exactly the full popup height below -> below again.
    rect, field_top, field_bottom = place(600 - field_h - (full_height + 5))
    assert content_top(rect) >= field_bottom, (
        "a full popup height of room below must keep the list below"
    )

    host.close()
