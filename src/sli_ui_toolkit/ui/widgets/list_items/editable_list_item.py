from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic import CheckBox, CustomLineEdit
from sli_ui_toolkit.ui.widgets.buttons import Button


class EditableListItem(QWidget):
    delete_clicked = pyqtSignal()

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
        self.checkbox.setMinimumSize(28, 28)
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

    def get_text(self) -> str:
        return self.input_field.text().strip()

    def is_enabled_checked(self) -> bool:
        return self.checkbox.isChecked()

    def get_value_data(self) -> dict:
        return {
            "value": self.get_text(),
            "enabled": self.is_enabled_checked(),
        }
