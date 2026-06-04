"""ColorSwatch — circular Button that opens a themed QColorDialog on click."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button


class ColorSwatch(Button):
    colorChanged = pyqtSignal(QColor)

    def __init__(
        self,
        color: QColor | None = None,
        *,
        size: int = 28,
        alpha: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        initial = QColor(color) if color is not None else QColor(255, 255, 255)
        tm = ThemeManager.get_instance()
        super().__init__(
            size=(size, size),
            circular=True,
            background_color=initial,
            border_color=QColor(tm.get_color("dialog.border")),
            parent=parent,
        )
        self._color = initial
        self._dialog: QColorDialog | None = None
        self._alpha = bool(alpha)
        self.clicked.connect(self._open_dialog)
        tm.theme_changed.connect(self._refresh_border)

    def _refresh_border(self) -> None:
        self.setBorderColor(
            QColor(ThemeManager.get_instance().get_color("dialog.border"))
        )

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        self._color = QColor(color)
        self.set_background_color(QColor(color))

    setColor = set_color

    def _open_dialog(self) -> None:
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.raise_()
            self._dialog.activateWindow()
            return
        parent_window = self.window()
        dialog = QColorDialog(self._color, parent_window)
        if self._alpha:
            dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setModal(False)
        ThemeManager.get_instance().apply_theme_to_dialog(dialog)

        def on_selected(c: QColor) -> None:
            if c.isValid():
                self.set_color(c)
                self.colorChanged.emit(QColor(c))

        def on_finished(_result: int) -> None:
            self._dialog = None

        dialog.colorSelected.connect(on_selected)
        dialog.finished.connect(on_finished)
        self._dialog = dialog
        dialog.show()
