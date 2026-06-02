"""Main application window for demo."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QApplication,
    QScrollArea
)
from PyQt6.QtGui import QColor
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import (
    Button, BodyLabel, GroupTitleLabel, CustomLineEdit, ComboBox,
    Switch, CheckBox, LoadingSpinner, CaptionLabel
)


class ButtonsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(GroupTitleLabel(text="Variants"))
        btn_layout = QHBoxLayout()
        for variant in ["default", "accent", "delete", "primary", "surface"]:
            btn = Button(text=variant.capitalize(), variant=variant)
            btn_layout.addWidget(btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addWidget(GroupTitleLabel(text="States"))
        toggle = Button(text="Toggle", toggle=True, variant="default")
        layout.addWidget(toggle)

        layout.addWidget(GroupTitleLabel(text="Features"))
        btn_with_badge = Button(text="Notification", badge="3", variant="accent")
        layout.addWidget(btn_with_badge)

        layout.addWidget(GroupTitleLabel(text="Custom Colors"))
        custom_layout = QHBoxLayout()
        btn_green = Button(text="Green", background_color=QColor("#4CAF50"))
        btn_orange = Button(text="Orange", background_color=QColor("#FF9800"))
        btn_purple = Button(text="Purple", background_color=QColor("#9C27B0"))
        custom_layout.addWidget(btn_green)
        custom_layout.addWidget(btn_orange)
        custom_layout.addWidget(btn_purple)
        custom_layout.addStretch()
        layout.addLayout(custom_layout)

        layout.addWidget(GroupTitleLabel(text="Custom Colors with Alpha"))
        alpha_layout = QHBoxLayout()
        color_alpha = QColor("#E91E63")
        color_alpha.setAlpha(180)
        btn_alpha = Button(text="Alpha 70%", background_color=color_alpha)
        alpha_layout.addWidget(btn_alpha)
        alpha_layout.addStretch()
        layout.addLayout(alpha_layout)

        layout.addStretch()


class InputsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(GroupTitleLabel(text="Text Input"))
        le = CustomLineEdit()
        le.setPlaceholderText("Type something...")
        layout.addWidget(le)

        layout.addWidget(GroupTitleLabel(text="ComboBox"))
        combo = ComboBox()
        combo.addItems(["Option 1", "Option 2", "Option 3"])
        layout.addWidget(combo)

        layout.addWidget(GroupTitleLabel(text="Toggle Controls"))
        toggle_layout = QHBoxLayout()
        sw = Switch()
        toggle_layout.addWidget(BodyLabel(text="Switch:"))
        toggle_layout.addWidget(sw)
        toggle_layout.addStretch()
        cb = CheckBox("Checkbox")
        toggle_layout.addWidget(cb)
        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)

        layout.addStretch()


class CompositesPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(GroupTitleLabel(text="Dialogs"))
        info = CaptionLabel(text="Dialog widgets are available through sli_ui_toolkit.widgets")
        layout.addWidget(info)

        from sli_ui_toolkit.widgets import DialogActionBar
        actionbar = DialogActionBar("OK", "Cancel")
        layout.addWidget(actionbar)

        layout.addStretch()


class MiscPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        layout.addWidget(GroupTitleLabel(text="Labels"))
        layout.addWidget(BodyLabel(text="Body Label - Main content"))
        layout.addWidget(CaptionLabel(text="Caption Label - Secondary text"))

        layout.addWidget(GroupTitleLabel(text="Loading Spinner"))
        spinner = LoadingSpinner()
        layout.addWidget(spinner)

        layout.addStretch()


class MainWindow(QWidget):
    """Demo application window with tabs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SLI UI Toolkit Demo")
        self.resize(900, 700)

        self._theme_manager = ThemeManager.get_instance()
        self._current_theme = self._theme_manager.get_current_theme()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

        title = BodyLabel(text="SLI UI Toolkit Demo")
        header_layout.addWidget(title)
        header_layout.addStretch()

        theme_btn = Button(text=self._get_theme_button_text(), variant="surface")
        theme_btn.clicked.connect(self._toggle_theme)
        self._theme_button = theme_btn
        header_layout.addWidget(theme_btn)

        header_widget = QWidget()
        header_widget.setLayout(header_layout)
        main_layout.addWidget(header_widget)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._tabs.addTab(ButtonsPage(), "Buttons")
        self._tabs.addTab(InputsPage(), "Inputs")
        self._tabs.addTab(CompositesPage(), "Composites")
        self._tabs.addTab(MiscPage(), "Misc")

        main_layout.addWidget(self._tabs)

        self._theme_manager.theme_changed.connect(self._on_theme_changed)

    def _get_theme_button_text(self) -> str:
        return "🌙 Dark" if self._current_theme == "light" else "☀️ Light"

    def _toggle_theme(self):
        self._current_theme = "dark" if self._current_theme == "light" else "light"
        self._theme_manager.set_theme(self._current_theme, QApplication.instance())

    def _on_theme_changed(self):
        self._theme_button.setText(self._get_theme_button_text())
        self.update()
