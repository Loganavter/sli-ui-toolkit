"""Labels & Text page."""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import DropZoneLabel, Label

from demo.components import GalleryPage


def _stack(*widgets) -> QWidget:
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    for w in widgets:
        layout.addWidget(w)
    return holder


class LabelsPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Labels & Text",
            subtitle="Label-варианты, обрезание, drop-zone.",
            source_file=__file__,
            parent=parent,
        )

        self.add_card(
            "Label sizes",
            _stack(
                Label("Title — 18 bold", pixel_size=18, bold=True),
                Label("Header — 14 bold", pixel_size=14, bold=True),
                Label("Body — 12", pixel_size=12),
                Label("Caption — 11", pixel_size=11),
                Label("Mono — 10", pixel_size=10),
            ),
        )

        self.add_card(
            "Selectable",
            Label("Этот текст можно выделить мышью.", pixel_size=12, selectable=True),
        )

        dz = DropZoneLabel("Drop files here")
        dz.setMinimumSize(280, 80)
        self.add_card("DropZoneLabel", dz, "Цель для drag&drop файлов/контента.")

        self.add_stretch()
