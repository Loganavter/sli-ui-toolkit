"""Base class for button capabilities."""

from abc import ABC, abstractmethod
from PySide6.QtWidgets import QWidget


class ButtonCapability(ABC):
    """Abstract base for composable button behaviors.

    Each capability handles one concern (scroll, long-press, menu, etc.) and is
    independent of other capabilities. Button attaches capabilities and dispatches
    events to them via handle_* methods.
    """

    def __init__(self) -> None:
        self._region_id: str | None = None

    @abstractmethod
    def attach(self, button: QWidget, region_id: str | None = None) -> None:
        """Called when capability is attached to a button. Set up timers, signals, etc."""
        self._region_id = region_id or "_main"

    @abstractmethod
    def detach(self, button: QWidget) -> None:
        """Called when capability is detached. Clean up timers, signals, etc."""
        pass

    def is_enabled(self) -> bool:
        """Whether this capability should respond to events. Override in subclasses."""
        return True

    def handle_wheel_event(self, event) -> bool:
        """Optional hook: handle a wheel event routed to this capability's region.

        Override and return True to consume the event. The default no-op lets
        capabilities that don't care about wheel input (long-press, menu, ...)
        ignore it without special-casing in Button's event dispatch.
        """
        return False
