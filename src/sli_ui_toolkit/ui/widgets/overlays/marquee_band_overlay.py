"""In-window selection rubber-band (not QRubberBand / Qt.Popup)."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.overlays.in_window_overlay import (
    TopLevelInWindowOverlay,
)


class MarqueeBandOverlay(TopLevelInWindowOverlay):
    """Pointer-transparent selection rectangle on the host window overlay.

    Same stacking model as ``DragDropOverlay``: in-window child, no
    ``grabMouse`` (Wayland only allows grabs on ``Qt.Popup``). Pair with
    ``MarqueeBandGesture`` for drag tracking.
    """

    def __init__(self, parent: QWidget):
        super().__init__(
            parent,
            close_on_background=False,
            close_on_escape=False,
            close_on_deactivate=False,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._accent = QColor("#0078D4")
        self._active = False
        try:
            from sli_ui_toolkit.theme import ThemeManager

            color = QColor(ThemeManager.get_instance().get_color("accent"))
            if color.isValid():
                self._accent = color
        except Exception:
            pass

    def set_accent(self, color: QColor) -> None:
        self._accent = QColor(color)
        if self.isVisible():
            self.update()

    def accent(self) -> QColor:
        return QColor(self._accent)

    def set_band(self, rect: QRect | None) -> None:
        """Show ``rect`` in parent-local coordinates, or hide when empty/None."""
        if rect is None or not rect.isValid() or rect.isEmpty():
            self._active = False
            self.hide()
            return
        self._active = True
        self.setGeometry(rect)
        self.raise_()
        self.show()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if not self._active or not self.isVisible():
            return
        painter = QPainter(self)
        fill = QColor(self._accent)
        fill.setAlpha(48)
        border = QColor(self._accent)
        border.setAlpha(200)
        painter.fillRect(self.rect(), fill)
        painter.setPen(QPen(border, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
