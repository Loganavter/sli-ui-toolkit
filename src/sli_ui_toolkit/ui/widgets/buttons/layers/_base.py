"""Layer ABC — общий интерфейс для всех слоёв painter pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext


class Layer(ABC):
    scope: Literal["region", "widget"] = "region"

    def applies(self, ctx: DrawContext) -> bool:
        return True

    @abstractmethod
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None: ...
