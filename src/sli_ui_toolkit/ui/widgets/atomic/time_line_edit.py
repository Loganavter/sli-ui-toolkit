from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTime, QTimer
from PySide6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
from sli_ui_toolkit.ui.widgets.buttons.layers import ContentLayer, RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.theme import ThemeManager


class _StepButtonOverlayLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        return ButtonState.HOVERED in ctx.states or ButtonState.PRESSED in ctx.states

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        color = QColor(tm.get_color("accent"))
        color.setAlpha(36 if ButtonState.PRESSED in ctx.states else 22)
        rect = ctx.rect.adjusted(0.0, 0.0, 0.0, -2.0)
        ctx.painter.setPen(Qt.PenStyle.NoPen)
        ctx.painter.setBrush(color)
        ctx.painter.drawRect(rect)


class _TimeLineStepButton(Button):
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        event.accept()


class TimeLineEdit(WheelScrollPolicyMixin, CustomLineEdit):
    """Toolkit-painted HH:mm input without native QTimeEdit chrome."""

    STEP_BUTTON_WIDTH = 22
    STEP_BUTTON_GAP = 0
    STEP_BUTTON_OVERLAP = 1
    STEP_ARROW_SIZE = 22
    REPEAT_START_DELAY_MS = 350
    REPEAT_INTERVAL_MS = 70

    def __init__(
        self,
        initial_time: str = "00:05",
        parent=None,
        *,
        alignment=Qt.AlignmentFlag.AlignCenter,
        show_step_buttons: bool = True,
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
        self.setObjectName("TimeLineEdit")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setPlaceholderText("HH:mm")
        self.setMaxLength(5)
        self._show_step_buttons = show_step_buttons
        self._last_valid_text = "00:05"
        self._active_step_delta = 0
        self._repeat_start_timer = QTimer(self)
        self._repeat_start_timer.setSingleShot(True)
        self._repeat_start_timer.setInterval(self.REPEAT_START_DELAY_MS)
        self._repeat_start_timer.timeout.connect(self._start_repeat_timer)
        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(self.REPEAT_INTERVAL_MS)
        self._repeat_timer.timeout.connect(self._repeat_step)
        self._up_button = self._create_step_button("▲", 1)
        self._down_button = self._create_step_button("▼", -1)
        self._sync_text_margins()
        self._sync_step_buttons()
        self.setText(initial_time)
        self.editingFinished.connect(self._normalize_or_restore)

    def setStepButtonsVisible(self, visible: bool) -> None:
        self._show_step_buttons = bool(visible)
        if not self._show_step_buttons:
            self.unsetCursor()
        self._sync_text_margins()
        self._sync_step_buttons()
        self.updateGeometry()
        self.update()

    def stepButtonsVisible(self) -> bool:
        return self._show_step_buttons

    def set_step_buttons_visible(self, visible: bool) -> None:
        self.setStepButtonsVisible(visible)

    def step_buttons_visible(self) -> bool:
        return self.stepButtonsVisible()

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), 32)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._content_width(), 32)

    def setText(self, text: str):
        normalized = self._normalize_text(text)
        if normalized is None:
            normalized = self._last_valid_text
        self._last_valid_text = normalized
        super().setText(normalized)

    def time(self) -> QTime:
        return QTime.fromString(self.text(), "HH:mm")

    def setTime(self, time_obj: QTime):
        if time_obj.isValid():
            self.setText(time_obj.toString("HH:mm"))

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._show_step_buttons:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        button_area = self._button_area_rect()
        bg = QColor(self.theme_manager.get_color("accent"))
        bg.setAlpha(22 if self.isEnabled() else 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRect(button_area)

        divider = QColor(self.theme_manager.get_color("input.border.thin"))
        divider.setAlpha(max(32, int(divider.alpha() * 0.75)))
        painter.setPen(QPen(divider, 0.66))
        painter.drawLine(button_area.left(), 4, button_area.left(), self.height() - 5)
        painter.drawLine(
            self._down_button_rect().left(),
            4,
            self._down_button_rect().left(),
            self.height() - 5,
        )
        painter.end()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            self._step_minutes(1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down:
            self._step_minutes(-1)
            event.accept()
            return
        text = event.text()
        if text and text.isdigit():
            self._insert_digit(text)
            event.accept()
            return
        if text == ":":
            self._insert_colon()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_step_buttons()

    def eventFilter(self, obj, event):
        if obj in {self._up_button, self._down_button} and event.type() in {
            QEvent.Type.Leave,
            QEvent.Type.MouseButtonRelease,
        }:
            self._stop_repeat()
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        if not self.shouldHandleWheelEvent(event):
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        self._step_minutes(1 if delta > 0 else -1)
        event.accept()

    def focusOutEvent(self, event):
        self._stop_repeat()
        self._normalize_or_restore()
        super().focusOutEvent(event)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._sync_step_buttons()

    def _create_step_button(self, text: str, delta: int) -> Button:
        button = _TimeLineStepButton(
            text=text,
            variant="ghost",
            size=(self.STEP_BUTTON_WIDTH, self.height() or 32),
            corner_radius=0,
            layers=[_StepButtonOverlayLayer(), RippleLayer(), ContentLayer()],
            parent=self,
        )
        button.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        button.setAutoFillBackground(False)
        font = QFont(button.font())
        font.setPixelSize(self.STEP_ARROW_SIZE)
        button.setFont(font)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.pressed.connect(lambda d=delta: self._start_step_hold(d))
        button.released.connect(self._stop_repeat)
        button.installEventFilter(self)
        return button

    def _insert_digit(self, digit: str) -> None:
        selected = self.selectedText()
        current = self.text()
        cursor = self.cursorPosition()
        if selected:
            start = self.selectionStart()
            current = current[:start] + current[start + len(selected):]
            cursor = start
        proposed = current[:cursor] + digit + current[cursor:]
        self._apply_edit_candidate(proposed, cursor + 1)

    def _insert_colon(self) -> None:
        current = self.text()
        if ":" in current:
            return
        cursor = self.cursorPosition()
        proposed = current[:cursor] + ":" + current[cursor:]
        self._apply_edit_candidate(proposed, cursor + 1)

    def _apply_edit_candidate(self, proposed: str, cursor: int) -> None:
        proposed = proposed[:5]
        if self._is_intermediate(proposed):
            super().setText(proposed)
            self.setCursorPosition(min(cursor, len(proposed)))

    def _normalize_or_restore(self) -> None:
        normalized = self._normalize_text(self.text())
        if normalized is None:
            normalized = self._last_valid_text
        self._last_valid_text = normalized
        if self.text() != normalized:
            super().setText(normalized)

    def _step_minutes(self, delta: int) -> None:
        normalized = self._normalize_text(self.text()) or self._last_valid_text
        time_obj = QTime.fromString(normalized, "HH:mm")
        if not time_obj.isValid():
            time_obj = QTime(0, 0)
        self.setText(time_obj.addSecs(delta * 60).toString("HH:mm"))

    def _start_step_hold(self, delta: int) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._active_step_delta = delta
        self._step_minutes(delta)
        self._repeat_start_timer.start()

    def _start_repeat_timer(self) -> None:
        if self._active_step_delta:
            self._repeat_timer.start()

    def _repeat_step(self) -> None:
        if self._active_step_delta:
            self._step_minutes(self._active_step_delta)

    def _stop_repeat(self) -> None:
        self._repeat_start_timer.stop()
        self._repeat_timer.stop()
        self._active_step_delta = 0

    def _sync_text_margins(self) -> None:
        step_margin = (
            self.STEP_BUTTON_WIDTH * 2 + self.STEP_BUTTON_GAP
            if self._show_step_buttons
            else 0
        )
        self.setTextMargins(
            self.H_PADDING,
            self.V_PADDING,
            self.H_PADDING + step_margin,
            self.V_PADDING,
        )

    def _content_width(self) -> int:
        text_width = self.fontMetrics().horizontalAdvance("00:00")
        step_buttons = (
            self.STEP_BUTTON_WIDTH * 2 + self.STEP_BUTTON_GAP
            if self._show_step_buttons
            else 0
        )
        return max(96, text_width + self.H_PADDING * 2 + step_buttons + 8)

    def _up_button_rect(self) -> QRect:
        height = max(1, self.height())
        right = self.width()
        left = right - self.STEP_BUTTON_WIDTH * 2 - self.STEP_BUTTON_GAP
        return QRect(left, 0, self.STEP_BUTTON_WIDTH + self.STEP_BUTTON_OVERLAP, height)

    def _down_button_rect(self) -> QRect:
        height = max(1, self.height())
        right = self.width()
        return QRect(
            right - self.STEP_BUTTON_WIDTH,
            0,
            self.STEP_BUTTON_WIDTH,
            height,
        )

    def _button_area_rect(self) -> QRect:
        left = self._up_button_rect().left()
        return QRect(left, 1, max(1, self.width() - left - 1), max(1, self.height() - 2))

    def _sync_step_buttons(self) -> None:
        for button in (self._up_button, self._down_button):
            button.setVisible(self._show_step_buttons)
            button.setEnabled(self.isEnabled() and self._show_step_buttons)
        if self._show_step_buttons:
            up_rect = self._up_button_rect()
            down_rect = self._down_button_rect()
            self._up_button.setFixedSize(up_rect.size())
            self._down_button.setFixedSize(down_rect.size())
            self._up_button.setGeometry(up_rect)
            self._down_button.setGeometry(down_rect)

    def _normalize_text(self, text: str) -> str | None:
        raw = str(text or "").strip()
        if not raw:
            return self._last_valid_text
        if ":" in raw:
            parts = raw.split(":", 1)
            if not parts[0].isdigit() or not parts[1].isdigit():
                return None
            hour = int(parts[0])
            minute = int(parts[1])
        else:
            if not raw.isdigit():
                return None
            padded = raw.zfill(4)[-4:]
            hour = int(padded[:2])
            minute = int(padded[2:])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return f"{hour:02d}:{minute:02d}"

    def _is_intermediate(self, text: str) -> bool:
        if not text:
            return True
        if text.count(":") > 1:
            return False
        if ":" in text:
            hour, minute = text.split(":", 1)
            return (
                len(hour) <= 2
                and len(minute) <= 2
                and (not hour or hour.isdigit())
                and (not minute or minute.isdigit())
            )
        return len(text) <= 4 and text.isdigit()
