"""Buttons & Controls demo page."""

from PyQt6.QtWidgets import QButtonGroup
from sli_ui_toolkit.widgets import Button, ButtonGroup
from demo.pages.base_page import BasePageWidget


class ButtonsPage(BasePageWidget):
    """Showcase of Button widget variants and features."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Variants
        variants_layout = self.add_section("Button Variants")
        for variant in ["default", "accent", "delete", "primary", "surface", "ghost", "subtle"]:
            btn = Button(text=variant.capitalize(), variant=variant)
            variants_layout.addWidget(btn)

        # States
        states_layout = self.add_section("Button States")
        toggle_btn = Button(text="Toggle Off", toggle=True)
        toggle_btn.toggled.connect(lambda checked: toggle_btn.setText("Toggle On" if checked else "Toggle Off"))
        states_layout.addWidget(toggle_btn)

        disabled_btn = Button(text="Disabled Button", variant="surface")
        disabled_btn.setEnabled(False)
        states_layout.addWidget(disabled_btn)

        # Text + Icon combinations
        self.add_section("Text & Icon")
        text_only = Button(text="Text Only", variant="surface")
        icon_only = Button()  # Empty button
        text_and_icon = Button(text="With Icon", variant="accent")
        icon_layout = self.add_section("Icons")
        icon_layout.addWidget(text_only)
        icon_layout.addWidget(icon_only)
        icon_layout.addWidget(text_and_icon)

        # Scrollable
        scroll_layout = self.add_section("Scrollable (Mouse Wheel)")
        scroll_btn = Button(text="Scroll: 0-100", scrollable=(0, 100), variant="surface")
        scroll_btn.valueChanged.connect(lambda v: scroll_btn.setText(f"Scroll: {v}"))
        scroll_layout.addWidget(scroll_btn)

        # Long press
        longpress_layout = self.add_section("Long Press")
        longpress_btn = Button(text="Hold me!", variant="delete")
        longpress_btn.longPressed.connect(lambda: print("Long press detected!"))
        longpress_layout.addWidget(longpress_btn)

        # Badge
        badge_layout = self.add_section("Badge")
        badge_btn = Button(text="Notification", badge="3", variant="accent")
        badge_layout.addWidget(badge_btn)

        # Menu
        menu_layout = self.add_section("Menu Button")
        menu_btn = Button(
            text="Options",
            menu=[
                ("Option A", "a"),
                ("Option B", "b"),
                ("Option C", "c"),
            ],
            variant="surface"
        )
        menu_btn.menuTriggered.connect(lambda action: print(f"Selected: {action}"))
        menu_layout.addWidget(menu_btn)

        # ButtonGroup
        group_layout = self.add_section("Button Group")
        btn_a = Button(text="A")
        btn_b = Button(text="B")
        btn_c = Button(text="C")
        button_group = ButtonGroup([btn_a, btn_b, btn_c], label="View Mode")
        group_layout.addWidget(button_group)

        # Underline
        underline_layout = self.add_section("Underline")
        underline_btn = Button(
            text="Colored",
            show_underline=True,
            toggle=True,
            variant="default"
        )
        underline_layout.addWidget(underline_btn)

        self._content_layout.addStretch()
