"""MenuCapability — dropdown menu integration."""

from PyQt6.QtWidgets import QWidget

from .base import ButtonCapability


class MenuCapability(ButtonCapability):
    """Manages button dropdown menu lifecycle."""

    def __init__(self, menu_items: list[tuple[str, any]] | None = None):
        super().__init__()
        self.menu_items = menu_items or []
        self._button = None
        self._menu_widget = None

    def attach(self, button: QWidget, region_id: str | None = None) -> None:
        super().attach(button, region_id=region_id)
        self._button = button
        self._init_menu()

    def detach(self, button: QWidget) -> None:
        if self._menu_widget:
            self._menu_widget.hide()
            self._menu_widget.deleteLater()
            self._menu_widget = None
        self._button = None

    def is_enabled(self) -> bool:
        return self._button is not None and len(self.menu_items) > 0

    def set_menu_items(self, items: list[tuple[str, any]]) -> None:
        self.menu_items = items or []
        if self._menu_widget is None:
            self._init_menu()
        else:
            self._menu_widget.set_actions(self.menu_items)

    def show_menu(self) -> None:
        if self._menu_widget is None:
            return
        if self._menu_widget.isVisible():
            self._menu_widget.hide()
            return
        self._menu_widget.show_for_anchor(self._button)

    def _init_menu(self):
        if not self._button or not self.menu_items:
            return

        from sli_ui_toolkit.ui.widgets.buttons._dropdown_menu import DropdownMenu

        self._menu_widget = DropdownMenu(self._button)
        self._menu_widget.item_selected.connect(self._on_menu_item)
        self._menu_widget.set_actions(self.menu_items)

    def _on_menu_item(self, action):
        if self._button and hasattr(self._button, "menuTriggered"):
            data = action.data()
            if hasattr(self._button, "regionMenuTriggered") and self._region_id is not None:
                self._button.regionMenuTriggered.emit(self._region_id, data)
            if self._region_id in (None, "_main"):
                self._button.menuTriggered.emit(data)
