"""Composite Widgets & Dialogs demo page."""

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget
from PyQt6.QtCore import Qt

from sli_ui_toolkit.widgets import (
    Button, DialogActionBar, ScrollableDialogPage, SidebarDialogShell,
    BodyLabel, CaptionLabel, IconListWidget, IconListItem,
)
from demo.pages.base_page import BasePageWidget


class CompositesPage(BasePageWidget):
    """Showcase of composite and dialog widgets."""

    def __init__(self, toast_manager=None, parent=None):
        super().__init__(parent)
        self._toast_manager = toast_manager

        # DialogActionBar
        actionbar_layout = self.add_section("DialogActionBar")
        actionbar = DialogActionBar(
            primary_text="Save",
            secondary_text="Cancel",
        )
        actionbar_layout.addWidget(actionbar)

        # ScrollableDialogPage
        scrollable_layout = self.add_section("ScrollableDialogPage")
        scrollable_page = ScrollableDialogPage()
        label1 = BodyLabel(text="This is inside a ScrollableDialogPage")
        label2 = CaptionLabel(text="Content is scrollable when it exceeds the viewport")
        scrollable_page.content_layout.addWidget(label1)
        scrollable_page.content_layout.addWidget(label2)
        for i in range(5):
            scrollable_page.content_layout.addWidget(CaptionLabel(text=f"Item {i+1}"))
        scrollable_layout.addWidget(scrollable_page)

        # SidebarDialogShell button
        shell_layout = self.add_section("SidebarDialogShell")
        shell_button = Button(text="Open Dialog with Sidebar", variant="accent")
        shell_button.clicked.connect(self._open_sidebar_dialog)
        shell_layout.addWidget(shell_button)

        self._content_layout.addStretch()

    def _open_sidebar_dialog(self):
        """Open a demo dialog with SidebarDialogShell."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Sidebar Dialog Demo")
        dialog.setGeometry(100, 100, 600, 400)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create sidebar shell
        shell = SidebarDialogShell(sidebar_width=150)

        # Create pages
        general_page = QWidget()
        general_layout = QVBoxLayout(general_page)
        general_layout.addWidget(BodyLabel(text="General Settings"))
        general_layout.addWidget(CaptionLabel(text="Configure general options here"))
        general_layout.addStretch()

        advanced_page = QWidget()
        advanced_layout = QVBoxLayout(advanced_page)
        advanced_layout.addWidget(BodyLabel(text="Advanced Settings"))
        advanced_layout.addWidget(CaptionLabel(text="Advanced options for power users"))
        advanced_layout.addStretch()

        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.addWidget(BodyLabel(text="About"))
        about_layout.addWidget(CaptionLabel(text="This is a demo application"))
        about_layout.addStretch()

        # Add pages to stacked widget
        shell.pages_stack.addWidget(general_page)
        shell.pages_stack.addWidget(advanced_page)
        shell.pages_stack.addWidget(about_page)

        # Setup sidebar
        sidebar_items = [
            IconListItem(text="General", icon=None),
            IconListItem(text="Advanced", icon=None),
            IconListItem(text="About", icon=None),
        ]
        shell.sidebar.set_items(sidebar_items)
        shell.sidebar.item_selected.connect(lambda idx: shell.pages_stack.setCurrentIndex(idx))

        # Add shell to dialog
        layout.addWidget(shell)

        # Add action buttons
        button_layout = QHBoxLayout()
        ok_btn = Button(text="OK", variant="accent")
        cancel_btn = Button(text="Cancel", variant="surface")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        dialog.exec()
