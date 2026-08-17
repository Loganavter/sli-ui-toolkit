"""Flyout families: BaseFlyout and the prebuilt flyouts."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from ..contract import WidgetInspection
from ..extract import from_getters, from_init_kwargs, from_qt_props
from ..registry import register_family

_TOKEN_FAMILY = ("flyout.background", "flyout.border", "shadow.color", "separator.color")


def _make(family: str, match, state_pairs):
    def extract(widget, theme_manager=None) -> WidgetInspection:
        config = from_init_kwargs(widget)
        state = from_getters(widget, state_pairs) + from_qt_props(widget)
        return WidgetInspection(
            family=family, config=config, state=state, token_family=_TOKEN_FAMILY
        )

    register_family(family, match, extract)


_BASE_STATE = (
    ("pinned", lambda w: bool(getattr(w, "pinned", False))),
    ("flyout_group", lambda w: getattr(type(w), "flyout_group", "")),
    ("visible", lambda w: w.isVisible()),
    ("anchor", (lambda w: getattr(w, "_anchor_widget", None)), True),
    ("background_brush", lambda w: getattr(w, "background_brush", lambda: None)()),
    ("border_color", lambda w: getattr(w, "border_color", lambda: None)()),
    ("shadow_color", lambda w: getattr(w, "shadow_color", lambda: None)()),
    ("fade_opacity", (lambda w: getattr(w, "_fade_opacity", None)), True),
)

_make(
    "SimpleOptionsFlyout",
    lambda w: hasattr(w, "populate") and hasattr(w, "rows"),
    _BASE_STATE
    + (
        ("row_count", lambda w: len(w.rows())),
        ("max_visible_items", lambda w: getattr(w, "_max_visible_items", None), True),
    ),
)
_make(
    "IconActionFlyout",
    lambda w: hasattr(w, "set_actions") and hasattr(w, "action_button"),
    _BASE_STATE,
)
_make(
    "IndexedToggleFlyout",
    lambda w: hasattr(w, "set_slots") and hasattr(w, "buttons"),
    _BASE_STATE + (("slot_count", lambda w: len(w.buttons())),),
)
_make(
    "BaseFlyout",
    lambda w: hasattr(w, "show_aligned") and hasattr(w, "add_section"),
    _BASE_STATE,
)
