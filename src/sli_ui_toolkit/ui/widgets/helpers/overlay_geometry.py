from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QWidget


def centered_inner_offset(outer: float, inner: float) -> int:
    """``round((outer - inner) / 2)`` — the offset that centers a smaller
    box inside a bigger one along one axis.

    Use this (never plain ``// 2``) anywhere a widget's own centered content
    must land in visual agreement with a *different* widget/overlay that
    centers the same-size inner box independently — e.g. ComboBox's field
    label vs. its dropdown popup, which both align the same row height inside
    the field height. ``//`` floors and ``round()`` rounds-half-to-even, so
    mixing the two across such call sites drifts apart by a px whenever the
    height difference is odd — this bit twice in the combo box (see
    ``combo_box.py``'s ``_ComboFieldContentLayer`` and ``_overlay.py``'s
    popup placement) before both were switched to call this helper instead of
    re-deriving the formula by hand.
    """
    return round((outer - inner) / 2)


def field_row_offset(field_rect: QRect, row_height: int) -> int:
    """Distance from a field's DRAWN top to the top of its row box, in px.

    One formula for two consumers, so they cannot drift:

    - the field paints its label in the box ``field_rect`` inset by this
      offset (``_ComboFieldContentLayer``);
    - the dropdown card carries exactly this much blank surface above its
      first row, which is what keeps the anchored row on the field's own text
      line while the card's top edge stays flush with the field's drawn top.

    Centered, not top-aligned: a row parked at the field's very top would ride
    ``(field_height - row_height) / 2`` px above the painted value — the
    "label jumps when the list opens" class of report (2026-10-22).
    """
    return centered_inner_offset(field_rect.height(), row_height)


def calculate_centered_overlay_geometry(
    *,
    anchor_widget: QWidget,
    field_rect: QRect,
    owner_window: QWidget,
    content_size: QSize,
    shadow_radius: int,
    current_index: int,
    visible_index: int,
    row_height: int,
    scrollable: bool,
) -> QRect:
    """Place a field-centric overlay card against the field's DRAWN rect.

    ``field_rect`` is the box the anchor's plate is painted in — the widget's
    own coordinates, from ``anchor_widget.field_rect()`` — and never
    ``anchor_widget.rect()``: a control whose plate is inset inside its widget
    (border/padding chrome) must have its popup follow the plate, or the card
    is offset by that inset and sized to the widget instead of the field
    (owner report 2026-11-26).

    The card's top edge is flush with ``field_rect.top()``, shifted up by the
    rows scrolled out above ``visible_index``. It is NOT placed on the
    anchored row: a card parked on the row leaves ``field_row_offset`` px of
    the field's plate (with its own rounded corners) peeking above the popup —
    the seam this function exists to remove. The caller pads the card by
    ``field_row_offset(field_rect, row_height)`` so the anchored row still
    lands on the field's text line. ``current_index`` and ``scrollable`` are
    accepted for callers that pass their own scroll state and are not read.
    """
    outer_width = content_size.width() + shadow_radius * 2
    outer_height = content_size.height() + shadow_radius * 2

    if visible_index < 0:
        visible_index = 0

    field_top_left_global = anchor_widget.mapToGlobal(field_rect.topLeft())
    window_top_left_global = owner_window.mapToGlobal(QPoint(0, 0))
    window_global_rect = QRect(window_top_left_global, owner_window.size())

    # The card follows the field: its top is the field's top, pulled up only
    # by the rows the list scrolled past (they render above it, still inside
    # the card).
    ideal_y_global = field_top_left_global.y() - visible_index * row_height - shadow_radius
    ideal_x_global = int(field_top_left_global.x() - shadow_radius)

    final_x_global = max(
        window_global_rect.left(),
        min(ideal_x_global, window_global_rect.right() - outer_width + 1),
    )
    final_y_global = max(
        window_global_rect.top(),
        min(ideal_y_global, window_global_rect.bottom() - outer_height + 1),
    )

    top_left = owner_window.mapFromGlobal(QPoint(final_x_global, final_y_global))
    return QRect(top_left.x(), top_left.y(), outer_width, outer_height)


def calculate_anchored_dropdown_geometry(
    *,
    anchor_widget: QWidget,
    field_rect: QRect,
    owner_window: QWidget,
    content_size: QSize,
    shadow_radius: int,
    gap: int = 4,
) -> QRect:
    """Place the dropdown below the field (or above if it does not fit).

    Used when Find Action reveals a non-current option: the selection-centered
    layout would park the committed row on the button and steal visual focus
    from the highlighted target row.

    ``field_rect`` is the anchor's DRAWN plate rect in its own coordinates
    (``anchor_widget.field_rect()``): the ``gap`` is measured from the painted
    bottom edge, not from the edge of a possibly taller/inset widget.
    """
    outer_width = content_size.width() + shadow_radius * 2
    outer_height = content_size.height() + shadow_radius * 2

    field_bottom_left = anchor_widget.mapToGlobal(field_rect.bottomLeft())
    field_top_left = anchor_widget.mapToGlobal(field_rect.topLeft())
    window_top_left_global = owner_window.mapToGlobal(QPoint(0, 0))
    window_global_rect = QRect(window_top_left_global, owner_window.size())

    ideal_x_global = int(field_top_left.x() - shadow_radius)
    below_y = int(field_bottom_left.y() + gap - shadow_radius)
    above_y = int(field_top_left.y() - gap - outer_height + shadow_radius)

    if below_y + outer_height <= window_global_rect.bottom() + 1:
        ideal_y_global = below_y
    elif above_y >= window_global_rect.top():
        ideal_y_global = above_y
    else:
        ideal_y_global = below_y

    final_x_global = max(
        window_global_rect.left(),
        min(ideal_x_global, window_global_rect.right() - outer_width + 1),
    )
    final_y_global = max(
        window_global_rect.top(),
        min(ideal_y_global, window_global_rect.bottom() - outer_height + 1),
    )

    top_left = owner_window.mapFromGlobal(QPoint(final_x_global, final_y_global))
    return QRect(top_left.x(), top_left.y(), outer_width, outer_height)
