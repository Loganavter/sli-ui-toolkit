"""SLI UI Toolkit demo — gallery-style main window."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, IconListWidget, Label

from demo.pages import build_pages


class MainWindow(QWidget):
    """Sidebar navigation + stacked page view."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SLI UI Toolkit — Gallery")
        self.resize(1100, 760)

        self._theme_manager = ThemeManager.get_instance()
        self._current_theme = self._theme_manager.get_current_theme()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._nav = IconListWidget()
        self._nav.setFixedWidth(220)
        self._nav.enable_minimal_scrollbar()

        self._stack = QStackedWidget()

        pages = build_pages()
        nav_items: list[tuple[str, object | None]] = []
        for title, page in pages:
            self._stack.addWidget(page)
            nav_items.append((title, None))
        self._nav.set_items(nav_items)
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        if self._nav.count() > 0:
            self._nav.setCurrentRow(0)

        body.addWidget(self._nav)
        body.addWidget(self._stack, 1)

        body_wrap = QWidget()
        body_wrap.setLayout(body)
        root.addWidget(body_wrap, 1)

        self._theme_manager.theme_changed.connect(self._on_theme_changed)

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        layout.addWidget(Label("SLI UI Toolkit Gallery", pixel_size=15, bold=True))
        layout.addStretch()

        self._theme_button = Button(text=self._theme_label(), variant="surface")
        self._theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self._theme_button)
        return header

    def _theme_label(self) -> str:
        return "Switch to Dark" if self._current_theme == "light" else "Switch to Light"

    def _toggle_theme(self) -> None:
        self._current_theme = "dark" if self._current_theme == "light" else "light"
        self._theme_manager.set_theme(self._current_theme, QApplication.instance())

    def _on_theme_changed(self) -> None:
        self._theme_button.setText(self._theme_label())
        self.update()
