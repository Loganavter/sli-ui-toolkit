"""Timeline family."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from ..contract import WidgetInspection
from ..extract import from_getters, from_init_kwargs, from_qt_props
from ..registry import register_family


def _match(widget: QWidget) -> bool:
    return hasattr(widget, "get_total_duration") and hasattr(widget, "set_data")


def _extract(widget, theme_manager=None) -> WidgetInspection:
    config = from_init_kwargs(widget)
    state = from_getters(
        widget,
        (
            ("fps", (lambda w: getattr(w, "_fps", None)), True),
            ("duration", (lambda w: getattr(w, "_duration", None)), True),
            ("zoom_level", (lambda w: getattr(w, "_zoom_level", None)), True),
            ("visual_index", (lambda w: getattr(w, "_visual_index", None)), True),
            (
                "collapsed_groups",
                (lambda w: sorted(getattr(w, "_collapsed_group_ids", set()) or [])),
                True,
            ),
            ("total_duration", lambda w: w.get_total_duration()),
            ("pixels_per_second", lambda w: w.get_pixels_per_second()),
            ("has_selection", lambda w: w.has_selection()),
            ("has_snapshots", lambda w: w.has_snapshots()),
        ),
    )
    state += from_qt_props(widget)
    return WidgetInspection(
        family="TimelineWidget",
        config=config,
        state=state,
        token_family=(
            "accent",
            "surface.background",
            "AlternateBase",
            "separator.color",
            "dialog.border",
            "WindowText",
        ),
    )


register_family("TimelineWidget", _match, _extract)
