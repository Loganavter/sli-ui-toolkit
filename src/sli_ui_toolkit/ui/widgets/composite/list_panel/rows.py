"""Row specs and pure row-data helpers for ListPanel.

``ListRowSpec`` is the contract handed to the host's row factory;
``make_item_position`` / ``apply_item_data`` are pure transformations
(index/geometry → position label, item → row widget state) and the
``find_*`` / ``reorder_*`` helpers implement the list-diff alignment used
by the panel's in-place refresh. None of this touches the panel widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import os

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

ListItemType = str  # host-defined row kind, e.g. "image" / "simple"


@dataclass(slots=True)
class ListRowSpec:
    """Everything a host row factory needs to build one list row.

    ``on_update_drop_indicator`` / ``on_clear_drop_indicator`` are the
    panel's drag-visual callbacks — rows that initiate drags forward the
    drag position to them so the panel can show the insertion indicator.
    """

    index: int
    text: str
    full_path: str
    list_num: int
    is_current: bool
    item_height: int
    item_font: Any
    item_type: str
    position: str
    on_update_drop_indicator: Callable[[QPointF], None]
    on_clear_drop_indicator: Callable[[], None]
    # Optional rating data — hosts that display one read it here; the panel
    # itself never interprets it.
    rating: Any = 0

    def __post_init__(self) -> None:
        self.item_type = self.item_type or "default"


RowFactory = Callable[[ListRowSpec], QWidget]


def make_item_position(index: int, total: int) -> str:
    if total <= 1:
        return "only"
    if index == 0:
        return "first"
    if index == total - 1:
        return "last"
    return "middle"


def _resolve_row_text(img_item: Any) -> str:
    """Generic display-name fallback: display_name → basename(path) → str(item)."""
    raw = getattr(img_item, "display_name", "")
    if raw:
        return raw if isinstance(raw, str) else str(raw)
    path = getattr(img_item, "path", "")
    if path:
        stem = os.path.splitext(os.path.basename(str(path)))[0]
        if stem:
            return stem
    text = str(img_item)
    return text if text else ""


def apply_item_data(widget, index, img_item, current_index, total) -> None:
    """Push one item's data onto an existing row widget in place."""
    widget.index = index
    widget.full_path = img_item.path if hasattr(img_item, "path") else ""
    widget.is_current = index == current_index
    widget.position = make_item_position(index, total)
    widget.name_label.setText(_resolve_row_text(img_item))
    if hasattr(widget, "rating_label"):
        rating = img_item.rating if hasattr(img_item, "rating") else 0
        widget.rating_label.setText(str(rating))
    widget.update()


def find_removed_index(existing_paths, target_paths) -> int | None:
    for idx in range(len(existing_paths)):
        if existing_paths[:idx] + existing_paths[idx + 1 :] == target_paths:
            return idx
    return None


def find_inserted_index(existing_paths, target_paths) -> int | None:
    for idx in range(len(target_paths)):
        if target_paths[:idx] + target_paths[idx + 1 :] == existing_paths:
            return idx
    return None


def reorder_widgets_to_match(layout, target_paths) -> None:
    """Re-stack the layout's row widgets to match ``target_paths`` order."""
    widget_by_path = {
        getattr(widget, "full_path", ""): widget
        for i in range(layout.count())
        for widget in [layout.itemAt(i).widget() if layout.itemAt(i) else None]
        if widget is not None
    }
    for index, path in enumerate(target_paths):
        widget = widget_by_path.get(path)
        if widget is None:
            return
        layout.removeWidget(widget)
        layout.insertWidget(index, widget)
