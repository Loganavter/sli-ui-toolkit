"""The step-button gutter shared by toolkit inputs that take a number.

``TimeLineEdit`` grew this first (▲/▼ on the right, hold-to-repeat, a pressed
overlay); a numeric stepper needs exactly the same affordance. Keeping the
geometry, the repeat timers and the painting in one place is what stops the
next numeric control from being a bare text field — the complaint that started
this (2026-10-25: the AI settings page showed ``SpinBox`` rows that read as
plain line edits, with no way to step a value by mouse).

A host widget mixes this in and implements two hooks:

* ``_step(delta)`` — apply one step (``+1`` up, ``-1`` down);
* ``_step_gutter_width()`` — how much horizontal room the text must leave.

The host keeps ownership of its own text/validation; this module only owns the
buttons, their layout, the repeat behaviour and the gutter paint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.context import DrawContext
from sli_ui_toolkit.ui.widgets.buttons.layers import ContentLayer, RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState


class StepButtonOverlayLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        return ButtonState.HOVERED in ctx.states or ButtonState.PRESSED in ctx.states

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        color = QColor(tm.get_color("accent"))
        color.setAlpha(36 if ButtonState.PRESSED in ctx.states else 22)
        rect = ctx.rect.adjusted(0.0, 0.0, 0.0, -2.0)
        ctx.painter.setPen(Qt.PenStyle.NoPen)
        ctx.painter.setBrush(color)
        ctx.painter.drawRect(rect)


class StepButton(Button):
    """A step arrow: it must never forward its press to the host line edit."""

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        event.accept()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        event.accept()


if TYPE_CHECKING:
    # The mixin is only ever combined with a ``QWidget`` subclass (TimeLineEdit,
    # StepButtons hosts), so the type checker must see that base: without it every
    # ``self.height()`` / ``QTimer(self)`` / ``parent=self`` reads as a misuse of a
    # bare object. At runtime the base stays ``object`` so the MRO of a host is
    # unchanged (``class Host(StepButtonsMixin, CustomLineEdit)``).
    class _StepMixinBase(QWidget):
        #: Host-provided: re-derive the text margins after the gutter moves.
        def _sync_text_margins(self) -> None: ...
else:
    _StepMixinBase = object


class StepButtonsMixin(_StepMixinBase):
    STEP_BUTTON_WIDTH = 22
    STEP_BUTTON_GAP = 0
    STEP_BUTTON_OVERLAP = 1
    STEP_ARROW_SIZE = 22
    REPEAT_START_DELAY_MS = 350
    REPEAT_INTERVAL_MS = 70

    # -- host hooks ---------------------------------------------------------

    def _step(self, delta: int) -> None:  # pragma: no cover - host implements
        raise NotImplementedError

    def _step_gutter_width(self) -> int:
        if not getattr(self, "_show_step_buttons", False):
            return 0
        return self.STEP_BUTTON_WIDTH * 2 + self.STEP_BUTTON_GAP

    # -- lifecycle ----------------------------------------------------------

    def _init_step_gutter(self, visible: bool) -> None:
        self._show_step_buttons = bool(visible)
        self._step_repeat_delta = 0
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

    def setStepButtonsVisible(self, visible: bool) -> None:
        self._show_step_buttons = bool(visible)
        if not self._show_step_buttons:
            self.unsetCursor()
            self._stop_repeat()
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

    # -- geometry -----------------------------------------------------------

    def _up_button_rect(self) -> QRect:
        height = max(1, self.height())
        right = self.width()
        left = right - self.STEP_BUTTON_WIDTH * 2 - self.STEP_BUTTON_GAP
        return QRect(left, 0, self.STEP_BUTTON_WIDTH + self.STEP_BUTTON_OVERLAP, height)

    def _down_button_rect(self) -> QRect:
        height = max(1, self.height())
        right = self.width()
        return QRect(right - self.STEP_BUTTON_WIDTH, 0, self.STEP_BUTTON_WIDTH, height)

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_step_buttons()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        if getattr(self, "_up_button", None) is not None:
            self._sync_step_buttons()

    # -- painting -----------------------------------------------------------

    def _paint_step_gutter(self, painter: QPainter) -> None:
        if not self._show_step_buttons:
            return
        theme_manager = getattr(self, "theme_manager", None) or ThemeManager.get_instance()
        button_area = self._button_area_rect()
        bg = QColor(theme_manager.get_color("accent"))
        bg.setAlpha(22 if self.isEnabled() else 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRect(button_area)

        divider = QColor(theme_manager.get_color("input.border.thin"))
        divider.setAlpha(max(32, int(divider.alpha() * 0.75)))
        painter.setPen(QPen(divider, 0.66))
        painter.drawLine(button_area.left(), 4, button_area.left(), self.height() - 5)
        painter.drawLine(
            self._down_button_rect().left(),
            4,
            self._down_button_rect().left(),
            self.height() - 5,
        )

    # -- buttons / repeat ---------------------------------------------------

    def _create_step_button(self, text: str, delta: int) -> Button:
        button = StepButton(
            text=text,
            variant="ghost",
            size=(self.STEP_BUTTON_WIDTH, self.height() or 32),
            corner_radius=0,
            layers=[StepButtonOverlayLayer(), RippleLayer(), ContentLayer()],
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

    def _start_step_hold(self, delta: int) -> None:
        self._step(delta)
        self._step_repeat_delta = delta
        self._repeat_start_timer.start()

    def _start_repeat_timer(self) -> None:
        if self._step_repeat_delta:
            self._repeat_timer.start()

    def _repeat_step(self) -> None:
        if self._step_repeat_delta:
            self._step(self._step_repeat_delta)

    def _stop_repeat(self) -> None:
        self._step_repeat_delta = 0
        self._repeat_start_timer.stop()
        self._repeat_timer.stop()

    # -- events -------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj in {getattr(self, "_up_button", None), getattr(self, "_down_button", None)} and event.type() in {
            QEvent.Type.Leave,
            QEvent.Type.MouseButtonRelease,
        }:
            self._stop_repeat()
        return super().eventFilter(obj, event)
