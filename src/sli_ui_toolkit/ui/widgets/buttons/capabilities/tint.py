"""TintCapability — dynamic overlay tinting via callback.

Used by CalendarDayButton to apply weekend/data-availability colors without paintEvent override.
"""

from typing import Callable
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget

from .base import ButtonCapability


class TintCapability(ButtonCapability):
    """Applies computed color overlay to button based on compute function.

    Usage:
        def compute_tint(ctx: ButtonDrawContext) -> QColor | None:
            if is_weekend:
                return QColor(0, 0, 255, 50)  # light blue overlay
            return None

        button.attach_capability(TintCapability(compute_tint))

    The tint is rendered by the painter in the context object.
    """

    def __init__(self, compute_fn: Callable | None = None):
        """
        Args:
            compute_fn: Function(ctx: ButtonDrawContext) -> QColor | None
                       Returns color to overlay, or None for no tint.
        """
        self.compute_fn = compute_fn
        self._button = None

    def attach(self, button: QWidget) -> None:
        self._button = button

    def detach(self, button: QWidget) -> None:
        self._button = None

    def is_enabled(self) -> bool:
        return self._button is not None and self.compute_fn is not None

    def compute_tint(self) -> QColor | None:
        """Compute the tint color for current button state."""
        if not self.is_enabled():
            return None
        # Note: When ButtonDrawContext is available, call compute_fn with it
        # For now, return None (placeholder)
        return None
