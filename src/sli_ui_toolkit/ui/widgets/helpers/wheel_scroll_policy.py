from PySide6.QtCore import Qt


class WheelScrollPolicyMixin:
    """Shared wheel-scroll focus policy for custom scrollable widgets."""

    def init_wheel_scroll_policy(self, *, wheel_requires_focus: bool = False) -> None:
        self._wheel_requires_focus = bool(wheel_requires_focus)

    def setWheelRequiresFocus(self, required: bool) -> None:
        self._wheel_requires_focus = bool(required)

    def wheelRequiresFocus(self) -> bool:
        return bool(getattr(self, "_wheel_requires_focus", False))

    def set_wheel_requires_focus(self, required: bool) -> None:
        self.setWheelRequiresFocus(required)

    def wheel_requires_focus(self) -> bool:
        return self.wheelRequiresFocus()

    def shouldHandleWheelEvent(self, event) -> bool:
        if self.wheelRequiresFocus() and not self.hasFocus():
            event.ignore()
            return False
        if not self.wheelRequiresFocus():
            self._focus_from_wheel()
        return True

    def should_handle_wheel_event(self, event) -> bool:
        return self.shouldHandleWheelEvent(event)

    def _focus_from_wheel(self) -> None:
        if self.hasFocus():
            return
        try:
            if not self.isEnabled() or self.focusPolicy() == Qt.FocusPolicy.NoFocus:
                return
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        except RuntimeError:
            return
