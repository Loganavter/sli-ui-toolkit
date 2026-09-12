from sli_ui_toolkit.ui.widgets.composite.unified_flyout.common import (
    FlyoutMode,
    current_index_for_list,
    items_for_list,
)

class _UnifiedFlyoutContentMixin:
    def populate(self, list_num: int, items: list, list_type="image", current_index=-1):
        panel = (
            self.panel_left
            if (list_num == 1 or list_type == "simple")
            else self.panel_right
        )
        owner = (
            self._owner_proxy_simple
            if list_type == "simple"
            else (self._owner_proxy_left if list_num == 1 else self._owner_proxy_right)
        )
        panel.clear_and_rebuild(
            items, owner, self.item_height, self.item_font, list_type, current_index
        )
        if self.mode == FlyoutMode.DOUBLE:
            self.refreshGeometry()

    def sync_from_store(self):
        if not self.isVisible() or self._is_simple_mode:
            return

        doc = self.store.document
        self.panel_left.sync_with_list(
            items_for_list(doc, 1),
            self._owner_proxy_left,
            self.item_height,
            self.item_font,
            "image",
            current_index_for_list(doc, 1),
        )
        self.panel_right.sync_with_list(
            items_for_list(doc, 2),
            self._owner_proxy_right,
            self.item_height,
            self.item_font,
            "image",
            current_index_for_list(doc, 2),
        )
        self.refreshGeometry(immediate=True)

    def update_rating_for_item(self, list_num: int, index: int):
        if not self.isVisible():
            return
        panel = self.panel_left if list_num == 1 else self.panel_right
        if panel and panel.isVisible():
            panel.update_rating_for_item(index)
