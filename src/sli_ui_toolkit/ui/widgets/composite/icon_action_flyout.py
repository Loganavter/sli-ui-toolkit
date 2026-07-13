from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QEvent, QEasingCurve, QSize, Signal
from PySide6.QtWidgets import QHBoxLayout

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.managers import AnchoredFlyoutAutoHide
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

@dataclass(slots=True)
class IconAction:
    action_id: str
    icon: object = None
    tooltip: str = ""
    visible: bool = True
    enabled: bool = True

class IconActionFlyout(BaseFlyout):
    actionTriggered = Signal(str)
    elementHovered = Signal(str)
    elementHoverEnded = Signal()

    def __init__(
        self,
        parent=None,
        *,
        actions: Iterable[IconAction] | None = None,
        button_size: int = 28,
        icon_size: int = 18,
    ):
        super().__init__(parent)
        self._hovered_element = None
        self._anchor_button = None
        self._button_size = int(button_size)
        self._icon_size = int(icon_size)
        self._actions: dict[str, IconAction] = {}
        self._buttons: dict[str, Button] = {}

        self._auto_hide = AnchoredFlyoutAutoHide(
            flyout=self,
            anchor_getter=lambda: self._anchor_button,
            parent=self,
        )

        self.h_layout = QHBoxLayout()
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(6)
        self.content_layout.addLayout(self.h_layout)

        self.set_actions(actions or [])

    def set_actions(self, actions: Iterable[IconAction]) -> None:
        for button in self._buttons.values():
            button.removeEventFilter(self)
            self.h_layout.removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        self._actions.clear()

        for action in actions:
            spec = action if isinstance(action, IconAction) else IconAction(**action)
            button = Button(spec.icon, parent=self.container)
            button.setFixedSize(self._button_size, self._button_size)
            button.setIconSize(QSize(self._icon_size, self._icon_size))
            button.setToolTip(spec.tooltip)
            button.setVisible(spec.visible)
            button.setEnabled(spec.enabled)
            button.clicked.connect(
                lambda _checked=False, action_id=spec.action_id: self._trigger_action(action_id)
            )
            button.installEventFilter(self)
            button.setProperty("element_name", spec.action_id)
            self.h_layout.addWidget(button)
            self._actions[spec.action_id] = spec
            self._buttons[spec.action_id] = button

        self.update_state()

    def action_button(self, action_id: str) -> Button | None:
        return self._buttons.get(action_id)

    def set_action_state(
        self,
        action_id: str,
        *,
        icon: object | None = None,
        tooltip: str | None = None,
        visible: bool | None = None,
        enabled: bool | None = None,
    ) -> None:
        button = self._buttons.get(action_id)
        spec = self._actions.get(action_id)
        if button is None or spec is None:
            return

        if icon is not None:
            spec.icon = icon
            button._icon = icon
            button.setIcon(resolve_icon(icon))
        if tooltip is not None:
            spec.tooltip = tooltip
            button.setToolTip(tooltip)
        if visible is not None:
            spec.visible = bool(visible)
            button.setVisible(spec.visible)
        if enabled is not None:
            spec.enabled = bool(enabled)
            button.setEnabled(spec.enabled)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            element_name = obj.property("element_name")
            if element_name and element_name != self._hovered_element:
                self._hovered_element = element_name
                self.elementHovered.emit(element_name)
        elif event.type() == QEvent.Type.Leave:
            if self._hovered_element:
                self._hovered_element = None
                self.elementHoverEnded.emit()

        return super().eventFilter(obj, event)

    def update_state(self):
        self.h_layout.invalidate()
        self.h_layout.activate()
        self.container.updateGeometry()
        self.updateGeometry()
        self.adjustSize()

    def _trigger_action(self, action_id: str) -> None:
        self.actionTriggered.emit(action_id)
        self.hide()

    def show_above(self, anchor):
        self.update_state()
        if self.isVisible() and self._anchor_button is anchor:
            self.hide()
            return
        self._anchor_button = anchor
        self.show_aligned(anchor, "top-center", "bottom-center")

    def show_aligned(
        self,
        anchor_widget,
        anchor_point="top-center",
        flyout_point="bottom-center",
        *,
        position: str | None = None,
        offset=5,
        animation: str = "none",
        animation_duration_ms: int | None = None,
        animation_distance: int = 24,
        easing: QEasingCurve.Type = QEasingCurve.Type.OutQuad,
        toggle: bool = True,
    ):
        # ``toggle`` guards the click-to-open/close behaviour used by
        # show_above(). Callers that reposition an already-visible flyout in
        # response to unrelated state changes (e.g. hover/store updates) must
        # pass toggle=False, otherwise this would hide the flyout instead of
        # just moving it.
        if toggle and self.isVisible() and self._anchor_button is anchor_widget:
            self.hide()
            return
        self._anchor_button = anchor_widget
        super().show_aligned(
            anchor_widget,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            position=position,
            offset=offset,
            animation=animation,
            animation_duration_ms=animation_duration_ms,
            animation_distance=animation_distance,
            easing=easing,
        )

    def schedule_auto_hide(self, ms: int):
        self._auto_hide.schedule(ms)

    def cancel_auto_hide(self):
        auto_hide = getattr(self, "_auto_hide", None)
        if auto_hide is not None:
            auto_hide.cancel()

    def hide(self):
        self.cancel_auto_hide()
        super().hide()
