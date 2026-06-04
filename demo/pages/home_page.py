"""Home page — overview & navigation hints."""

from __future__ import annotations

from PyQt6.QtWidgets import QGridLayout, QWidget

from sli_ui_toolkit import __version__
from sli_ui_toolkit.widgets import CustomGroupWidget, Label

from demo.components import GalleryPage


_SECTIONS = [
    ("Buttons", "Все варианты Button + интерактивный playground."),
    ("Basic Inputs", "Текстовые поля, спинбоксы, слайдеры, чекбоксы, свитчи, радио."),
    ("ComboBoxes", "Стандартный и scrollable combobox."),
    ("Labels & Text", "Label-варианты, drop-zone, editable text."),
    ("Lists & Items", "IconListWidget, EditableListItem."),
    ("Composites", "CustomGroupWidget и составные формовые блоки."),
    ("Flyouts", "Color/Font/Indexed/Simple options flyouts."),
    ("Dialogs", "MarkdownHelpDialog, SidebarDialogShell, ScrollableDialogPage."),
    ("Feedback", "LoadingSpinner, ToastNotification, MinimalistScrollBar."),
    ("Charts", "SunburstChart, Timeline."),
    ("Console", "LogConsoleWidget, ProcessConsoleWidget."),
    ("Misc", "CalendarWidget, PreviewPanel, оверлеи."),
]


class HomePage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title=f"SLI UI Toolkit Gallery v{__version__}",
            subtitle=(
                "Showcase каталога виджетов. Выбирайте раздел в боковой панели."
                " Каждая карточка ссылается на исходник виджета через 'View source'."
            ),
            source_file=__file__,
            parent=parent,
        )

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        for idx, (title, desc) in enumerate(_SECTIONS):
            tile = CustomGroupWidget(title_text=title)
            d = Label(desc, pixel_size=11)
            d.setWordWrap(True)
            tile.add_widget(d)
            grid.addWidget(tile, idx // 3, idx % 3)

        self.add_card("Каталог разделов", grid_holder, source_file=__file__)
        self.add_stretch()
