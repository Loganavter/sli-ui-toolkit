from PySide6.QtCore import QSize, Qt, QTime
from PySide6.QtGui import QColor, QKeyEvent, QPainter
from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.ui.widgets.atomic._step_buttons import StepButtonsMixin
from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit, TextAlignment
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin


class TimeLineEdit(StepButtonsMixin, WheelScrollPolicyMixin, CustomLineEdit):
    """Toolkit-painted HH:mm input with the shared ▲/▼ step gauge."""

    def __init__(
        self,
        initial_time: str = "00:05",
        parent=None,
        *,
        alignment: TextAlignment = Qt.AlignmentFlag.AlignCenter,
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
        self._last_valid_text = "00:05"
        self._init_step_gutter(show_step_buttons)
        self.setText(initial_time)
        self.editingFinished.connect(self._normalize_or_restore)

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), 32)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._content_width(), 32)

    def setText(self, text: str | None):
        normalized = self._normalize_text(text or "")
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self._paint_step_gutter(painter)
        finally:
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

    # -- StepButtonsMixin host hooks ---------------------------------------

    def _step(self, delta: int) -> None:
        self._step_minutes(delta)

    def _start_step_hold(self, delta: int) -> None:
        """The gauge focuses the field on press; the shared mixin does not."""
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super()._start_step_hold(delta)

    def _sync_text_margins(self) -> None:
        self.setTextMargins(
            self.H_PADDING,
            self.V_PADDING,
            self.H_PADDING + self._step_gutter_width(),
            self.V_PADDING,
        )

    def _content_width(self) -> int:
        text_width = self.fontMetrics().horizontalAdvance("00:00")
        return max(96, text_width + self.H_PADDING * 2 + self._step_gutter_width() + 8)

    # -- step / text --------------------------------------------------------

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
