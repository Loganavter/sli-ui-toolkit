"""LongPressCapability — press-and-hold gesture detection."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

from .base import ButtonCapability


class LongPressCapability(ButtonCapability):
    """Enables long-press detection via timer.

    When user presses and holds, emits longPressed signal after delay.
    """

    def __init__(self, delay_ms: int = 600):
        super().__init__()
        self.delay_ms = delay_ms
        self._button = None
        self._lp_timer: QTimer | None = None
        self._lp_triggered = False

    def attach(self, button: QWidget, region_id: str | None = None) -> None:
        super().attach(button, region_id=region_id)
        self._button = button
        self._lp_timer = QTimer(button)
        self._lp_timer.setSingleShot(True)
        self._lp_timer.setInterval(self.delay_ms)
        self._lp_timer.timeout.connect(self._on_long_press)
        self._lp_triggered = False

    def detach(self, button: QWidget) -> None:
        if self._lp_timer:
            self._lp_timer.stop()
            self._lp_timer.deleteLater()
        self._button = None

    def is_enabled(self) -> bool:
        return self._button is not None and self._button.isEnabled()

    def on_press_start(self) -> None:
        """Called when button is pressed down. Start timer."""
        if not self.is_enabled() or not self._lp_timer:
            return
        self._lp_triggered = False
        self._lp_timer.start()

    def on_press_end(self) -> None:
        """Called when button is released. Stop timer."""
        if self._lp_timer:
            self._lp_timer.stop()
        self._lp_triggered = False

    def was_long_pressed(self) -> bool:
        """Check if this release was a long-press (prevents double-signal)."""
        return self._lp_triggered

    def _on_long_press(self):
        if self._button is None:
            return
        pressed_region = getattr(self._button, "_pressed_region", None)
        if hasattr(self._button, '_pressed') and self._button._pressed:
            if self._region_id is not None and pressed_region not in (None, self._region_id):
                return
            self._lp_triggered = True
            if hasattr(self._button, "regionLongPressed") and self._region_id is not None:
                self._button.regionLongPressed.emit(self._region_id)
            if hasattr(self._button, 'longPressed'):
                if self._region_id in (None, "_main"):
                    self._button.longPressed.emit()
