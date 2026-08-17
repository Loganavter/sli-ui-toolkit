"""Process-wide UI scale factor for toolkit chrome.

Mirrors ``ThemeManager`` (color) and ``UiFont`` (typeface): a singleton
holding one number — the logical-px multiplier applied to fonts, icons,
tokens, and widget geometry. It is independent of the OS/Qt display scale
factor (``devicePixelRatio`` stays at the render/pixmap boundary only).

Live-apply contract: consumers read the factor through ``scaled_px()``
(or ``UiFont.resolve`` / style-bridge defaults, which already multiply)
and subscribe to ``scale_changed`` to relayout/repaint. Widgets that want
the same auto-subscription idiom as ``ThemedWidget`` can connect
``UiScale.get_instance().scale_changed`` to ``updateGeometry``+``update``.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QObject, Signal

#: Hard safety clamp for ``set_factor``. The app-side settings UI restricts
#: the user to 0.75–2.0; this wider clamp only guards against nonsense values.
MIN_FACTOR = 0.5
MAX_FACTOR = 2.5


class UiScale(QObject):
    """Process-wide UI scale factor resolver for toolkit widgets."""

    scale_changed = Signal(float)

    _instance: Optional["UiScale"] = None

    def __init__(self) -> None:
        super().__init__()
        self._factor = 1.0

    @classmethod
    def get_instance(cls) -> "UiScale":
        if cls._instance is None:
            cls._instance = UiScale()
        return cls._instance

    def factor(self) -> float:
        return self._factor

    def set_factor(self, value: float) -> None:
        """Set the scale factor, clamped to [MIN_FACTOR, MAX_FACTOR].

        Emits ``scale_changed`` only when the clamped value actually
        changed, so subscribers are not re-entered for no-ops.
        """
        try:
            new_factor = float(value)
        except (TypeError, ValueError):
            return
        if math.isnan(new_factor) or math.isinf(new_factor):
            return
        new_factor = min(MAX_FACTOR, max(MIN_FACTOR, new_factor))
        if new_factor == self._factor:
            return
        self._factor = new_factor
        self.scale_changed.emit(self._factor)

    def scaled_px(self, value: int | float) -> int:
        """Multiply *value* by the factor, rounding to whole px (min 1)."""
        return max(1, int(round(float(value) * self._factor)))


def scaled_px(value: int | float) -> int:
    """Convenience entry point: ``UiScale.get_instance().scaled_px(value)``."""
    return UiScale.get_instance().scaled_px(value)


__all__ = [
    "MAX_FACTOR",
    "MIN_FACTOR",
    "UiScale",
    "scaled_px",
]
