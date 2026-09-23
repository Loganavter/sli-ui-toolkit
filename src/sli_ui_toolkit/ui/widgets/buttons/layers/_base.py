"""Layer ABC — общий интерфейс для всех слоёв painter pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext


class Layer(ABC):
    scope: Literal["region", "widget"] = "region"

    def applies(self, ctx: DrawContext) -> bool:
        return True

    @abstractmethod
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None: ...


def outline_width(widget: Any) -> float:
    """Outline width from the ``borderWidth`` dynamic property (default 1.0).

    Shared by ``BackgroundLayer`` (plain buttons) and ``BorderLayer``
    (region-composed buttons): ``setProperty("borderWidth", 2)`` gives a 2px
    leader edge, anything missing/invalid falls back to a 1px hairline.
    """
    try:
        raw = widget.property("borderWidth")
    except Exception:
        return 1.0
    try:
        width = float(raw) if raw is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    return width if width >= 1.0 else 1.0
