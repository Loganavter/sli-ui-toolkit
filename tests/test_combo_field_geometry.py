"""The dropdown follows the FIELD the combo DRAWS, not the widget it fills.

Owner report (2026-11-26): "the combobox does not account for the height of the
trigger button and its rounding, so it constantly misses on geometry". What a
person sees and clicks is the field's painted plate; the widget rect is only
the box the plate happens to fill for the stock combo. Placement used
``anchor_widget.rect()`` for everything and parked the card on the anchored
ROW, which left ``(field_height - row_height) / 2`` px of the field's own
rounded plate peeking above the popup, and the card's corner radius came from
``BaseFlyout.CONTENT_RADIUS`` (a design-px constant) while the field's came
from the combo's token scaled by ``UiScale`` — two numbers for the same visible
corner, drifting apart with the scale factor.

Pinned here, at scale 1.0 AND 1.5:

- the anchored row lands in the field's ROW box (``ComboBox.field_row_rect``),
  so the popup's row text sits on the field's own text line;
- the card's top edge is flush with the field's DRAWN top — the plate does not
  peek above the popup, and the two corner arcs nest;
- the popup's width is the field's width (+ the shadow radius on both sides),
  never the widget's;
- a host whose plate is inset inside a TALLER/wider trigger (the reported case)
  gets the popup on the plate, in both the field-centric and the
  below/above (``calculate_anchored_dropdown_geometry``) modes;
- a configured ``corner_radius`` reaches both the plate's paint and the card —
  one token, two surfaces.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.helpers import calculate_anchored_dropdown_geometry
from sli_ui_toolkit.widgets import ComboBox

ITEMS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
VISIBLE = 4


class _InsetFieldCombo(ComboBox):
    """A host combo whose plate is drawn INSIDE a taller/wider trigger.

    The reported case: the widget reserves chrome the field does not fill, so
    ``rect()`` (what the placement used to read) and the drawn field part ways.
    Overriding the one hook — ``field_rect()`` — is all a host owes the popup.
    """

    def __init__(self, *, inset: tuple[int, int, int, int], **kwargs) -> None:
        super().__init__(**kwargs)
        self._inset = inset
        self._sync_field_tooltip()

    def field_rect(self) -> QRect:
        # ``getattr``: the base constructor asks for the field before this
        # subclass attribute exists (field_rect is public API, callable from
        # any early hook); the inset applies from the first real layout on.
        left, top, right, bottom = getattr(self, "_inset", (0, 0, 0, 0))
        return super().field_rect().adjusted(left, top, -right, -bottom)


def _settle(app: QApplication, rounds: int = 8) -> None:
    for _ in range(rounds):
        app.processEvents()


def _open(
    qtbot,
    *,
    factor: float,
    inset: tuple[int, int, int, int] = (0, 0, 0, 0),
    extra_height: int = 0,
    radius: int | None = None,
    widget_width: int = 220,
    current: int = 0,
    free_size: bool = False,
) -> tuple[QWidget, ComboBox]:
    app = QApplication.instance()
    UiScale.get_instance().set_factor(factor)
    _settle(app)

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(460, 700)
    combo = _InsetFieldCombo(inset=inset, parent=host)
    height = scaled_px(combo.BASE_HEIGHT) + extra_height
    if free_size:
        # A host that sizes a tall/wider trigger by geometry, not by a fixed
        # size: ``setFixedSize`` would also raise ``minimumWidth``, which is
        # the popup's width floor and would mask the drawn field's own width.
        combo.setMinimumSize(0, 0)
        combo.setMaximumSize(16777215, 16777215)
        combo.resize(widget_width, height)
    else:
        combo.setFixedSize(widget_width, height)
    if radius is not None:
        combo.setCornerRadiusPx(radius)
    combo.addItems(ITEMS)
    combo.setMaxVisibleItems(VISIBLE)
    combo.setCurrentIndex(current)
    combo.move(40, 160)
    host.show()
    qtbot.waitExposed(host)

    combo.showDropdown()
    _settle(app)
    assert combo._expanded and combo._overlay is not None and combo._overlay.isVisible()
    return host, combo


def _card(combo: ComboBox) -> QRect:
    """The painted card's rect in the owner host's coordinates."""
    overlay = combo._overlay
    host = combo.window()
    return QRect(
        overlay.container.mapTo(host, QPoint(0, 0)),
        overlay.container.size(),
    )


def _field(combo: ComboBox) -> QRect:
    """The DRAWN field's rect in the owner host's coordinates."""
    host = combo.window()
    field = combo.field_rect()
    return QRect(combo.mapTo(host, field.topLeft()), field.size())


def _visible_index(combo: ComboBox) -> int:
    """The anchored row's position inside the visible window."""
    anchor = combo._focus_or_current_index()
    return max(
        0,
        combo._visible_position_for_index(anchor) - combo._scroll_offset,
    )


def _row(combo: ComboBox) -> QRect:
    """The anchored row's rect in the owner host's coordinates."""
    host = combo.window()
    row = combo.dropdown_row_widget(combo.currentIndex())
    assert row is not None, "the current row must be inside the opened window"
    return QRect(row.mapTo(host, QPoint(0, 0)), row.size())


@pytest.mark.parametrize("factor", [1.0, 1.5])
def test_the_anchored_row_lands_in_the_drawn_fields_row_box(qtbot, factor):
    """The row's top == the row box inside the field, at any scale."""
    host, combo = _open(qtbot, factor=factor)
    field = _field(combo)
    row_box = combo.field_row_rect()
    row_box_host = QRect(
        combo.mapTo(host, row_box.topLeft()), row_box.size()
    )
    row = _row(combo)

    assert abs(row.top() - row_box_host.top()) <= 1, (
        f"row top {row.top()} is not the field's row box top {row_box_host.top()}"
    )
    assert field.contains(row.topLeft()), (
        "the anchored row must sit inside the drawn field, not beside it"
    )
    host.close()


@pytest.mark.parametrize("factor", [1.0, 1.5])
def test_the_popup_card_is_flush_with_the_drawn_fields_top(qtbot, factor):
    """No band of the field's plate above the card: the corners nest.

    The card used to be parked on the anchored ROW, which left
    ``(field_height - row_height) / 2`` px of the field's rounded plate visible
    above it — 2 px at 1.0 and 4 px at 1.5 (measured).
    """
    host, combo = _open(qtbot, factor=factor)
    field = _field(combo)
    card = _card(combo)
    visible_index = _visible_index(combo)
    assert visible_index == 0, "fixture must have no rows scrolled above the field"

    assert abs(card.top() - field.top()) <= 1, (
        f"card top {card.top()} vs field top {field.top()}: the plate peeks above the popup"
    )
    host.close()


@pytest.mark.parametrize("factor", [1.0, 1.5])
def test_a_scrolled_open_shows_the_rows_above_the_field(qtbot, factor):
    """The only offset the card may have: the rows scrolled past it.

    The card's top follows the drawn field's top minus the rows that render
    above it (the list is centred on the field); the anchored row keeps landing
    in the field's row box either way.
    """
    host, combo = _open(qtbot, factor=factor, current=5)
    field = _field(combo)
    card = _card(combo)
    visible_index = _visible_index(combo)
    assert visible_index > 0, "fixture must scroll rows above the field"

    expected = field.top() - visible_index * combo._item_height()
    assert abs(card.top() - expected) <= 1, (
        f"card top {card.top()} vs field top minus {visible_index} scrolled rows {expected}"
    )
    row = _row(combo)
    row_box = combo.field_row_rect()
    row_box_host = QRect(combo.mapTo(host, row_box.topLeft()), row_box.size())
    assert abs(row.top() - row_box_host.top()) <= 1
    host.close()


@pytest.mark.parametrize("factor", [1.0, 1.5])
def test_the_popup_width_is_the_drawn_fields_width_plus_the_shadow(qtbot, factor):
    host, combo = _open(qtbot, factor=factor)
    field = _field(combo)
    card = _card(combo)
    overlay = combo._overlay

    assert card.width() == field.width(), (
        f"card {card.width()} px wide, field {field.width()} px"
    )
    assert abs(card.left() - field.left()) <= 1
    outer = overlay.geometry()
    assert outer.width() == field.width() + 2 * overlay.SHADOW_RADIUS, (
        "the outer surface is the card plus the flyout shadow on both sides"
    )
    assert abs(outer.left() - (field.left() - overlay.SHADOW_RADIUS)) <= 1
    host.close()


def test_a_field_inset_inside_a_taller_widget_places_the_popup_on_the_field(qtbot):
    """The reported case: the widget is taller/wider than the plate it draws."""
    inset = (7, 5, 7, 11)
    host, combo = _open(
        qtbot,
        factor=1.0,
        inset=inset,
        extra_height=22,
        widget_width=260,
        free_size=True,
    )
    field = _field(combo)
    card = _card(combo)

    assert field.size() != combo.size(), "fixture must split widget from drawn field"
    assert field.top() == combo.mapTo(host, QPoint(0, 0)).y() + inset[1]
    assert abs(card.top() - field.top()) <= 1, (
        "the card must be flush with the DRAWN field's top, not the widget's"
    )
    assert card.width() == field.width(), (
        "the card must be the DRAWN field's width, not the widget's"
    )
    assert card.left() == field.left()

    row = _row(combo)
    row_box = combo.field_row_rect()
    row_box_host = QRect(combo.mapTo(host, row_box.topLeft()), row_box.size())
    assert abs(row.top() - row_box_host.top()) <= 1
    host.close()


@pytest.mark.parametrize("factor", [1.0, 1.5])
def test_a_configured_corner_radius_reaches_the_plate_and_the_card(qtbot, factor):
    """One radius token for the field's paint and the card's corners."""
    radius = 18
    host, combo = _open(qtbot, factor=factor, radius=radius)
    overlay = combo._overlay
    plate_radius = scaled_px(radius)

    assert combo.field_corner_radius() == radius
    assert overlay.CONTENT_RADIUS == plate_radius, (
        "the card's corners must be the field's corners, scaled the same way"
    )
    assert overlay._container_clip.radius() == plate_radius
    host.close()


def test_the_anchored_mode_sits_a_gap_below_the_drawn_fields_bottom(qtbot):
    """Below/above placement measures the gap from the drawn edge too."""
    inset = (0, 4, 0, 10)
    host, combo = _open(
        qtbot,
        factor=1.0,
        inset=inset,
        extra_height=20,
        widget_width=220,
        free_size=True,
    )
    combo.hideDropdown()
    _settle(QApplication.instance())

    overlay = combo._overlay
    content = QSize(combo.field_rect().width(), VISIBLE * combo._item_height())
    shadow = overlay.SHADOW_RADIUS
    gap = 4
    rect = calculate_anchored_dropdown_geometry(
        anchor_widget=combo,
        field_rect=combo.field_rect(),
        owner_window=host,
        content_size=content,
        shadow_radius=shadow,
        gap=gap,
    )
    field = _field(combo)
    content_top = rect.top() + shadow
    assert abs(content_top - (field.bottom() + 1 + gap)) <= 1, (
        "the dropdown's gap is measured from the DRAWN field's bottom edge"
    )
    # And not from the widget's: the difference the fix removes.
    widget_based = combo.mapTo(host, QPoint(0, 0)).y() + combo.height()
    assert abs(content_top - (widget_based + gap)) > 1
    host.close()


def test_a_shipped_combo_draws_its_plate_in_the_whole_widget_rect(qtbot):
    """Baseline the fix rests on: for the stock field, rect() IS the field.

    The plate's border hairline is stroked centred on the box's edge, so it
    lives INSIDE the field and does not shrink it (``FIELD_BORDER_WIDTH``).
    """
    host, combo = _open(qtbot, factor=1.5)
    assert combo.field_rect() == QRect(0, 0, combo.width(), combo.height())
    field = _field(combo)
    card = _card(combo)
    assert abs(card.top() - field.top()) <= 1
    host.close()
