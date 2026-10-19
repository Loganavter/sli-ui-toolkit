from __future__ import annotations

from PySide6.QtCore import QDate, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.ui.managers.ui_metrics import (
    AXIS_FONT,
    AXIS_SCALE,
    connect_ui_metrics,
)
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.theme import ThemeManager

#: Design-px geometry for a calendar cell — resolved at USE time and
#: re-derived on the appearance bus so the grid follows a live UiScale change.
_DESIGN_MIN_SIZE = (28, 36)
_DESIGN_HINT_SIZE = (50, 70)

class CalendarDayButton(Button):
    date_clicked = Signal(QDate)
    date_context_menu = Signal(QDate)

    def __init__(self, parent=None):
        super().__init__(
            toggle=True,
            size=(0, 0),
            corner_radius=4,
            variant="ghost",
            parent=parent
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(scaled_px(_DESIGN_MIN_SIZE[0]), scaled_px(_DESIGN_MIN_SIZE[1]))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
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
        connect_ui_metrics(
            self,
            self._on_ui_metrics_changed,
            axes=frozenset({AXIS_FONT, AXIS_SCALE}),
        )

    def _on_ui_metrics_changed(self, *_args: object) -> None:
        """Re-derive the cell floor for the live factor (appearance bus)."""
        self.setMinimumSize(
            scaled_px(_DESIGN_MIN_SIZE[0]), scaled_px(_DESIGN_MIN_SIZE[1])
        )
        self.updateGeometry()
        self.update()

    def set_data(self, has_data: bool, color: QColor | None = None) -> None:
        self._has_data = has_data
        self._data_color = color
        self._sync_calendar_background()

    def set_date(self, date: QDate) -> None:
        self.date = date

    def set_weekend(self, is_weekend: bool, color: QColor | None = None) -> None:
        self._is_weekend = is_weekend
        self._weekend_color = color
        self._sync_calendar_background()

    def set_disabled_export(self, is_disabled: bool, color: QColor | None = None) -> None:
        self._is_disabled_export = is_disabled
        self._disabled_export_color = color
        self._sync_calendar_background()

    def setChecked(self, checked: bool, emit: bool = True, emit_signal: bool | None = None):
        super().setChecked(checked, emit=emit, emit_signal=emit_signal)
        self._sync_calendar_background()

    def _sync_calendar_background(self) -> None:
        """Resolve calendar semantic backgrounds without bypassing Button input state."""
        if self._is_disabled_export and self._disabled_export_color:
            self.set_background_color(None)
            self.set_override_bg_color(QColor(self._disabled_export_color))
            self.set_bg_locked(True)
        elif self._checked:
            self.set_background_color(None)
            self.set_override_bg_color(self._theme_manager.get_color("accent"))
            self.set_bg_locked(True)
        elif self._is_weekend and self._weekend_color:
            self.set_override_bg_color(None)
            self.set_bg_locked(False)
            self.set_background_color(QColor(self._weekend_color))
        elif self._has_data and self._data_color:
            self.set_override_bg_color(None)
            self.set_bg_locked(False)
            self.set_background_color(QColor(self._data_color))
        else:
            self.set_override_bg_color(None)
            self.set_bg_locked(False)
            self.set_background_color(None)

    def _on_click(self):
        if self.date:
            self.date_clicked.emit(self.date)

    def _on_context_menu(self, pos):
        if self.date:
            self.date_context_menu.emit(self.date)

    def sizeHint(self) -> QSize:
        return QSize(scaled_px(_DESIGN_HINT_SIZE[0]), scaled_px(_DESIGN_HINT_SIZE[1]))

    def minimumSizeHint(self) -> QSize:
        return QSize(scaled_px(_DESIGN_MIN_SIZE[0]), scaled_px(_DESIGN_MIN_SIZE[1]))
