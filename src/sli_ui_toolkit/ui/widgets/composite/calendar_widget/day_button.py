from __future__ import annotations

from PyQt6.QtCore import QDate, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QSizePolicy

from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.theme import ThemeManager

class CalendarDayButton(Button):
    date_clicked = pyqtSignal(QDate)
    date_context_menu = pyqtSignal(QDate)

    def __init__(self, parent=None):
        super().__init__(
            toggle=True,
            size=(0, 0),
            corner_radius=4,
            variant="ghost",
            parent=parent
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(28, 36)
        self._is_weekend = False
        self._weekend_color: QColor | None = None
        self._is_disabled_export = False
        self._disabled_export_color: QColor | None = None
        self._has_data = False
        self._data_color: QColor | None = None
        self.date: QDate | None = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clicked.connect(self._on_click)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._theme_manager = ThemeManager.get_instance()

    def set_data(self, has_data: bool, color: QColor | None = None) -> None:
        self._has_data = has_data
        self._data_color = color
        self.update()

    def set_date(self, date: QDate) -> None:
        self.date = date

    def set_weekend(self, is_weekend: bool, color: QColor | None = None) -> None:
        self._is_weekend = is_weekend
        self._weekend_color = color
        self.update()

    def set_disabled_export(self, is_disabled: bool, color: QColor | None = None) -> None:
        self._is_disabled_export = is_disabled
        self._disabled_export_color = color
        self.update()

    def paintEvent(self, event):
        # Определить только высокий приоритет (disabled/checked) через override
        if self._is_disabled_export and self._disabled_export_color:
            self._override_bg_color = self._disabled_export_color
        elif self._checked:
            self._override_bg_color = self._theme_manager.get_color("accent")
        else:
            self._override_bg_color = None

        # Button рисует себя с hover эффектами
        super().paintEvent(event)

        # Потом рисуем тинты поверх (не блокируя hover)
        tint = self._compute_base_tint()
        if tint:
            self._paint_tint_overlay(tint)

    def _compute_base_tint(self) -> QColor | None:
        """Compute visual indicator tints (weekend, data, etc).

        Returns highest-priority tint. In the future, this can be extended
        to blend multiple tints or apply interactive state modifiers.
        Priority order: disabled > weekend > data
        """
        if self._is_disabled_export and self._disabled_export_color:
            color = QColor(self._disabled_export_color)
            color.setAlpha(60)
            return color

        if self._is_weekend and self._weekend_color:
            color = QColor(self._weekend_color)
            color.setAlpha(60)
            return color

        if self._has_data and self._data_color:
            color = QColor(self._data_color)
            color.setAlpha(50)
            return color

        return None

    def _paint_tint_overlay(self, tint_color: QColor) -> None:
        """Paint a tint layer on top of the button without blocking hover."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(tint_color)
        painter.setPen(Qt.PenStyle.NoPen)

        radius = max(0, int(self._corner_radius_px or 6))
        rect_f = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(rect_f, radius, radius)

    def _on_click(self):
        if self.date:
            self.date_clicked.emit(self.date)

    def _on_context_menu(self, pos):
        if self.date:
            self.date_context_menu.emit(self.date)

    def enterEvent(self, event):
        if self._has_data:
            super().enterEvent(event)
        event.accept()

    def leaveEvent(self, event):
        if self._has_data:
            super().leaveEvent(event)
        else:
            self._hovered = False
            self.update()
        event.accept()

    def sizeHint(self) -> QSize:
        return QSize(50, 70)

    def minimumSizeHint(self) -> QSize:
        return QSize(28, 36)
