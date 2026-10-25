"""A toolkit-painted numeric stepper: a ``SpinBox`` with a visible ▲/▼ gutter.

Why it exists (2026-10-25): ``SpinBox`` is a ``CustomLineEdit`` subclass, so in
a settings row it read as a plain text field — nothing said "this is a number",
and a value could only be changed by typing. The step gauge is the one
``TimeLineEdit`` already had (hold-to-repeat, pressed overlay, accent wash), so
both widgets now share it through :class:`StepButtonsMixin` instead of one
copying the other's paint code.

Keyboard and wheel keep working (Up/Down and one notch step by ``step``), the
value stays clamped to ``setRange``, and ``valueChanged`` is inherited.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QWheelEvent

from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic._step_buttons import StepButtonsMixin
from sli_ui_toolkit.ui.widgets.atomic.spinbox import SpinBox


class Stepper(StepButtonsMixin, SpinBox):
    """``SpinBox`` + the ▲/▼ gauge, sharing ``TimeLineEdit``'s step mechanics."""

    def __init__(
        self,
        parent=None,
        default_value: int = 0,
        *,
        step: int = 1,
        show_step_buttons: bool = True,
        **kwargs,
    ):
        super().__init__(parent, default_value=default_value, **kwargs)
        self._step_size = max(1, int(step))
        self._init_step_gutter(show_step_buttons)
        self.setMinimumWidth(self.minimumSizeHint().width())
        self.updateGeometry()
        self.update()

    # -- value --------------------------------------------------------------

    def step(self) -> int:
        return self._step_size

    def setStep(self, step: int) -> None:
        self._step_size = max(1, int(step))

    # -- host hooks ---------------------------------------------------------

    def _step(self, delta: int) -> None:
        self.setValue(self.value() + int(delta) * self._step_size)

    def _sync_text_margins(self) -> None:
        gutter = self._step_gutter_width()
        self.setTextMargins(self.H_PADDING, 0, gutter + 6 if gutter else self.H_PADDING, 0)

    def _content_width(self) -> int:
        digits = self.fontMetrics().horizontalAdvance(str(self._maximum)) + scaled_px(12)
        return max(72, digits + self.H_PADDING * 2 + self._step_gutter_width() + 8)

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), self.height() or 32)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._content_width(), self.height() or 32)

    # -- events -------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            self._step(1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down:
            self._step(-1)
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        handler = getattr(self, "shouldHandleWheelEvent", None)
        if callable(handler) and not handler(event):
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self._step(1 if delta > 0 else -1)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            self._paint_step_gutter(painter)
        finally:
            painter.end()

    def on_scale_changed(self, *_args: object) -> None:
        super().on_scale_changed(*_args)
        self._sync_text_margins()
        self._sync_step_buttons()
