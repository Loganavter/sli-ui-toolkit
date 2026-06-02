"""Miscellaneous widgets demo page."""

from sli_ui_toolkit.widgets import (
    AdaptiveLabel, BodyLabel, CaptionLabel, CompactLabel, GroupTitleLabel,
    ClickableLabel, LoadingSpinner, Button,
)
from demo.pages.base_page import BasePageWidget


class MiscPage(BasePageWidget):
    """Showcase of labels, spinners, toasts, and other widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toast_manager = None

        # Labels
        labels_layout = self.add_section("Labels")
        labels_layout.addWidget(GroupTitleLabel(text="Group Title Label"))
        labels_layout.addWidget(BodyLabel(text="Body Label - Main content text"))
        labels_layout.addWidget(CaptionLabel(text="Caption Label - Secondary text"))
        labels_layout.addWidget(AdaptiveLabel(text="Adaptive Label - Adjusts to theme"))
        labels_layout.addWidget(CompactLabel(text="Compact Label - Space-saving"))
        labels_layout.addWidget(ClickableLabel(text="Clickable Label"))

        # Loading Spinner
        spinner_layout = self.add_section("Loading Spinner")
        spinner = LoadingSpinner()
        spinner.setMinimumHeight(40)

        spinner_control_layout = self.add_section("Spinner Controls")
        start_btn = Button(text="Start", variant="accent")
        stop_btn = Button(text="Stop", variant="surface")

        start_btn.clicked.connect(spinner.start)
        stop_btn.clicked.connect(spinner.stop)

        spinner_layout.addWidget(spinner)
        spinner_control_layout.addWidget(start_btn)
        spinner_control_layout.addWidget(stop_btn)

        # Toast notifications (demo only - actual toasts require ToastManager)
        toast_layout = self.add_section("Toast Notifications")
        toast_label = BodyLabel(text="Toast notifications disabled (requires window context)")
        toast_layout.addWidget(toast_label)

        # Tooltip demo
        tooltip_layout = self.add_section("Tooltip Demo")
        tooltip_label = BodyLabel(text="Hover over buttons for tooltips")
        tooltip_layout.addWidget(tooltip_label)

        btn1 = Button(text="Button A", variant="surface")
        btn1.setToolTip("This is a helpful tooltip for Button A")
        tooltip_layout.addWidget(btn1)

        btn2 = Button(text="Button B", variant="surface")
        btn2.setToolTip("This is a helpful tooltip for Button B with more information")
        tooltip_layout.addWidget(btn2)

        self._content_layout.addStretch()
