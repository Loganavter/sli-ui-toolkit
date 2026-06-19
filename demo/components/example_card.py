"""ExampleCard — wraps a widget sample with title + 'View source' footer.

Built only on sli_ui_toolkit primitives: CustomGroupWidget (border + title),
Label (texts), no raw QFrame/QLabel.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import CustomGroupWidget, Label


class _SourceLink(Label):
    def __init__(self, source_path: str | None, parent: QWidget | None = None) -> None:
        super().__init__("View source", pixel_size=11, parent=parent)
        self._source_path = source_path
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        tm = ThemeManager.get_instance()
        try:
            color = tm.get_color("accent")
            self.setStyleSheet(f"color: {color.name()};")
        except Exception:
            self.setStyleSheet("color: #0078D4;")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._source_path and event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._source_path))
        super().mousePressEvent(event)


class ExampleCard(CustomGroupWidget):
    """Bordered card: title via CustomGroupWidget, widget body, source-link footer."""

    def __init__(
        self,
        title: str,
        widget: QWidget,
        source_file: str | None = None,
        description: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title_text=title, parent=parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if description:
            desc = Label(description, pixel_size=11)
            desc.setWordWrap(True)
            self.add_widget(desc)

        widget_row_host = QWidget()
        widget_row = QHBoxLayout(widget_row_host)
        widget_row.setContentsMargins(0, 6, 0, 6)
        widget_row.setSpacing(8)
        widget_row.addWidget(widget)
        widget_row.addStretch()
        self.add_widget(widget_row_host)

        if source_file:
            resolved = str(Path(source_file).resolve())
            self.add_widget(_SourceLink(resolved, self))
