"""Navigation families: IconListWidget (sidebar nav), ListPanel,
AdaptiveTabStrip / TopTabBar / TopTabHost."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from ..contract import WidgetInspection
from ..extract import from_getters, from_init_kwargs, from_qt_props
from ..registry import register_family


def _make(family: str, match, state_pairs, token_family):
    def extract(widget, theme_manager=None) -> WidgetInspection:
        config = from_init_kwargs(widget)
        state = from_getters(widget, state_pairs) + from_qt_props(widget)
        return WidgetInspection(
            family=family, config=config, state=state, token_family=token_family
        )

    register_family(family, match, extract)


_NAVLIST_STATE = (
    ("count", lambda w: w.count()),
    ("current_row", lambda w: w.currentRow()),
    ("selected_icon_mode", "selectedIconMode"),
    ("rows", lambda w: [item.text for item in (w.item(i) for i in range(w.count()))]),
)
_make(
    "IconListWidget",
    lambda w: hasattr(w, "row_button") and hasattr(w, "currentRow"),
    _NAVLIST_STATE,
    (
        "list_item.background.normal",
        "list_item.background.hover",
        "list_item.background.selected",
        "list_item.icon.selected",
        "accent",
    ),
)

_LISTPANEL_STATE = (
    ("list_num", lambda w: getattr(w, "list_num", None)),
    ("item_height", lambda w: getattr(w, "item_height", None)),
    ("list_type", (lambda w: getattr(w, "_list_type", None)), True),
    ("selected_indices", (lambda w: sorted(getattr(w, "_selected_indices", set()) or [])), True),
    ("drop_indicator_y", lambda w: getattr(w, "drop_indicator_y", None)),
    ("max_visible_items", lambda w: getattr(w, "MAX_VISIBLE_ITEMS", None)),
)
_make(
    "ListPanel",
    lambda w: hasattr(w, "clear_and_rebuild") and hasattr(w, "list_num"),
    _LISTPANEL_STATE,
    ("surface.background", "flyout.border", "accent"),
)

_TAB_STRIP_STATE = (
    ("count", lambda w: w.count()),
    ("current_index", lambda w: w.currentIndex()),
)
_TAB_STRIP_TOKENS = (
    "surface.list",
    "Window",
    "separator.color",
    "button.toggle.background.hover",
    "WindowText",
)
_make(
    "AdaptiveTabStrip",
    lambda w: hasattr(w, "tab_bar") and hasattr(w, "add_button"),
    _TAB_STRIP_STATE,
    _TAB_STRIP_TOKENS,
)
_make(
    "TopTabBar",
    lambda w: hasattr(w, "setTabData") and hasattr(w, "currentChanged") and not hasattr(w, "add_button"),
    _TAB_STRIP_STATE,
    ("accent",),
)
