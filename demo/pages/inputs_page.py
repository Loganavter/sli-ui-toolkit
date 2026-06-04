"""Basic Inputs page — line edits, spinboxes, sliders, checkboxes, switches, radios."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

from sli_ui_toolkit.widgets import (
    CheckBox,
    CustomLineEdit,
    Label,
    RadioButton,
    Slider,
    SpinBox,
    Switch,
    TimeLineEdit,
)

from demo.components import GalleryPage

_UNDERLINE_GRAY = QColor("#808080")
_FOCUSED_UNDERLINE_ACCENT = QColor("#0078D4")


def _row(*widgets) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    for w in widgets:
        layout.addWidget(w)
    layout.addStretch()
    return holder


class InputsPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Basic Inputs",
            subtitle="Текстовые поля, спинбоксы, слайдеры, чекбоксы, свитчи и радио-кнопки.",
            source_file=__file__,
            parent=parent,
        )

        self.add_section("Text & time")
        le = CustomLineEdit(
            underline_color=_UNDERLINE_GRAY,
            focused_underline_color=_FOCUSED_UNDERLINE_ACCENT,
        )
        le.setPlaceholderText("Type something…")
        self.add_card("CustomLineEdit", le)

        left = CustomLineEdit(
            alignment="left",
            underline_color=_UNDERLINE_GRAY,
            focused_underline_color=_FOCUSED_UNDERLINE_ACCENT,
        )
        left.setText("Left")
        center = CustomLineEdit(
            alignment="center",
            underline_color=_UNDERLINE_GRAY,
            focused_underline_color=_FOCUSED_UNDERLINE_ACCENT,
        )
        center.setText("Center")
        right = CustomLineEdit(
            alignment="right",
            underline_color=_UNDERLINE_GRAY,
            focused_underline_color=_FOCUSED_UNDERLINE_ACCENT,
        )
        right.setText("Right")
        self.add_card("CustomLineEdit alignment", _row(left, center, right))

        tle = TimeLineEdit(
            alignment="center",
            underline_color=_UNDERLINE_GRAY,
            focused_underline_color=_FOCUSED_UNDERLINE_ACCENT,
        )
        self.add_card("TimeLineEdit", tle, "Поле ввода времени.")

        self.add_section("Numeric")
        s1 = SpinBox(
            default_value=42,
            underline_color=_UNDERLINE_GRAY,
            focused_underline_color=_FOCUSED_UNDERLINE_ACCENT,
        )
        s1.setRange(0, 100)
        self.add_card("SpinBox", s1)

        sl = Slider(Qt.Orientation.Horizontal)
        sl.setRange(0, 100)
        sl.setValue(40)
        self.add_card("Slider", sl)

        self.add_section("Booleans")
        self.add_card("CheckBox", CheckBox("Enabled"))

        sw = Switch()
        sw.setChecked(True)
        self.add_card("Switch", _row(Label("On:", pixel_size=11), sw))

        radios = QWidget()
        radio_layout = QHBoxLayout(radios)
        radio_layout.setContentsMargins(0, 0, 0, 0)
        radio_layout.setSpacing(12)
        group = QButtonGroup(radios)
        for i, name in enumerate(("Option A", "Option B", "Option C")):
            rb = RadioButton(name)
            if i == 0:
                rb.setChecked(True)
            group.addButton(rb)
            radio_layout.addWidget(rb)
        self.add_card("RadioButton group", radios)

        self.add_stretch()
