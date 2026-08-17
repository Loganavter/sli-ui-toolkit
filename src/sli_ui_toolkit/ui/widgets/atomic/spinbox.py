from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QFocusEvent, QIntValidator
from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit, TextAlignment
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin


class SpinBox(WheelScrollPolicyMixin, CustomLineEdit):
    valueChanged = Signal(int)

    def __init__(
        self,
        parent=None,
        default_value: int = 0,
        *,
        alignment: TextAlignment = Qt.AlignmentFlag.AlignCenter,
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
        self.setFixedHeight(scaled_px(32))

        self.editingFinished.connect(self._on_editing_finished)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)
        self._update_style()
        UiScale.get_instance().scale_changed.connect(self.on_scale_changed)

    def on_scale_changed(self, _factor: float) -> None:
        self.setFixedHeight(scaled_px(32))
        self.updateGeometry()
        self.update()

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
        return QSize(self._content_width(), scaled_px(32))

    def minimumSizeHint(self) -> QSize:
        return QSize(self._content_width(), scaled_px(32))

    def _content_width(self) -> int:
        widest = max(
            len(str(self._minimum)),
            len(str(self._maximum)),
            len(str(self._value)),
            len(str(self._default_value)),
            2,
        )
        text_width = self.fontMetrics().horizontalAdvance("8" * widest)
        margins = scaled_px(self.H_PADDING) * 2 + scaled_px(14)
        return max(scaled_px(44), text_width + margins)

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


class DoubleSpinBox(SpinBox):
    """Float-valued variant of :class:`SpinBox` (same painting/layout).

    Design values, `scaled_px`-aware geometry, `singleStep` + optional
    `decimals` for display formatting. ``setValue`` clamps to the range and
    snaps to ``singleStep`` increments, matching SpinBox's stepped semantics.
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        parent=None,
        default_value: float = 0.0,
        *,
        single_step: float = 1.0,
        decimals: int = 2,
        alignment: TextAlignment = Qt.AlignmentFlag.AlignCenter,
        wheel_requires_focus: bool = False,
    ):
        self._single_step = max(0.0, float(single_step))
        self._decimals = max(0, int(decimals))
        super().__init__(
            parent,
            default_value=int(default_value),
            alignment=alignment,
            wheel_requires_focus=wheel_requires_focus,
        )
        self._minimum = 0.0
        self._maximum = 100.0
        self._value = float(default_value)
        self._default_value = float(default_value)

        self.setValidator(QDoubleValidator(-1e9, 1e9, self._decimals, self))
        self.setText(self._format(self._value))
        self._update_content_width()

    def _format(self, value: float) -> str:
        return f"{value:.{self._decimals}f}"

    def setDecimals(self, decimals: int) -> None:
        self._decimals = max(0, int(decimals))
        self.setValidator(QDoubleValidator(-1e9, 1e9, self._decimals, self))
        self.setText(self._format(self._value))
        self._update_content_width()
        self.updateGeometry()

    def setSingleStep(self, step: float) -> None:
        self._single_step = max(0.0, float(step))

    def singleStep(self) -> float:
        return self._single_step

    def setRange(self, min_val: float, max_val: float):  # type: ignore[override]
        self._minimum = float(min_val)
        self._maximum = float(max_val)
        self.setValue(self._value)
        self._update_content_width()
        self.updateGeometry()

    def value(self) -> float:  # type: ignore[override]
        return self._value

    def setValue(self, val: float):  # type: ignore[override]
        clamped = min(max(float(val), self._minimum), self._maximum)
        if self._single_step > 0:
            clamped = round((clamped - self._minimum) / self._single_step) * self._single_step + self._minimum
            clamped = min(max(clamped, self._minimum), self._maximum)
        if abs(clamped - self._value) > 1e-12:
            self._value = clamped
            self.valueChanged.emit(self._value)
        if self.text() != self._format(clamped):
            self.setText(self._format(clamped))
        self.updateGeometry()

    def _content_width(self) -> int:
        widest = max(
            len(self._format(self._minimum)),
            len(self._format(self._maximum)),
            len(self._format(self._value)),
            len(self._format(self._default_value)),
            2,
        )
        text_width = self.fontMetrics().horizontalAdvance("8" * widest)
        margins = scaled_px(self.H_PADDING) * 2 + scaled_px(14)
        return max(scaled_px(44), text_width + margins)

    def _update_content_width(self) -> None:
        self.setMinimumWidth(self.minimumSizeHint().width())

    def _on_editing_finished(self):
        text = self.text().strip()
        try:
            val = float(text) if text else self._default_value
        except ValueError:
            val = self._default_value
        self.setValue(val)

    def wheelEvent(self, event):
        if not self.shouldHandleWheelEvent(event):
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        if delta > 0:
            self.setValue(self._value + self._single_step * factor)
        else:
            self.setValue(self._value - self._single_step * factor)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self.setValue(self._value + self._single_step)
            event.accept()
        elif event.key() == Qt.Key.Key_Down:
            self.setValue(self._value - self._single_step)
            event.accept()
        else:
            super().keyPressEvent(event)

SpinBox.inspect_spec = InspectSpec(
    family="SpinBox",
    state=(
        SpecField("value", "value"),
        SpecField("minimum", "_minimum", private=True),
        SpecField("maximum", "_maximum", private=True),
        SpecField("default_value", "_default_value", private=True),
    ),
    token_family=("dialog.input.background", "input.border.thin", "dialog.text", "accent"),
    docs='docs/user/INPUTS_API.md',
)

DoubleSpinBox.inspect_spec = InspectSpec(
    family="DoubleSpinBox",
    state=(
        SpecField("value", "value"),
        SpecField("minimum", "_minimum", private=True),
        SpecField("maximum", "_maximum", private=True),
        SpecField("single_step", "singleStep"),
        SpecField("decimals", "_decimals", private=True),
    ),
    token_family=("dialog.input.background", "input.border.thin", "dialog.text", "accent"),
    docs='docs/user/INPUTS_API.md',
)