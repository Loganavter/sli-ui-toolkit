from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.widgets import SidebarDialogShell


def test_sidebar_dialog_shell_uses_configured_sidebar_width_as_minimum(qapp):
    shell = SidebarDialogShell()

    assert shell.sidebar.minimumWidth() == 200
    assert shell.sidebar.maximumWidth() == 16777215
    assert shell.sidebar.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Preferred


def test_sidebar_dialog_shell_respects_custom_sidebar_minimum(qapp):
    shell = SidebarDialogShell(sidebar_width=240)

    assert shell.sidebar.minimumWidth() == 240
    assert shell.sidebar.maximumWidth() == 16777215
