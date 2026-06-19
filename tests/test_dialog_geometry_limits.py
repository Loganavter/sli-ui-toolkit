from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout

from sli_ui_toolkit.ui.dialogs import BaseDialog, setup_dialog_scaffold
from sli_ui_toolkit.widgets import MarkdownHelpDialog, MarkdownHelpSection


def test_base_dialog_does_not_set_default_minimum_size(qapp):
    dialog = BaseDialog(title="Plain")

    assert dialog.minimumWidth() == 0
    assert dialog.minimumHeight() == 0


def test_dialog_scaffold_buttons_keep_natural_minimums(qapp):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)

    setup_dialog_scaffold(dialog, layout, ok_text="OK", cancel_text="Cancel")

    assert dialog.ok_button.minimumWidth() == 0
    assert dialog.cancel_button.minimumWidth() == 0


def test_markdown_help_dialog_does_not_cap_nav_or_page_width(qapp):
    dialog = MarkdownHelpDialog(
        sections=[
            MarkdownHelpSection(
                order=1,
                title="Very long help navigation title",
                slug="long-title",
                body_md="### Heading\n\nBody",
            )
        ]
    )
    dialog.resize(900, 600)
    dialog.show()
    qapp.processEvents()

    page = dialog.scroll_area.widget()

    assert dialog.nav_widget.maximumWidth() == 16777215
    assert dialog.nav_widget.minimumWidth() > 0
    assert page.maximumWidth() == 16777215

    dialog.close()
    dialog.deleteLater()
    qapp.processEvents()
