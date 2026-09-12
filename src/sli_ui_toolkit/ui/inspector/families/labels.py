"""Label family (Label + DropZoneLabel)."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from ..contract import WidgetInspection
from ..extract import (
    from_dataclass,
    from_getters,
    from_init_kwargs,
    from_qt_props,
)
from ..registry import register_family


def _match(widget: QWidget) -> bool:
    if not isinstance(widget, QWidget):
        return False
    return hasattr(widget, "get_original_text") and hasattr(widget, "variant")


def _extract(widget, theme_manager=None) -> WidgetInspection:
    config = from_init_kwargs(widget)
    label_config = getattr(widget, "_config", None)
    if label_config is None:
        label_config = getattr(widget, "_spec", None)
    config += from_dataclass(label_config, label="config")
    state = from_getters(
        widget,
        (
            ("text", lambda: getattr(widget, "get_original_text", lambda: "")()),
            ("variant", lambda w: w.variant()),
            ("marquee", lambda w: w.marquee()),
        ),
    )
    state += from_qt_props(widget)
    token_family = ("dialog.text",)
    color_token = getattr(widget, "_color_token_override", None)
    if color_token:
        token_family = (color_token,)
    return WidgetInspection(
        family="Label",
        config=config,
        state=state,
        token_family=token_family,
    )


register_family("Label", _match, _extract)
