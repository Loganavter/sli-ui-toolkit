"""Base class for button capabilities."""

from abc import ABC, abstractmethod
from PyQt6.QtWidgets import QWidget


class ButtonCapability(ABC):
    """Abstract base for composable button behaviors.

    Each capability handles one concern (scroll, long-press, menu, etc.) and is
    independent of other capabilities. Button attaches capabilities and dispatches
    events to them via handle_* methods.
    """

    @abstractmethod
    def attach(self, button: QWidget) -> None:
        """Called when capability is attached to a button. Set up timers, signals, etc."""
        pass

    @abstractmethod
    def detach(self, button: QWidget) -> None:
        """Called when capability is detached. Clean up timers, signals, etc."""
        pass

    def is_enabled(self) -> bool:
        """Whether this capability should respond to events. Override in subclasses."""
        return True
