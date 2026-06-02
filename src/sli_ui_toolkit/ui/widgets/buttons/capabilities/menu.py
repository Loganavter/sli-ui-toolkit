"""MenuCapability — dropdown menu integration."""

from PyQt6.QtWidgets import QWidget

from .base import ButtonCapability


class MenuCapability(ButtonCapability):
    """Manages button dropdown menu lifecycle.

    Usage:
        cap = MenuCapability(menu_items=[("Copy", copy_action), ("Paste", paste_action)])
        button.attach_capability(cap)
    """

    def __init__(self, menu_items: list[tuple[str, any]] | None = None):
        self.menu_items = menu_items or []
        self._button = None
        self._menu_widget = None

    def attach(self, button: QWidget) -> None:
        self._button = button
        self._init_menu()

    def detach(self, button: QWidget) -> None:
        if self._menu_widget:
            self._menu_widget.hide()
            self._menu_widget.deleteLater()
        self._button = None

    def is_enabled(self) -> bool:
        return self._button is not None and len(self.menu_items) > 0

    def _init_menu(self):
        if not self._button or not self.menu_items:
            return

        from sli_ui_toolkit.ui.widgets.buttons._dropdown_menu import DropdownMenu

        self._menu_widget = DropdownMenu(self._button)
        self._menu_widget.item_selected.connect(self._on_menu_item)
        self._menu_widget.set_actions(self.menu_items)

    def show_menu(self) -> None:
        if self._menu_widget is None:
            return
        if self._menu_widget.isVisible():
            self._menu_widget.hide()
            return
        self._menu_widget.show_for_anchor(self._button)

    def _on_menu_item(self, action):
        if self._button and hasattr(self._button, 'menuTriggered'):
            self._button.menuTriggered.emit(action)
