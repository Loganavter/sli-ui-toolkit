"""Lists & Items page."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.list_items import EditableListItem
from sli_ui_toolkit.widgets import IconListItem, IconListWidget, Label

from demo.components import GalleryPage


class ListsPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Lists & Items",
            subtitle="Списки и одиночные элементы списка.",
            source_file=__file__,
            parent=parent,
        )

        list_host = QWidget()
        list_layout = QVBoxLayout(list_host)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        lw = IconListWidget(icon_size=QSize(24, 24), row_height=40)
        lw.setIconSize(QSize(24, 24))
        lw.set_items([
            IconListItem(text=f"Asset folder {i}", icon="folder_open", data=f"/project/assets/{i}")
            for i in range(1, 16)
        ])
        lw.enable_minimal_scrollbar()
        lw.setFixedSize(320, 220)
        lw.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        list_status = Label("Selected path: -", pixel_size=11)
        lw.currentItemChanged.connect(
            lambda item, _prev: list_status.setText(
                f"Selected path: {item.data(Qt.ItemDataRole.UserRole)}" if item else "Selected path: -"
            )
        )
        lw.setCurrentRow(0)
        list_layout.addWidget(lw)
        list_layout.addWidget(list_status)
        self.add_card(
            "IconListWidget",
            list_host,
            "Обычный список строк с иконками, data payload и MinimalistScrollBar.",
        )

        nav_host = QWidget()
        nav_layout = QHBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(12)
        nav = IconListWidget()
        nav.setIconSize(QSize(20, 20))
        nav.setSelectedIconMode("replace")
        nav.set_items([
            IconListItem("Home", ("photo", "chart")),
            IconListItem("Library", ("folder_open", "download")),
            IconListItem("Settings", ("settings", "sync")),
            IconListItem("About", ("help", "incognito")),
        ])
        nav.enable_minimal_scrollbar()
        nav.setFixedSize(220, 220)
        stack = QStackedWidget()
        stack.setMinimumSize(220, 160)
        for title in ("Home dashboard", "Library browser", "Settings form", "About page"):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.addWidget(Label(title, pixel_size=14, bold=True))
            page_layout.addWidget(Label("Страница меняется через currentRowChanged.", pixel_size=11))
            page_layout.addStretch()
            stack.addWidget(page)
        nav.currentRowChanged.connect(stack.setCurrentIndex)
        nav.setCurrentRow(0)
        nav_layout.addWidget(nav)
        nav_layout.addWidget(stack, 1)
        self.add_card("IconListWidget driving QStackedWidget", nav_host, "Навигационный паттерн: IconListWidget управляет QStackedWidget.")

        item_host = QWidget()
        item_layout = QVBoxLayout(item_host)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(4)
        edit_status = Label("Enabled items: 3", pixel_size=11)

        def update_edit_status() -> None:
            rows = item_host.findChildren(EditableListItem)
            enabled_count = sum(1 for row in rows if row.is_enabled_checked())
            edit_status.setText(f"Enabled items: {enabled_count}")

        def add_editable_row(text: str) -> None:
            item = EditableListItem(
                text=text,
                checkbox_tooltip="Enable this item",
                delete_tooltip="Delete row",
            )
            item.delete_clicked.connect(lambda item=item: (item.setParent(None), item.deleteLater(), update_edit_status()))
            item.checkbox.toggled.connect(update_edit_status)
            item.input_field.textChanged.connect(lambda _text, item=item: edit_status.setText(f"Edited: {item.get_text()}"))
            item_layout.addWidget(item)

        for text in ("Draft note", "Saved checklist", "Recipe ideas"):
            add_editable_row(text)
        item_layout.addWidget(edit_status)
        self.add_card("EditableListItem", item_host, "Редактирование текста, checkbox state и delete signal подключены.")

        self.add_stretch()
