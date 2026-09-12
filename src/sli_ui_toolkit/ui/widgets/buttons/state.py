"""Button state — единый StateSet, единственный источник истины о визуальном состоянии."""

from __future__ import annotations

from enum import Enum, auto


class ButtonState(Enum):
    HOVERED = auto()
    PRESSED = auto()
    CHECKED = auto()
    DISABLED = auto()
    FOCUSED = auto()


StateSet = frozenset[ButtonState]
