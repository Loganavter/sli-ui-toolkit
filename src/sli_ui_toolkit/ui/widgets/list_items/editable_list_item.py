from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.ui_metrics import (
    AXIS_FONT,
    AXIS_SCALE,
    connect_ui_metrics,
)
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic import CheckBox, CustomLineEdit
from sli_ui_toolkit.ui.widgets.buttons import Button

#: Design-px floor for the row checkbox (the CheckBox paints its own scaled
#: indicator); resolved at USE time and re-derived on the appearance bus.
_DESIGN_CHECKBOX_MIN = 28


class EditableListItem(QWidget):
    delete_clicked = Signal()

    def __init__(
        self,
        text: str = "",
        *,
        enabled: bool = True,
        placeholder: str = "",
        checkbox_tooltip: str = "",
        delete_icon: Any = "delete",
        delete_tooltip: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.input_field = CustomLineEdit()
        self.input_field.setText(text)
        if placeholder:
            self.input_field.setPlaceholderText(placeholder)
        layout.addWidget(self.input_field, 1)

        self.checkbox = CheckBox("")
        self.checkbox.setChecked(enabled)
        self.checkbox.setMinimumSize(
            scaled_px(_DESIGN_CHECKBOX_MIN), scaled_px(_DESIGN_CHECKBOX_MIN)
        )
        if checkbox_tooltip:
            self.checkbox.setToolTip(checkbox_tooltip)
        layout.addWidget(self.checkbox)

        self.delete_btn = Button(
            icon=delete_icon,
            size=(28, 28),
            icon_size=16,
            variant="surface",
            parent=self,
        )
        if delete_tooltip:
            self.delete_btn.setToolTip(delete_tooltip)
        self.delete_btn.clicked.connect(self.delete_clicked.emit)
        layout.addWidget(self.delete_btn)

        connect_ui_metrics(
            self,
            self._on_ui_metrics_changed,
            axes=frozenset({AXIS_FONT, AXIS_SCALE}),
        )

    def _on_ui_metrics_changed(self, *_args: object) -> None:
        """Re-derive the checkbox floor for the live factor (appearance bus)."""
        size = scaled_px(_DESIGN_CHECKBOX_MIN)
        self.checkbox.setMinimumSize(size, size)
        self.checkbox.updateGeometry()
        self.updateGeometry()
        self.update()

    def get_text(self) -> str:
        return self.input_field.text().strip()

    def is_enabled_checked(self) -> bool:
        return self.checkbox.isChecked()

    def get_value_data(self) -> dict:
        return {
            "value": self.get_text(),
            "enabled": self.is_enabled_checked(),
        }
