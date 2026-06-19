from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFocusEvent, QIntValidator
from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin


class SpinBox(WheelScrollPolicyMixin, CustomLineEdit):
    valueChanged = Signal(int)

    def __init__(
        self,
        parent=None,
        default_value: int = 0,
        *,
        alignment=Qt.AlignmentFlag.AlignCenter,
        wheel_requires_focus: bool = False,
        underline_color: QColor | None = None,
        underline_thickness: float | None = None,
        focused_underline_color: QColor | None = None,
        focused_underline_thickness: float | None = None,
    ):
        super().__init__(
            parent,
            alignment=alignment,
            underline_color=underline_color,
            underline_thickness=underline_thickness,
            focused_underline_color=focused_underline_color,
            focused_underline_thickness=focused_underline_thickness,
        )
        self.init_wheel_scroll_policy(wheel_requires_focus=wheel_requires_focus)
        self._minimum = 0
        self._maximum = 100
        self._value = default_value
        self._default_value = default_value

        self.setValidator(QIntValidator(-999999, 999999, self))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setText(str(default_value))
        self.setMinimumWidth(self.minimumSizeHint().width())
        self.setFixedHeight(32)

        self.editingFinished.connect(self._on_editing_finished)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)
        self._update_style()

    def setRange(self, min_val: int, max_val: int):
        self._minimum = min_val
        self._maximum = max_val
        self.setValue(self._value)
        self.setMinimumWidth(self.minimumSizeHint().width())
        self.updateGeometry()

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        clamped = max(self._minimum, min(self._maximum, int(val)))

        if self._value != clamped:
            self._value = clamped
            self.valueChanged.emit(self._value)

        if self.text() != str(clamped):
            self.setText(str(clamped))
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), 32)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._content_width(), 32)

    def _content_width(self) -> int:
        widest = max(
            len(str(self._minimum)),
            len(str(self._maximum)),
            len(str(self._value)),
            len(str(self._default_value)),
            2,
        )
        text_width = self.fontMetrics().horizontalAdvance("8" * widest)
        margins = self.H_PADDING * 2 + 14
        return max(44, text_width + margins)

    def _on_editing_finished(self):
        text = self.text().strip()
        try:
            val = int(text) if text else self._default_value
        except ValueError:
            val = self._default_value

        self.setValue(val)

    def wheelEvent(self, event):
        if not self.shouldHandleWheelEvent(event):
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1

        if delta > 0:
            self.setValue(self._value + step)
        else:
            self.setValue(self._value - step)

        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self.setValue(self._value + 1)
            event.accept()
        elif event.key() == Qt.Key.Key_Down:
            self.setValue(self._value - 1)
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent):
        QTimer.singleShot(0, self.selectAll)
        super().focusInEvent(event)

    def _update_style(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
