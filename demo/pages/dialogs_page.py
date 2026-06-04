"""Dialogs page — modal dialogs triggered by buttons."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.widgets import (
    Button,
    CheckBox,
    ComboBox,
    CustomLineEdit,
    IconListItem,
    Label,
    MarkdownHelpDialog,
    MarkdownHelpSection,
    ScrollableDialogPage,
    SidebarDialogShell,
)

from demo.components import GalleryPage


class DialogsPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Dialogs",
            subtitle="Готовые шаблоны диалоговых окон.",
            source_file=__file__,
            parent=parent,
        )

        markdown_btn = Button(text="Open Markdown Help", variant="surface")
        markdown_btn.clicked.connect(self._open_markdown_help)
        self.add_card("MarkdownHelpDialog", markdown_btn, "Документация: markdown, секции, TOC, anchors и links.")

        shell_btn = Button(text="Open Sidebar Dialog", variant="surface")
        shell_btn.clicked.connect(self._open_sidebar_dialog)
        self.add_card("SidebarDialogShell", shell_btn, "Каркас: sidebar + QStackedWidget для собственных форм.")

        self.add_stretch()

    def _open_markdown_help(self) -> None:
        sections = (
            MarkdownHelpSection(
                order=1,
                slug="quick-start",
                title="Quick Start",
                body_md=(
                    "# Quick Start\n\n"
                    "MarkdownHelpDialog принимает секции и сам строит левую навигацию.\n\n"
                    "### Create sections\n\n"
                    "- Заголовки получают anchors\n"
                    "- Списки рендерятся через markdown\n"
                    "- Внутренние ссылки могут вести на `help://advanced#events`\n\n"
                    "### Jump example\n\n"
                    "[Open events section](help://advanced#events)"
                ),
            ),
            MarkdownHelpSection(
                order=2,
                slug="advanced",
                title="Advanced",
                body_md=(
                    "## Advanced\n\n"
                    "### Events\n\n"
                    "`QTextBrowser.anchorClicked` обрабатывает относительные anchors, внешние URL "
                    "и `help://slug#anchor`.\n\n"
                    "### Code\n\n"
                    "```python\n"
                    "MarkdownHelpSection(order=1, slug='intro', title='Intro', body_md='...')\n"
                    "```\n"
                ),
            ),
        )
        dlg = MarkdownHelpDialog(title="Help", toc_title="On this page", sections=sections, parent=self)
        dlg.exec()

    def _open_sidebar_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Sidebar Dialog")
        dialog.resize(640, 420)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        shell = SidebarDialogShell(sidebar_width=160)

        general = ScrollableDialogPage()
        general_layout = general.content_layout
        general_layout.addWidget(Label("General", pixel_size=14, bold=True))
        general_layout.addWidget(CheckBox("Enable notifications"))
        name_input = CustomLineEdit(underline_color=QColor("#808080"))
        name_input.setPlaceholderText("Profile name")
        general_layout.addWidget(name_input)
        for i in range(10):
            general_layout.addWidget(CheckBox(f"Additional setting {i + 1}"))
        general_layout.addStretch()

        advanced = ScrollableDialogPage()
        advanced_layout = advanced.content_layout
        advanced_layout.addWidget(Label("Advanced", pixel_size=14, bold=True))
        mode_combo = ComboBox(underline_color=QColor("#808080"))
        mode_combo.addItems(("Balanced", "Quality", "Performance"))
        advanced_layout.addWidget(mode_combo)
        advanced_layout.addWidget(CheckBox("Write verbose logs"))
        for i in range(8):
            advanced_layout.addWidget(CheckBox(f"Optimization flag {i + 1}"))
        advanced_layout.addStretch()

        about = ScrollableDialogPage()
        about_layout = about.content_layout
        about_layout.addWidget(Label("About", pixel_size=14, bold=True))
        about_layout.addWidget(Label("SidebarDialogShell не рендерит markdown. Это layout shell для ваших страниц.", pixel_size=11, word_wrap=True))
        about_layout.addWidget(Label("ScrollableDialogPage используется как содержимое страниц, когда форма может не помещаться по высоте.", pixel_size=11, word_wrap=True))
        about_layout.addStretch()

        for page in (general, advanced, about):
            shell.pages_stack.addWidget(page)

        shell.sidebar.set_items([
            IconListItem(text="General", icon=None),
            IconListItem(text="Advanced", icon=None),
            IconListItem(text="About", icon=None),
        ])
        try:
            shell.sidebar.item_selected.connect(
                lambda idx: shell.pages_stack.setCurrentIndex(idx)
            )
        except AttributeError:
            shell.sidebar.currentRowChanged.connect(shell.pages_stack.setCurrentIndex)
        shell.sidebar.setCurrentRow(0)

        layout.addWidget(shell)

        actions = QWidget(dialog)
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addStretch()
        apply_btn = Button(text="Apply", variant="surface")
        close_btn = Button(text="Close", variant="surface")
        apply_btn.clicked.connect(dialog.accept)
        close_btn.clicked.connect(dialog.reject)
        action_layout.addWidget(apply_btn)
        action_layout.addWidget(close_btn)
        layout.addWidget(actions)

        dialog.exec()
