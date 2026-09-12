from __future__ import annotations

from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget, QVBoxLayout

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


def test_sidebar_dialog_shell_header_is_pinned_above_the_nav_list(qapp):
    header = QLabel("search")
    shell = SidebarDialogShell(sidebar_header=header)

    assert shell.sidebar_header is header
    assert shell.sidebar_column is not None
    # The header and the nav list share the sidebar column, header on top.
    layout = shell._sidebar_column_layout
    assert layout.count() == 2
    assert layout.itemAt(0).widget() is header
    assert layout.itemAt(1).widget() is shell.sidebar
    # The column (not the bare list) is the shell's left column and tracks
    # the sidebar width on scale changes.
    assert shell.main_layout.itemAt(0).widget() is shell.sidebar_column
    assert shell.sidebar_column.minimumWidth() == 200
    assert shell.sidebar.minimumWidth() == 200


def test_sidebar_dialog_shell_without_header_keeps_bare_sidebar(qapp):
    shell = SidebarDialogShell()

    assert shell.sidebar_header is None
    assert shell.sidebar_column is None
    assert shell.main_layout.itemAt(0).widget() is shell.sidebar


def test_sidebar_dialog_shell_header_parented_to_shell(qapp):
    header = QWidget()
    shell = SidebarDialogShell(sidebar_header=header)

    assert header.parent() is shell.sidebar_column
