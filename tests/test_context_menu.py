from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import (
    ContextMenu,
    ContextMenuAction,
    ContextMenuBuilder,
    ContextMenuSeparator,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu import _SeparatorRow


def test_context_menu_is_public():
    from sli_ui_toolkit import widgets

    assert widgets.ContextMenu is ContextMenu
    assert widgets.ContextMenuAction is ContextMenuAction
    assert widgets.ContextMenuBuilder is ContextMenuBuilder


def test_context_menu_is_in_app_widget_not_separate_window(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = ContextMenuBuilder().action("rename", "Rename").build(parent)

    assert not menu.isWindow()
    assert menu.parentWidget() is not None


def test_context_menu_builder_creates_rows(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = (
        ContextMenuBuilder()
        .action("rename", "Rename", shortcut="F2")
        .separator()
        .action("remove", "Remove", enabled=False, danger=True)
        .build(parent)
    )

    assert [row._text for row in menu._rows] == ["Rename", "Remove"]
    assert menu._rows[0]._shortcut_text == "F2"
    assert not menu._rows[1].isEnabled()
    assert menu._rows[1]._danger is True


def test_context_menu_trims_duplicate_separators(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = ContextMenu(
        parent,
        entries=[
            ContextMenuSeparator(),
            ContextMenuAction("rename", "Rename"),
            ContextMenuSeparator(),
            ContextMenuSeparator(),
        ],
    )

    separator_rows = [
        menu.content_layout.itemAt(i).widget()
        for i in range(menu.content_layout.count())
        if isinstance(menu.content_layout.itemAt(i).widget(), _SeparatorRow)
    ]
    assert separator_rows == []
    assert [row._text for row in menu._rows] == ["Rename"]


def test_context_menu_submenu_and_trigger_signal(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    triggered = []
    menu = ContextMenu(
        parent,
        entries=[
            ContextMenuAction(
                "edit",
                "Edit",
                children=(ContextMenuAction("rename", "Rename", data={"id": 1}),),
            )
        ],
        on_triggered=lambda action_id, data: triggered.append((action_id, data)),
    )

    edit_row = menu._rows[0]
    assert edit_row._has_children

    edit_row.clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    submenu._rows[0].clicked.emit()

    assert triggered == [("rename", {"id": 1})]
    assert not menu.isVisible()
