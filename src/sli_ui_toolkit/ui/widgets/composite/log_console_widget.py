from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleLine, ConsoleView


@dataclass(frozen=True)
class LogConsoleEntry:
    level: str
    text: str
    color: str | None = None
    bold: bool = False
    italic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class LogConsoleWidget(QWidget):
    """Level-colored log console backed by the painted :class:`ConsoleView`.

    ``output`` is a :class:`ConsoleView`; use its API (not a stock
    text-edit API).
    """

    def __init__(self, parent=None, *, max_entries: int = 1000):
        super().__init__(parent)
        self._max_entries = max(1, int(max_entries))
        self._entries: list[LogConsoleEntry] = []
        self.theme_manager = ThemeManager.get_instance()
        self._info_color = QColor("#ffffff")
        self._error_color = QColor("#FF0000")
        self._status_color = QColor("#9E9E9E")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.output = ConsoleView(self, max_lines=self._max_entries)
        self.output.setObjectName("LogConsoleOutput")

        layout.addWidget(self.output)

        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)

    def set_max_entries(self, max_entries: int) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries = self._entries[-self._max_entries :]
        self.output.set_max_lines(self._max_entries)
        self._rebuild()

    def set_output_font(self, font: QFont) -> None:
        """Set the log text font on the painted console."""
        self.output.set_font(QFont(font))

    def clear(self) -> None:
        self._entries.clear()
        self.output.clear()

    def entries(self) -> tuple[LogConsoleEntry, ...]:
        return tuple(self._entries)

    def history(self) -> tuple[LogConsoleEntry, ...]:
        return self.entries()

    def plain_text_history(self) -> tuple[str, ...]:
        return tuple(entry.text for entry in self._entries)

    def full_text(self, *, separator: str = "\n") -> str:
        return separator.join(self.plain_text_history())

    def append_message(
        self,
        text: str,
        *,
        level: str = "info",
        color: str | QColor | None = None,
        bold: bool = False,
        italic: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> LogConsoleEntry:
        entry = LogConsoleEntry(
            level=self._normalize_level(level),
            text=str(text),
            color=self._normalize_color(color),
            bold=bool(bold),
            italic=bool(italic),
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        self._entries = self._entries[-self._max_entries :]
        self.output.append(
            entry.text,
            color=self._entry_color(entry),
            bold=self._entry_bold(entry),
            italic=entry.italic,
        )
        return entry

    def append_info(self, text: str, **kwargs) -> LogConsoleEntry:
        return self.append_message(text, level="info", **kwargs)

    def append_error(self, text: str, **kwargs) -> LogConsoleEntry:
        return self.append_message(text, level="error", **kwargs)

    def append_status(self, text: str, **kwargs) -> LogConsoleEntry:
        return self.append_message(text, level="status", **kwargs)

    def append_entry(self, entry: LogConsoleEntry) -> LogConsoleEntry:
        return self.append_message(
            entry.text,
            level=entry.level,
            color=entry.color,
            bold=entry.bold,
            italic=entry.italic,
            metadata=entry.metadata,
        )

    def set_entries(self, entries: list[LogConsoleEntry]) -> None:
        self._entries = list(entries)[-self._max_entries :]
        self.output.set_max_lines(self._max_entries)
        self._rebuild()

    def _rebuild(self) -> None:
        self.output.set_lines(self._entry_to_console_line(entry) for entry in self._entries)

    def _entry_to_console_line(self, entry: LogConsoleEntry) -> ConsoleLine:
        return ConsoleLine(
            entry.text,
            self._entry_color(entry),
            self._entry_bold(entry),
            entry.italic,
        )

    def _entry_color(self, entry: LogConsoleEntry) -> QColor:
        if entry.color:
            return QColor(entry.color)
        if entry.level == "error":
            return QColor(self._error_color)
        if entry.level == "status":
            return QColor(self._status_color)
        return QColor(self._info_color)

    def _entry_bold(self, entry: LogConsoleEntry) -> bool:
        return entry.bold or entry.level == "error"

    def _normalize_level(self, level: str) -> str:
        return level if level in {"info", "error", "status"} else "info"

    def _normalize_color(self, color: str | QColor | None) -> str | None:
        if color is None:
            return None
        if isinstance(color, QColor):
            return color.name(QColor.NameFormat.HexArgb)
        value = str(color).strip()
        return value or None

    def _apply_styles(self) -> None:
        self._info_color = QColor(self.theme_manager.get_color("dialog.text"))
        self._error_color = QColor("#D70000" if self.theme_manager.is_dark() else "#FF0000")
        self._status_color = QColor("#9E9E9E")
        self._rebuild()
