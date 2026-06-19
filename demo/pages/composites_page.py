"""Composites page — reusable composite widgets."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import CheckBox, CustomGroupBuilder, CustomGroupWidget

from demo.components import GalleryPage


class CompositesPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Composites",
            subtitle="Композитные виджеты для частых паттернов диалогов и форм.",
            source_file=__file__,
            parent=parent,
        )

        try:
            builder = CustomGroupBuilder()
            builder.add(CheckBox("Option A"))
            builder.add(CheckBox("Option B"))
            builder.add(CheckBox("Option C"))
            group = builder.build(title="Group title")
            self.add_card("CustomGroupWidget (via builder)", group)
        except Exception:
            simple_group = CustomGroupWidget()
            self.add_card("CustomGroupWidget", simple_group)

        self.add_stretch()
