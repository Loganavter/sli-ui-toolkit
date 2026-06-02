"""ScrollCapability — wheel-based value manipulation with visual feedback."""

from PyQt6.QtCore import QPoint, QSize, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QWidget
from PyQt6.QtCore import Qt

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from .base import ButtonCapability


class ScrollCapability(ButtonCapability):
    """Enables scroll wheel value adjustment with popup feedback.

    Handles:
    - wheelEvent dispatch
    - scroll value increment/decrement with toggle mode (0 = "off")
    - scroll end timeout (hides popup, clears scrolling state)
    - value popup display
    """

    def __init__(self, min_value: int = 0, max_value: int = 10):
        self.min_value = min_value
        self.max_value = max_value
        self._button = None
        self._scroll_end_timer: QTimer | None = None
        self._value_popup: QLabel | None = None
        self._popup_controller = None

    def attach(self, button: QWidget) -> None:
        self._button = button
        self._scroll_end_timer = QTimer(button)
        self._scroll_end_timer.setSingleShot(True)
        self._scroll_end_timer.setInterval(800)
        self._scroll_end_timer.timeout.connect(self._on_scroll_ended)

        # Try to get popup controller if available
        if hasattr(button, '_popup_controller'):
            self._popup_controller = button._popup_controller

    def detach(self, button: QWidget) -> None:
        if self._scroll_end_timer:
            self._scroll_end_timer.stop()
            self._scroll_end_timer.deleteLater()
        if self._value_popup:
            self._value_popup.hide()
            self._value_popup.deleteLater()
        self._button = None

    def is_enabled(self) -> bool:
        return self._button is not None and self._button.isEnabled()

    def handle_wheel_event(self, event) -> bool:
        """Handle wheel event. Return True if consumed, False to pass through."""
        if not self.is_enabled():
            return False
        if not hasattr(self._button, '_has_scroll') or not self._button._has_scroll:
            return False

        delta = event.angleDelta().y()
        if delta == 0:
            return False

        self._button._is_scrolling = True
        if self._scroll_end_timer:
            self._scroll_end_timer.start()

        # Toggle+scroll mode: toggle between value and 0
        if hasattr(self._button, '_has_toggle') and self._button._has_toggle:
            if self._button._checked:
                restored = self._button._saved_value if self._button._saved_value and self._button._saved_value > 0 else 1
                self._button._saved_value = None
                step = 1 if delta > 0 else -1
                new_val = max(self._button._scroll_min if self._button._scroll_min > 0 else 1,
                             min(self._button._scroll_max, restored + step))
                self._button._scroll_value = new_val
                self._button._checked = False
                self._button.valueChanged.emit(new_val)
                self._button.update()
                self._show_scroll_popup(new_val)
                event.accept()
                return True

        step = 1 if delta > 0 else -1
        old_value = self._button._scroll_value
        new_val = max(self._button._scroll_min, min(self._button._scroll_max, self._button._scroll_value + step))

        # Check toggle boundary (0 = "off" state)
        if hasattr(self._button, '_has_toggle') and self._button._has_toggle:
            if old_value > 0 and new_val == 0:
                self._button._saved_value = old_value
                self._button._scroll_value = 0
                self._button._checked = True
                self._button.valueChanged.emit(0)
                self._button.update()
                self._show_scroll_popup(0)
                event.accept()
                return True

        if new_val != self._button._scroll_value:
            self._button._scroll_value = new_val
            self._button.valueChanged.emit(new_val)
            self._button.update()
        self._show_scroll_popup(new_val)
        event.accept()
        return True

    def _on_scroll_ended(self):
        if self._button is None:
            return
        self._button._is_scrolling = False
        self._hide_scroll_popup()
        self._button.update()

    def _show_scroll_popup(self, val: int):
        if self._button is None or not self._button.isVisible():
            return

        if val == 0:
            pixmap = resolve_icon(get_named_icon("divider_hidden")).pixmap(18, 18)
            popup_text = ""
            popup_size = QSize(32, 28)
        else:
            pixmap = None
            popup_text = str(val)
            popup_size = QSize(32 if val >= 10 else 26, 28)

        popup_id = f"button:{id(self._button)}"
        if self._popup_controller is not None:
            self._popup_controller.show_popup(
                popup_id, self._button,
                text=popup_text, pixmap=pixmap,
                size=popup_size, position="top",
                offset=6,
                timeout_ms=self._scroll_end_timer.interval() if self._scroll_end_timer else 800,
            )
            return

        if self._value_popup is None:
            self._value_popup = QLabel(parent=self._button.window())
            self._value_popup.setObjectName("ValuePopupLabel")
            self._value_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if pixmap is not None:
            self._value_popup.setPixmap(pixmap)
            self._value_popup.setText("")
        else:
            self._value_popup.setPixmap(QPixmap())
            self._value_popup.setText(popup_text)
        self._value_popup.setFixedSize(popup_size)

        window = self._button.window()
        pos = self._button.mapToGlobal(QPoint(0, 0))
        local_pos = window.mapFromGlobal(pos) if window is not None else pos
        popup_x = local_pos.x() + (self._button.width() - self._value_popup.width()) // 2
        popup_y = local_pos.y() - self._value_popup.height() - 6
        self._value_popup.move(popup_x, popup_y)

        if not self._value_popup.isVisible():
            self._value_popup.show()
        self._value_popup.raise_()

    def _hide_scroll_popup(self):
        popup_id = f"button:{id(self._button)}"
        if self._popup_controller is not None:
            self._popup_controller.hide_popup(popup_id)
        if self._value_popup:
            self._value_popup.hide()
