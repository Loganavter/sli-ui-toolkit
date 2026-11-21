from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402
from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import QLocale, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QFocusEvent, QIntValidator, QPainter
from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic._step_buttons import StepButtonsMixin
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit, TextAlignment
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


class SpinBox(WheelScrollPolicyMixin, StepButtonsMixin, CustomLineEdit):
    """A compact numeric field, optionally with Qt's ▲/▼ step gutter.

    ``show_step_buttons=True`` gives it the gutter Qt's own ``QSpinBox`` has:
    one narrow column on the right, ▲ above ▼, sharing
    ``StepButtonsMixin``'s hold-to-repeat, pressed overlay and accent wash with
    ``Stepper`` and ``TimeLineEdit`` (measured against the host's Designer
    screenshots: 29 px field, 20 px gutter — both are constructor arguments,
    see ``field_height`` / ``step_button_width``). Off by default: a bare
    ``SpinBox`` keeps the exact geometry and behaviour it always had.
    """

    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar["WidgetDescriptor"]

    valueChanged = Signal(int)

    #: Qt stacks the two arrows in ONE column on the right; the host's stock
    #: control is 29 px tall with a 20 px gutter, so the column takes the whole
    #: `STEP_BUTTON_WIDTH` and each half is ~14 px (the arrow glyph drops to
    #: 10 px so it fits that half instead of being clipped by it).
    STEP_LAYOUT = "vertical"
    STEP_BUTTON_WIDTH = 20
    STEP_ARROW_SIZE = 10

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
        single_step: int = 1,
        show_step_buttons: bool = False,
        step_button_width: int | None = None,
        field_height: int = 32,
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
        self._minimum: int = 0
        self._maximum: int = 100
        self._value: int = default_value
        self._default_value: int = default_value
        self._single_step: int = max(1, int(single_step))
        self._field_height: int = max(1, int(field_height))
        if step_button_width is not None:
            self.STEP_BUTTON_WIDTH = max(1, int(step_button_width))

        self.setValidator(QIntValidator(-999999, 999999, self))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setText(str(default_value))
        self._min_width_explicit = False
        self.setFixedHeight(scaled_px(self._field_height))
        self._init_step_gutter(show_step_buttons)
        self._pin_content_width()

        self.editingFinished.connect(self._on_editing_finished)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)
        self._update_style()
        connect_ui_metrics(self, self.on_scale_changed, axes=frozenset({AXIS_SCALE}))

    def on_scale_changed(self, *_args: object) -> None:
        self.setFixedHeight(scaled_px(self._field_height))
        self._sync_text_margins()
        self._sync_step_buttons()
        self.updateGeometry()
        self.update()

    # -- stepping -----------------------------------------------------------

    def singleStep(self) -> int:
        return self._single_step

    def setSingleStep(self, step: int) -> None:  # noqa: N802 - Qt API
        self._single_step = max(1, int(step))
        self._sync_step_buttons()

    def _step(self, delta: int) -> None:
        self.setValue(self.value() + int(delta) * self._single_step)

    def _step_button_enabled(self, delta: int) -> bool:
        """An arrow is inert once a step can no longer move the value.

        Compared as ``target vs clamped target`` rather than ``value < maximum``
        because ``DoubleSpinBox`` snaps to ``single_step`` grid: at max 10 with
        step 0.3 the top reachable value is 9.9, and `9.9 < 10` would otherwise
        keep ▲ enabled forever with nothing to do.
        """
        if not getattr(self, "_show_step_buttons", False):
            return False
        target = float(self.value()) + int(delta) * float(self.singleStep())
        clamped = max(float(self._minimum), min(float(self._maximum), target))
        return abs(clamped - float(self.value())) > 1e-9

    def _sync_text_margins(self) -> None:
        """Leave exactly ``gutter`` px less room for the text than a bare field."""
        padding = scaled_px(self.H_PADDING)
        self.setTextMargins(padding, 0, padding + self._step_gutter_width(), 0)

    def setRange(self, min_val: int, max_val: int):
        self._minimum = min_val
        self._maximum = max_val
        self.setValue(self._value)
        self._pin_content_width()
        self._sync_step_buttons()
        self.updateGeometry()

    def _pin_content_width(self) -> None:
        """Widen to the value text - unless the HOST stated a minimum.

        A page that says `setMinimumSize(75, 30)` (the Designer's statement) had its width replaced by this control's
        own hint on every `setRange`, so the field rendered 57 px instead of 75 (measured). The explicit flag is the
        same shape as the buttons' `_corner_radius_explicit`.
        """
        if getattr(self, "_min_width_explicit", False):
            return
        super().setMinimumWidth(self.minimumSizeHint().width())

    def setMinimumWidth(self, width: int) -> None:  # noqa: N802 - Qt API
        self._min_width_explicit = True
        super().setMinimumWidth(width)

    def setMinimumSize(self, width, height=None) -> None:  # noqa: N802 - Qt API
        self._min_width_explicit = True
        super().setMinimumSize(width, height) if height is not None else super().setMinimumSize(width)

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        clamped = max(self._minimum, min(self._maximum, int(val)))

        if self._value != clamped:
            self._value = clamped
            self.valueChanged.emit(self._value)

        if self.text() != str(clamped):
            self.setText(str(clamped))
        self._sync_step_buttons()
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), scaled_px(self._field_height))

    def minimumSizeHint(self) -> QSize:
        return QSize(self._content_width(), scaled_px(self._field_height))

    def _content_width(self) -> int:
        widest = max(
            len(str(self._minimum)),
            len(str(self._maximum)),
            len(str(self._value)),
            len(str(self._default_value)),
            2,
        )
        text_width = self.fontMetrics().horizontalAdvance("8" * widest)
        margins = scaled_px(self.H_PADDING) * 2 + scaled_px(14) + self._step_gutter_width()
        return max(scaled_px(44), text_width + margins)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self._paint_step_gutter(painter)
        finally:
            painter.end()

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
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # Up/Down are reserved for routing between controls (row/panel
            # navigation, see NavigationManager/ToolbarRowsSection) -- never
            # value-adjustment here. Leave the event unaccepted (matches
            # Slider.keyPressEvent's identical contract) so it stays
            # available for routing instead of being silently swallowed by
            # a SpinBox sitting inside a ToolbarRowsSection row.
            event.ignore()
            return
        if key == Qt.Key.Key_PageUp:
            # Left/Right are not repurposed for value-stepping here (unlike
            # Slider) -- SpinBox is a text field where Left/Right must stay
            # cursor movement for manual digit editing. PageUp/PageDown are
            # free for keyboard-driven stepping instead.
            self.setValue(self._value + 1)
            event.accept()
        elif key == Qt.Key.Key_PageDown:
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

    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar["WidgetDescriptor"]

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
        show_step_buttons: bool = False,
        step_button_width: int | None = None,
        field_height: int = 32,
    ):
        # Set before super(): the base re-declares this as SpinBox's int step,
        # so the float re-assignment after it (see below) is what sticks.
        self._single_step = max(0.0, float(single_step))  # type: ignore[assignment]
        self._decimals = max(0, int(decimals))
        super().__init__(
            parent,
            default_value=int(default_value),
            alignment=alignment,
            wheel_requires_focus=wheel_requires_focus,
            show_step_buttons=show_step_buttons,
            step_button_width=step_button_width,
            field_height=field_height,
        )
        self._single_step = max(0.0, float(single_step))  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float
        self._minimum = 0.0  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float
        self._maximum = 100.0  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float
        self._value = float(default_value)  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float
        self._default_value = float(default_value)  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float

        self.setValidator(QDoubleValidator(-1e9, 1e9, self._decimals, self))
        self.setText(self._format(self._value))
        self._update_content_width()
        # The gutter was created inside ``SpinBox.__init__``, while
        # ``_single_step`` was still SpinBox's int state; re-evaluate the bound
        # hook now that the float range/step is in place.
        self._sync_step_buttons()

    def _format(self, value: float) -> str:
        """Format through the LOCALE, like Qt's own QDoubleSpinBox does.

        A hardcoded `f"{value:.1f}"` prints `3.5` on a Russian desktop where the stock widget prints `3,5` - a host
        replacing the widget then sees a glyph change on every spin box (measured on the settings page: the text axis,
        not geometry). `setDecimals` still decides how many digits are shown.
        """
        return QLocale().toString(float(value), "f", self._decimals)

    def setDecimals(self, decimals: int) -> None:
        self._decimals = max(0, int(decimals))
        self.setValidator(QDoubleValidator(-1e9, 1e9, self._decimals, self))
        self.setText(self._format(self._value))
        self._update_content_width()
        self.updateGeometry()

    def setSingleStep(self, step: float) -> None:  # type: ignore[override]  # DoubleSpinBox widens SpinBox's int step to float
        self._single_step = max(0.0, float(step))  # type: ignore[assignment]  # see __init__: float state on an int-typed slot
        self._sync_step_buttons()

    def singleStep(self) -> float:  # type: ignore[override]  # DoubleSpinBox widens SpinBox's int step to float
        return self._single_step

    def setRange(self, min_val: float, max_val: float):  # type: ignore[override]
        self._minimum = float(min_val)  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float
        self._maximum = float(max_val)  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float
        self.setValue(self._value)
        self._update_content_width()
        self._sync_step_buttons()
        self.updateGeometry()

    def value(self) -> float:  # type: ignore[override]
        return self._value

    def setValue(self, val: float):  # type: ignore[override]
        clamped = min(max(float(val), self._minimum), self._maximum)
        if self._single_step > 0:
            clamped = round((clamped - self._minimum) / self._single_step) * self._single_step + self._minimum
            clamped = min(max(clamped, self._minimum), self._maximum)
        if abs(clamped - self._value) > 1e-12:
            self._value = clamped  # type: ignore[assignment]  # DoubleSpinBox widens SpinBox int state to float
            self.valueChanged.emit(self._value)
        if self.text() != self._format(clamped):
            self.setText(self._format(clamped))
        self._sync_step_buttons()
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
        margins = scaled_px(self.H_PADDING) * 2 + scaled_px(14) + self._step_gutter_width()
        return max(scaled_px(44), text_width + margins)

    def _update_content_width(self) -> None:
        self._pin_content_width()

    def _on_editing_finished(self):
        text = self.text().strip()
        # The user types what the locale shows (`3,5`), so parse with the same locale and keep a plain `.` accepted.
        parsed, ok = QLocale().toDouble(text) if text else (0.0, False)
        if not ok and text:
            try:
                parsed, ok = float(text), True
            except ValueError:
                ok = False
        val = parsed if ok else self._default_value
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
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # See SpinBox.keyPressEvent -- same routing contract.
            event.ignore()
            return
        if key == Qt.Key.Key_PageUp:
            self.setValue(self._value + self._single_step)
            event.accept()
        elif key == Qt.Key.Key_PageDown:
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
    token_family=("surface.background", "input.border.thin", "dialog.text", "accent"),
    docs='docs/user/INPUTS_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
SpinBox.widget_descriptor = WidgetDescriptor(
    family=SpinBox.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(SpinBox.inspect_spec, 'config', ()),
        state=SpinBox.inspect_spec.state,
        token_family=getattr(SpinBox.inspect_spec, 'token_family', ()),
        regions=getattr(SpinBox.inspect_spec, 'regions', False),
        layers=getattr(SpinBox.inspect_spec, 'layers', False),
        docs=getattr(SpinBox.inspect_spec, 'docs', ''),
    ),
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
    token_family=("surface.background", "input.border.thin", "dialog.text", "accent"),
    docs='docs/user/INPUTS_API.md',
)

DoubleSpinBox.widget_descriptor = WidgetDescriptor(
    family=DoubleSpinBox.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(DoubleSpinBox.inspect_spec, 'config', ()),
        state=DoubleSpinBox.inspect_spec.state,
        token_family=getattr(DoubleSpinBox.inspect_spec, 'token_family', ()),
        regions=getattr(DoubleSpinBox.inspect_spec, 'regions', False),
        layers=getattr(DoubleSpinBox.inspect_spec, 'layers', False),
        docs=getattr(DoubleSpinBox.inspect_spec, 'docs', ''),
    ),
)