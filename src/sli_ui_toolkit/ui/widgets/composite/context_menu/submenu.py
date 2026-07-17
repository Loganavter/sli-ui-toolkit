"""Submenu open/close/position helpers operating on a ContextMenu instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect

from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.ui.popup_surface import clamp_popup_rect, screen_available_rect
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import ContextMenuAction
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import ContextMenuRow

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu


def close_submenu(menu: ContextMenu) -> None:
    submenu = menu._open_submenu
    if submenu is None:
        return
    menu._open_submenu = None
    if menu._submenu_owner_row is not None:
        menu._submenu_owner_row.set_submenu_open(False)
    menu._submenu_owner_row = None
    submenu.hide()
    submenu.deleteLater()


def position_submenu(
    menu: ContextMenu, submenu: ContextMenu, row: ContextMenuRow
) -> None:
    size = submenu.sizeHint()
    if menu.is_popup_surface():
        anchor_tl = row.mapToGlobal(QPoint(0, 0))
        anchor_rect = QRect(anchor_tl, row.size())
        available = screen_available_rect(submenu, margin=4)
        target = QRect(
            anchor_rect.right() + 2,
            anchor_rect.top() - menu.SHADOW_RADIUS,
            size.width(),
            size.height(),
        )
        if (
            target.right() > available.right()
            and anchor_rect.left() - size.width() - 2 >= available.left()
        ):
            target.moveLeft(anchor_rect.left() - size.width() - 2)
        submenu.setGeometry(clamp_popup_rect(target, submenu, margin=4))
        return

    anchor_rect = surface_anchor_rect(submenu, row, submenu.overlay_layer)
    available = surface_available_rect(submenu, row, submenu.overlay_layer, margin=4)
    target = QRect(
        anchor_rect.right() + 2,
        anchor_rect.top() - menu.SHADOW_RADIUS,
        size.width(),
        size.height(),
    )
    if (
        target.right() > available.right()
        and anchor_rect.left() - size.width() - 2 >= available.left()
    ):
        target.moveLeft(anchor_rect.left() - size.width() - 2)
    target = clamp_surface_rect(target, available)
    submenu.setGeometry(target)


def toggle_submenu(
    menu: ContextMenu, row: ContextMenuRow, spec: ContextMenuAction
) -> None:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu

    if menu._open_submenu is not None and menu._submenu_owner_row is row:
        close_submenu(menu)
        return
    close_submenu(menu)

    parent = menu._logical_parent if menu.is_popup_surface() else menu.parentWidget()
    submenu = ContextMenu(
        parent,
        entries=spec.children,
        on_triggered=menu._on_triggered,
        _is_submenu=True,
        surface=menu._surface,
    )
    submenu.actionTriggered.connect(menu.actionTriggered)
    submenu._owner_menu = menu
    if not menu.is_popup_surface():
        submenu._ensure_overlay_parent(row)

    menu._open_submenu = submenu
    menu._submenu_owner_row = row
    row.set_submenu_open(True)

    position_submenu(menu, submenu, row)
    submenu.show()
    submenu.raise_()


def root_menu(menu: ContextMenu) -> ContextMenu:
    current = menu
    while current._owner_menu is not None:
        current = current._owner_menu
    return current
