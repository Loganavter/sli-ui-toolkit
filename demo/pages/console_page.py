"""Console & Logs page."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.widgets import (
    Button,
    LogConsoleWidget,
    ProcessConsoleWidget,
)

from demo.components import GalleryPage


class ConsolePage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Console & Logs",
            subtitle="Виджеты лог-консоли.",
            source_file=__file__,
            parent=parent,
        )

        log = LogConsoleWidget()
        log.setMinimumHeight(180)
        for level, text in (
            ("info", "Application started"),
            ("status", "Low memory warning"),
            ("error", "Failed to load resource"),
            ("info", "Render frame in 16ms"),
        ):
            log.append_message(text, level=level)

        controls = QWidget()
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        cl.addWidget(log, 1)
        clear = Button(text="Clear", variant="surface")
        clear.clicked.connect(lambda: getattr(log, "clear", lambda: None)())
        cl.addWidget(clear)
        self.add_card("LogConsoleWidget", controls)

        proc = ProcessConsoleWidget()
        proc.setMinimumHeight(180)
        proc.start_shell()
        self.add_card(
            "ProcessConsoleWidget",
            proc,
            "Виджет вывода процесса (stdout/stderr). Демо запускает интерактивный шелл — введите команду и нажмите Send.",
        )

        self.add_stretch()
