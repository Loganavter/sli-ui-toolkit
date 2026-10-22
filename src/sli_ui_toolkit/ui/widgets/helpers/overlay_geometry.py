from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QWidget


def centered_inner_offset(outer: float, inner: float) -> int:
    """``round((outer - inner) / 2)`` — the offset that centers a smaller
    box inside a bigger one along one axis.

    Use this (never plain ``// 2``) anywhere a widget's own centered content
    must land in visual agreement with a *different* widget/overlay that
    centers the same-size inner box independently — e.g. ComboBox's field
    label vs. its dropdown popup and gear-drag frame, which all align the
    same row height inside the field height. ``//`` floors and ``round()``
    rounds-half-to-even, so mixing the two across such call sites drifts
    apart by a px whenever the height difference is odd — this bit twice in
    the combo box (see ``combo_box.py``'s ``_ComboFieldContentLayer`` and
    ``_overlay.py``'s ``_update_gear_frame``) before both were switched to
    call this helper instead of re-deriving the formula by hand.
    """
    return round((outer - inner) / 2)


def calculate_centered_overlay_geometry(
    *,
    anchor_widget: QWidget,
    owner_window: QWidget,
    content_size: QSize,
    shadow_radius: int,
    current_index: int,
    visible_index: int,
    row_height: int,
    scrollable: bool,
) -> QRect:
    """Place an overlay so ``visible_index``'s row sits exactly under the anchor.

    Both the fitted and the scrollable case align the ROW, never the list's
    centre: with an even number of visible rows a centred list puts the
    anchor's centre on a row boundary, leaving the selected row half a row
    off (owner report 2026-10-22). ``scrollable`` is kept in the signature for
    callers that pass their own scroll state; both branches share the
    alignment formula.
    """
    outer_width = content_size.width() + shadow_radius * 2
    outer_height = content_size.height() + shadow_radius * 2

    combo_rect = anchor_widget.rect()
    field_top_global = anchor_widget.mapToGlobal(combo_rect.topLeft()).y()
    owner_top_left_global = anchor_widget.mapToGlobal(combo_rect.topLeft())
    window_top_left_global = owner_window.mapToGlobal(QPoint(0, 0))
    window_global_rect = QRect(window_top_left_global, owner_window.size())

    if current_index < 0:
        current_index = 0
    if visible_index < 0:
        visible_index = 0

    # Anchor the selected ROW, never the list's centre — for both overflow and
    # fitted lists. Centring the outer box on the field puts the field's centre
    # on a row BOUNDARY whenever the visible window has an even number of rows
    # (12 visible -> the field sits between rows 5 and 6), so the selected row
    # reads as half a row off and the user has to nudge the list up by half a
    # row (owner report 2026-10-22). Aligning the row top to the field's inner
    # top is exact for every parity and every scale factor, and it matches the
    # gear-drag frame (``_GearFrame`` uses the same ``centered_inner_offset``).
    selected_item_offset_y = visible_index * row_height
    ideal_y_global = (
        field_top_global
        + centered_inner_offset(combo_rect.height(), row_height)
        - selected_item_offset_y
        - shadow_radius
    )

    ideal_x_global = int(owner_top_left_global.x() - shadow_radius)

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
    owner_window: QWidget,
    content_size: QSize,
    shadow_radius: int,
    gap: int = 4,
) -> QRect:
    """Place the dropdown below the field (or above if it does not fit).

    Used when Find Action reveals a non-current option: the selection-centered
    layout would park the committed row on the button and steal visual focus
    from the highlighted target row.
    """
    outer_width = content_size.width() + shadow_radius * 2
    outer_height = content_size.height() + shadow_radius * 2

    combo_rect = anchor_widget.rect()
    field_bottom_left = anchor_widget.mapToGlobal(combo_rect.bottomLeft())
    field_top_left = anchor_widget.mapToGlobal(combo_rect.topLeft())
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
