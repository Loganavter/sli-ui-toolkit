"""Input Widgets demo page."""

from PyQt6.QtWidgets import QButtonGroup
from sli_ui_toolkit.widgets import (
    CustomLineEdit, ComboBox, FluentComboBox, ScrollableComboBox,
    SpinBox, FluentSpinBox, Slider, FluentSlider,
    Switch, FluentSwitch, CheckBox, FluentCheckBox,
    RadioButton, FluentRadioButton, DropZoneLabel,
    InstancesCounterButton, TimeLineEdit,
)
from demo.pages.base_page import BasePageWidget


class InputsPage(BasePageWidget):
    """Showcase of input widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Text input
        text_layout = self.add_section("Text Input")
        line_edit = CustomLineEdit()
        line_edit.setPlaceholderText("Type something...")
        text_layout.addWidget(line_edit)

        time_edit = TimeLineEdit()
        text_layout.addWidget(time_edit)

        # Selection - ComboBox
        combo_layout = self.add_section("ComboBox")
        combo = ComboBox()
        combo.addItems(["Option 1", "Option 2", "Option 3", "Option 4"])
        combo_layout.addWidget(combo)

        fluent_combo = FluentComboBox()
        fluent_combo.addItems(["Fluent A", "Fluent B", "Fluent C"])
        combo_layout.addWidget(fluent_combo)

        scroll_combo = ScrollableComboBox()
        for i in range(20):
            scroll_combo.addItem(f"Item {i}")
        combo_layout.addWidget(scroll_combo)

        # Numeric - SpinBox
        spinbox_layout = self.add_section("SpinBox & Slider")
        spinbox = SpinBox()
        spinbox.setValue(50)
        spinbox_layout.addWidget(spinbox)

        fluent_spinbox = FluentSpinBox()
        fluent_spinbox.setValue(50)
        spinbox_layout.addWidget(fluent_spinbox)

        slider = Slider()
        slider.setValue(50)
        spinbox_layout.addWidget(slider)

        fluent_slider = FluentSlider()
        fluent_slider.setValue(50)
        spinbox_layout.addWidget(fluent_slider)

        # Toggle controls - Switch
        toggle_layout = self.add_section("Toggle Controls")
        switch = Switch()
        toggle_layout.addWidget(switch)

        fluent_switch = FluentSwitch()
        toggle_layout.addWidget(fluent_switch)

        # CheckBox
        check1 = CheckBox("Standard Checkbox")
        check2 = FluentCheckBox("Fluent Checkbox")
        toggle_layout.addWidget(check1)
        toggle_layout.addWidget(check2)

        # RadioButton
        radio_group = QButtonGroup()
        radio1 = RadioButton("Option A")
        radio2 = RadioButton("Option B")
        radio3 = RadioButton("Option C")
        radio1.setChecked(True)
        radio_group.addButton(radio1)
        radio_group.addButton(radio2)
        radio_group.addButton(radio3)

        for radio in [radio1, radio2, radio3]:
            toggle_layout.addWidget(radio)

        fluent_radio_group = QButtonGroup()
        f_radio1 = FluentRadioButton("Fluent A")
        f_radio2 = FluentRadioButton("Fluent B")
        f_radio1.setChecked(True)
        fluent_radio_group.addButton(f_radio1)
        fluent_radio_group.addButton(f_radio2)

        for radio in [f_radio1, f_radio2]:
            toggle_layout.addWidget(radio)

        # Misc - DropZoneLabel
        misc_layout = self.add_section("Misc Input Widgets")
        dropzone = DropZoneLabel("Drop files here")
        misc_layout.addWidget(dropzone)

        counter = InstancesCounterButton()
        misc_layout.addWidget(counter)

        self._content_layout.addStretch()
