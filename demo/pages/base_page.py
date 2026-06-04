"""Base page widget for demo pages."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from sli_ui_toolkit.widgets import Label, OverlayScrollArea


class BasePageWidget(QWidget):
    """Reusable page base with scrollable content and section helpers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Scroll area with content widget
        self._scroll = OverlayScrollArea()
        self._scroll.setWidgetResizable(True)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(20, 20, 20, 20)
        self._content_layout.setSpacing(20)

        self._scroll.setWidget(self._content)
        self._layout.addWidget(self._scroll)

    def add_section(self, title: str) -> QVBoxLayout:
        """Add a named section with a title and return its layout for adding widgets."""
        section_title = Label(title, pixel_size=13, bold=True)
        self._content_layout.addWidget(section_title)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(0, 8, 0, 0)
        section_layout.setSpacing(12)

        self._content_layout.addLayout(section_layout)
        return section_layout
