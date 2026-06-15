"""ComboBoxes page."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import ComboBox, ScrollableComboBox, SimpleOptionsFlyout

from demo.components import GalleryPage


class ComboBoxesPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="ComboBoxes",
            subtitle="Выпадающие списки разных стилей.",
            source_file=__file__,
            parent=parent,
        )

        c1 = ComboBox()
        c1.addItems(["Alpha", "Beta", "Gamma", "Delta"])
        self.add_card("ComboBox", c1)

        self._scrollable_items = [f"Item {i}" for i in range(1, 21)]
        self._scrollable_combo = ScrollableComboBox()
        self._scrollable_combo.updateState(
            count=len(self._scrollable_items),
            current_index=0,
            text=self._scrollable_items[0],
            items=self._scrollable_items,
        )
        self._scrollable_combo.setFixedWidth(220)
        self._scrollable_flyout: SimpleOptionsFlyout | None = None
        self._scrollable_combo.clicked.connect(self._open_scrollable_dropdown)
        self._scrollable_combo.wheelScrolledToIndex.connect(
            self._scrollable_combo.setCurrentIndex
        )
        self.add_card(
            "ScrollableComboBox",
            self._scrollable_combo,
            "Прокрутка колесом мыши над виджетом + клик открывает список.",
        )

        self.add_stretch()

    def _open_scrollable_dropdown(self) -> None:
        if self._scrollable_flyout is None:
            self._scrollable_flyout = SimpleOptionsFlyout(parent_widget=self.window())
            self._scrollable_flyout.item_chosen.connect(self._on_scrollable_item_chosen)
        self._scrollable_flyout.populate(
            self._scrollable_items,
            current_index=self._scrollable_combo.currentIndex(),
        )
        self._scrollable_combo.setFlyoutOpen(True)
        try:
            self._scrollable_flyout.show_below(self._scrollable_combo)
        except Exception:
            self._scrollable_flyout.show()

    def _on_scrollable_item_chosen(self, index: int) -> None:
        self._scrollable_combo.setFlyoutOpen(False)
        if 0 <= index < len(self._scrollable_items):
            self._scrollable_combo.setCurrentIndex(index)
