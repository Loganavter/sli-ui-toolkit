"""GalleryPage — scrollable container that hosts ExampleCard widgets per page.

Uses OverlayScrollArea from the toolkit instead of raw QScrollArea.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import Label, OverlayScrollArea

from demo.components.example_card import ExampleCard


class GalleryPage(OverlayScrollArea):
    def __init__(
        self,
        title: str,
        subtitle: str | None = None,
        source_file: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_file = source_file
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        self.setWidget(container)
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(28, 24, 28, 24)
        self._layout.setSpacing(20)

        header = Label(title, pixel_size=22, bold=True)
        self._layout.addWidget(header)

        if subtitle:
            sub = Label(subtitle, pixel_size=12)
            sub.setWordWrap(True)
            self._layout.addWidget(sub)

        self._layout.addSpacing(6)

    def add_section(self, title: str) -> None:
        section = Label(title, pixel_size=15, bold=True)
        self._layout.addSpacing(6)
        self._layout.addWidget(section)

    def add_card(
        self,
        title: str,
        widget: QWidget,
        description: str | None = None,
        source_file: str | None = None,
    ) -> ExampleCard:
        card = ExampleCard(
            title=title,
            widget=widget,
            source_file=source_file or self._source_file,
            description=description,
        )
        self._layout.addWidget(card)
        return card

    def add_stretch(self) -> None:
        self._layout.addStretch(1)
