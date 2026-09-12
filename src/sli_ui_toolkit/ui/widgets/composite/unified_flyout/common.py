import logging
from enum import Enum

from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect

logger = logging.getLogger(__name__)

# Back-compat alias for in-package imports.
_RoundedClipEffect = RoundedClipEffect

class FlyoutMode(Enum):
    HIDDEN = 0
    SINGLE_LEFT = 1
    SINGLE_RIGHT = 2
    DOUBLE = 3
    SINGLE_SIMPLE = 4


def items_for_list(document, list_num: int):
    """Items for side ``list_num`` (1|2).

    Prefers neutral ``list1``/``list2``; falls back to host-domain
    ``image_list1``/``image_list2`` (Improve-ImgSLI document shape).
    """
    if list_num == 1:
        items = getattr(document, "list1", None)
        if items is None:
            items = getattr(document, "image_list1", None)
    elif list_num == 2:
        items = getattr(document, "list2", None)
        if items is None:
            items = getattr(document, "image_list2", None)
    else:
        return []
    return items if items is not None else []


def current_index_for_list(document, list_num: int) -> int:
    if list_num == 1:
        return int(getattr(document, "current_index1", -1))
    if list_num == 2:
        return int(getattr(document, "current_index2", -1))
    return -1


def set_items_for_list(document, list_num: int, items) -> None:
    """Write items, preferring neutral ``list1``/``list2`` when present."""
    seq = list(items) if items is not None else []
    if list_num == 1:
        if hasattr(document, "list1"):
            document.list1 = seq
        elif hasattr(document, "image_list1"):
            document.image_list1 = seq
        return
    if list_num == 2:
        if hasattr(document, "list2"):
            document.list2 = seq
        elif hasattr(document, "image_list2"):
            document.image_list2 = seq

