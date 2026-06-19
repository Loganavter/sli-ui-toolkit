"""Deprecated directional choice helper.

Use ``TopLevelInWindowOverlay`` directly for new overlays.
"""

from __future__ import annotations

import warnings

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.overlays.in_window_overlay import (
    OverlaySlot,
    TopLevelInWindowOverlay,
)


class ChoiceOverlay(TopLevelInWindowOverlay):
    """Deprecated directional button choice helper."""

    chosen = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        parent: QWidget,
        *,
        anchor: QWidget | None = None,
        button_size: int = 120,
        cancel_size: int = 60,
        spacing: int = 20,
        corner_radius: int = 10,
    ):
        warnings.warn(
            "ChoiceOverlay is deprecated. Use TopLevelInWindowOverlay with "
            "Button or other child widgets instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        offset = button_size // 2 + spacing + cancel_size // 2
        super().__init__(parent, anchor=anchor, default_distance=offset)
        self._button_size = button_size
        self._cancel_size = cancel_size
        self._corner_radius = corner_radius
        self._choice_buttons: dict[str, Button] = {}
        self._cancel_button: Button | None = None
        self.dismissed.connect(self.cancelled.emit)

    def add_choice(
        self,
        key: str,
        *,
        slot: OverlaySlot,
        label: str = "",
        icon=None,
    ) -> Button:
        btn = Button(
            icon=icon,
            text=label,
            size=(self._button_size, self._button_size),
            corner_radius=self._corner_radius,
            variant="surface",
        )
        btn.clicked.connect(lambda k=key: self._on_chosen(k))
        self._choice_buttons[key] = btn
        self.add_widget(btn, key=key, slot=slot)
        return btn

    def set_cancel(self, *, enabled: bool = True, icon=None) -> Button | None:
        if self._cancel_button is not None:
            self.remove_widget(self._cancel_button)
            self._cancel_button.deleteLater()
            self._cancel_button = None
        if not enabled:
            return None
        btn = Button(
            icon=icon,
            text="" if icon else "x",
            size=(self._cancel_size, self._cancel_size),
            corner_radius=self._cancel_size // 2,
            variant="ghost",
        )
        btn.clicked.connect(self._on_cancel)
        self._cancel_button = btn
        self.add_widget(btn, key="cancel", slot=OverlaySlot.CENTER, distance=0)
        return btn

    def buttons(self) -> dict[str, Button]:
        return dict(self._choice_buttons)

    def show_modal(self) -> None:
        self.show_overlay()

    def _on_chosen(self, key: str) -> None:
        self.chosen.emit(key)
        self.dismiss(emit_signal=False)

    def _on_cancel(self) -> None:
        self.cancelled.emit()
        self.dismiss(emit_signal=False)


def __getattr__(name: str):
    if name == "ChoiceSlot":
        warnings.warn(
            "ChoiceSlot is deprecated. Use OverlaySlot instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return OverlaySlot
    raise AttributeError(name)
