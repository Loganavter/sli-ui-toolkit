"""A toolkit-painted numeric stepper: a ``SpinBox`` with a visible ▲/▼ gutter.

Why it exists (2026-10-25): ``SpinBox`` is a ``CustomLineEdit`` subclass, so in
a settings row it read as a plain text field — nothing said "this is a number",
and a value could only be changed by typing. The step gauge is the one
``TimeLineEdit`` already had (hold-to-repeat, pressed overlay, accent wash), so
both widgets now share it through :class:`StepButtonsMixin` instead of one
copying the other's paint code.

Since 2026-11-22 the gutter itself lives on ``SpinBox`` (a *vertical* column,
the shape Qt's own ``QSpinBox`` has — ``SpinBox(show_step_buttons=True)``);
``Stepper`` keeps the wide two-button gutter it always had and adds the
stepper-only semantics: a ``step`` size, PageUp/PageDown keys and the wheel.

Keyboard and wheel keep working (PageUp/PageDown and one notch step by
``step``; the value stays clamped to ``setRange``, and ``valueChanged`` is
inherited), but a Stepper is a typed field like its ``SpinBox`` base — so it
takes the SpinBox shape of the value-edit contract: Up/Down stay navigation
keys, and stepping is PageUp/PageDown (``docs/dev/NAVIGATION.md`` §1.1).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent

from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic.spinbox import SpinBox


class Stepper(SpinBox):
    """``SpinBox`` + the wide ▲/▼ gauge, sharing ``TimeLineEdit``'s step mechanics."""

    #: The stepper's gutter stays the wide side-by-side gauge it always had:
    #: two 22 px buttons, not ``SpinBox``'s narrow vertical column.
    STEP_LAYOUT = "horizontal"
    STEP_BUTTON_WIDTH = 22
    STEP_ARROW_SIZE = 22

    def __init__(
        self,
        parent=None,
        default_value: int = 0,
        *,
        step: int = 1,
        show_step_buttons: bool = True,
        **kwargs,
    ):
        super().__init__(
            parent,
            default_value=default_value,
            single_step=max(1, int(step)),
            show_step_buttons=show_step_buttons,
            **kwargs,
        )
        self._pin_content_width()
        self.updateGeometry()
        self.update()

    # -- value --------------------------------------------------------------

    def step(self) -> int:
        return self.singleStep()

    def setStep(self, step: int) -> None:
        self.setSingleStep(max(1, int(step)))

    # -- host hooks ---------------------------------------------------------

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
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # Value-edit contract, SpinBox shape: a Stepper is a typed field,
            # so Up/Down belong to row navigation (NavigationManager /
            # ToolbarRowsSection) and never step the value while idle.
            event.ignore()
            return
        if event.key() == Qt.Key.Key_PageUp:
            self._step(1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_PageDown:
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
