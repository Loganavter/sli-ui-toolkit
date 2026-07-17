"""Self-contained adapter so UnifiedFlyout can be used without an external
store/controller/main_window — accepts plain item lists and two anchor widgets.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UnifiedFlyoutItem:
    display_name: str
    rating: int = 0
    path: str = ""


class _Document:
    def __init__(self) -> None:
        self.image_list1: list[UnifiedFlyoutItem] = []
        self.image_list2: list[UnifiedFlyoutItem] = []
        self.current_index1: int = -1
        self.current_index2: int = -1


class SimpleUnifiedFlyoutStore:
    """Minimal store with the same shape that UnifiedFlyout reads.

    Lets hosts use the widget standalone without supplying their own document
    object.
    """

    def __init__(self) -> None:
        self.document = _Document()

    def set_lists(
        self,
        left: list[UnifiedFlyoutItem | str],
        right: list[UnifiedFlyoutItem | str],
        *,
        current_left: int = -1,
        current_right: int = -1,
    ) -> None:
        self.document.image_list1 = [_coerce(i) for i in left]
        self.document.image_list2 = [_coerce(i) for i in right]
        self.document.current_index1 = current_left
        self.document.current_index2 = current_right


class SimpleUnifiedFlyoutController:
    """Receives selection / reorder callbacks from UnifiedFlyout panels."""

    def __init__(self, store: SimpleUnifiedFlyoutStore) -> None:
        self._store = store

    def on_combobox_changed(self, list_num: int, index: int) -> None:
        if list_num == 1:
            self._store.document.current_index1 = index
        elif list_num == 2:
            self._store.document.current_index2 = index

    def remove_specific_image_from_list(self, list_num: int, index: int) -> None:
        target = (
            self._store.document.image_list1
            if list_num == 1
            else self._store.document.image_list2
        )
        if 0 <= index < len(target):
            target.pop(index)

    def increment_rating(self, image_number: int, index: int) -> None:
        item = self._item(image_number, index)
        if item is not None:
            item.rating = min(5, item.rating + 1)

    def decrement_rating(self, image_number: int, index: int) -> None:
        item = self._item(image_number, index)
        if item is not None:
            item.rating = max(0, item.rating - 1)

    def reorder_item_in_list(
        self, *, image_number: int, source_index: int, dest_index: int
    ) -> None:
        target = (
            self._store.document.image_list1
            if image_number == 1
            else self._store.document.image_list2
        )
        if 0 <= source_index < len(target) and 0 <= dest_index <= len(target):
            item = target.pop(source_index)
            target.insert(dest_index, item)

    def move_item_between_lists(
        self,
        *,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ) -> None:
        src = (
            self._store.document.image_list1
            if source_list_num == 1
            else self._store.document.image_list2
        )
        dst = (
            self._store.document.image_list1
            if dest_list_num == 1
            else self._store.document.image_list2
        )
        if 0 <= source_index < len(src):
            item = src.pop(source_index)
            dst.insert(min(dest_index, len(dst)), item)

    sessions = property(lambda self: self)

    def _item(self, image_number: int, index: int) -> UnifiedFlyoutItem | None:
        target = (
            self._store.document.image_list1
            if image_number == 1
            else self._store.document.image_list2
        )
        return target[index] if 0 <= index < len(target) else None


def make_main_window_proxy(host_window, anchor_left, anchor_right):
    """Deprecated shim — prefer ``UnifiedFlyout.set_list_anchors``."""
    flyout = getattr(host_window, "_unified_flyout", None)
    if flyout is not None and hasattr(flyout, "set_list_anchors"):
        flyout.set_list_anchors(anchor_left, anchor_right)
    return host_window


def _coerce(item) -> UnifiedFlyoutItem:
    if isinstance(item, UnifiedFlyoutItem):
        return item
    if isinstance(item, str):
        return UnifiedFlyoutItem(display_name=item)
    if isinstance(item, dict):
        return UnifiedFlyoutItem(**item)
    return UnifiedFlyoutItem(display_name=str(item))
