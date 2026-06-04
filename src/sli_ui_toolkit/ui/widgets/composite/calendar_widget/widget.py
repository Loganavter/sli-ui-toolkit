from __future__ import annotations

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QWheelEvent
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.day_button import CalendarDayButton
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.models import (
    CalendarViewModel,
)


_THEME_KEYS = {
    "accent": "accent",
    "hover": "dialog.button.hover",
    "text": "dialog.text",
    "bg": "dialog.background",
}


def _theme_color(theme_manager: ThemeManager, key: str, fallback: str) -> str:
    try:
        return theme_manager.get_color(key).name()
    except Exception:
        return fallback


def _mix_colors(first: QColor, second: QColor, first_weight: float) -> QColor:
    first_weight = max(0.0, min(1.0, first_weight))
    second_weight = 1.0 - first_weight
    return QColor(
        int(first.red() * first_weight + second.red() * second_weight),
        int(first.green() * first_weight + second.green() * second_weight),
        int(first.blue() * first_weight + second.blue() * second_weight),
    )


def _contrast_color(color: QColor) -> QColor:
    luminance = (
        0.299 * color.red()
        + 0.587 * color.green()
        + 0.114 * color.blue()
    )
    return QColor("#111111") if luminance > 150 else QColor("#F5F5F5")


class CalendarWidget(QWidget):
    """Generic three-level calendar (days / months / years).

    Feed data via ``update_view(CalendarViewModel)``.
    Connect to signals for navigation and selection.
    """

    date_clicked = pyqtSignal(QDate)
    date_context_menu = pyqtSignal(QDate)
    month_selected = pyqtSignal(int, int)
    month_context_menu = pyqtSignal(int, int)
    year_selected = pyqtSignal(int)
    year_context_menu = pyqtSignal(int)

    navigate_previous = pyqtSignal()
    navigate_next = pyqtSignal()
    title_clicked = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        weekday_labels: list[str] | None = None,
        accent_color: str | None = None,
        hover_color: str | None = None,
        text_color: str | None = None,
        bg_color: str | None = None,
        data_bg: str | None = None,
        weekend_bg: str | None = None,
        disabled_bg: str | None = None,
    ):
        super().__init__(parent)
        self._current_year = QDate.currentDate().year()

        self._theme_manager = ThemeManager.get_instance()

        self._color_overrides: dict[str, str] = {}
        for name, value in (
            ("accent", accent_color),
            ("hover", hover_color),
            ("text", text_color),
            ("bg", bg_color),
            ("data_bg", data_bg),
            ("weekend_bg", weekend_bg),
            ("disabled_bg", disabled_bg),
        ):
            if value is not None:
                self._color_overrides[name] = value

        self._resolve_palette()

        self._day_buttons: list[CalendarDayButton] = []
        self._month_buttons: list[Button] = []
        self._year_buttons: list[Button] = []
        self._weekday_labels_widgets: list[QLabel] = []

        self._weekday_names = weekday_labels or [
            tr("weekday_mon", default="Mon"),
            tr("weekday_tue", default="Tue"),
            tr("weekday_wed", default="Wed"),
            tr("weekday_thu", default="Thu"),
            tr("weekday_fri", default="Fri"),
            tr("weekday_sat", default="Sat"),
            tr("weekday_sun", default="Sun"),
        ]

        self._last_vm: CalendarViewModel | None = None
        self._setup_ui()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

    def _resolve_palette(self) -> None:
        """Pull theme defaults; user overrides win."""
        tm = self._theme_manager
        bg = QColor(_theme_color(tm, _THEME_KEYS["bg"], "#191919"))
        text = QColor(_theme_color(tm, _THEME_KEYS["text"], "#F2F2F2"))
        accent = QColor(_theme_color(tm, _THEME_KEYS["accent"], "#3A7AFE"))
        checked = QColor(
            _theme_color(tm, "button.toggle.background.checked", "#C0C0C0")
        )
        is_dark = bool(getattr(tm, "is_dark", lambda: False)())

        defaults = {
            "accent": accent.name(),
            "hover": _theme_color(tm, _THEME_KEYS["hover"], "#3A3A3A"),
            "text": text.name(),
            "bg": bg.name(),
        }
        defaults["weekend_bg"] = _mix_colors(accent, bg, 0.24 if is_dark else 0.18).name()
        defaults["data_bg"] = checked.name()
        defaults["disabled_bg"] = (
            _mix_colors(QColor("#E06C6C"), bg, 0.62).name()
            if is_dark
            else _mix_colors(QColor("#D94F4F"), bg, 0.28).name()
        )

        palette = {**defaults, **self._color_overrides}
        self._accent = palette["accent"]
        self._hover = palette["hover"]
        self._text = palette["text"]
        self._bg = palette["bg"]
        self._data_bg = palette["data_bg"]
        self._weekend_bg = palette["weekend_bg"]
        self._disabled_bg = palette["disabled_bg"]
        self._muted_text = self._faded_color(0.68)
        self._data_text = _contrast_color(QColor(self._data_bg)).name()
        self._disabled_text = _contrast_color(QColor(self._disabled_bg)).name()

    def set_colors(
        self,
        *,
        accent_color: str | None = None,
        hover_color: str | None = None,
        text_color: str | None = None,
        bg_color: str | None = None,
        data_bg: str | None = None,
        weekend_bg: str | None = None,
        disabled_bg: str | None = None,
    ) -> None:
        """Override one or more colors; passing None clears the override."""
        for name, value in (
            ("accent", accent_color),
            ("hover", hover_color),
            ("text", text_color),
            ("bg", bg_color),
            ("data_bg", data_bg),
            ("weekend_bg", weekend_bg),
            ("disabled_bg", disabled_bg),
        ):
            if value is None:
                self._color_overrides.pop(name, None)
            else:
                self._color_overrides[name] = value
        self._resolve_palette()
        self._apply_styles()

    def _on_theme_changed(self, *args, **kwargs) -> None:
        self._resolve_palette()
        self._apply_styles()

    def _font_unit(self) -> int:
        """Базовая единица — высота строки шрифта виджета."""
        return max(12, self.fontMetrics().height())

    def _spacing_unit(self) -> int:
        """Spacing для layout'ов — ~30% от font_unit."""
        return max(2, self._font_unit() // 3)

    def _nav_button_size(self) -> int:
        """Высота nav/title кнопок (квадратные для nav)."""
        return max(28, int(self._font_unit() * 1.8))

    def _month_year_row_sizes(self) -> tuple[int, int]:
        """Размеры (title, sub) для строк кнопок месяцев/годов в пикселях.

        Масштабируется от высоты CalendarWidget — на больших диалогах текст крупнее.
        """
        h = max(120, self.height())
        title_px = max(11, h // 35)
        sub_px = max(9, h // 45)
        return title_px, sub_px

    def _set_button_availability(self, btn: Button, is_available: bool) -> None:
        btn.setEnabled(is_available)
        btn.setCursor(
            Qt.CursorShape.PointingHandCursor
            if is_available
            else Qt.CursorShape.ArrowCursor
        )

    def _period_rows(
        self,
        title: str,
        value: str,
        *,
        title_px: int,
        sub_px: int,
        sub_color: QColor,
        strike: bool,
        title_color: QColor | None = None,
    ) -> list[ButtonRow]:
        return [
            ButtonRow(
                title, size=title_px, weight="bold", color=title_color, ratio=0.6,
                strikethrough=strike, italic=strike,
            ),
            ButtonRow(
                value, size=sub_px, color=sub_color, ratio=0.4,
                strikethrough=strike,
            ),
        ]

    def _set_period_disabled_export(self, btn: Button, is_disabled: bool) -> None:
        btn.set_override_bg_color(QColor(self._disabled_bg) if is_disabled else None)

    def _faded_color(self, factor: float = 0.6) -> str:
        bg = QColor(self._bg)
        txt = QColor(self._text)
        r = int(txt.red() * factor + bg.red() * (1 - factor))
        g = int(txt.green() * factor + bg.green() * (1 - factor))
        b = int(txt.blue() * factor + bg.blue() * (1 - factor))
        return QColor(r, g, b).name()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(self._spacing_unit())

        header = QHBoxLayout()
        nav_h = self._nav_button_size()
        self.prev_button = Button(text="‹", size=(nav_h, nav_h), corner_radius=4, variant="surface")
        self.title_button = Button(text="", size=(0, nav_h), corner_radius=4, variant="surface")
        self.next_button = Button(text="›", size=(nav_h, nav_h), corner_radius=4, variant="surface")

        self.title_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        header.addWidget(self.prev_button)
        header.addWidget(self.title_button, 1)
        header.addWidget(self.next_button)
        root.addLayout(header)

        self.prev_button.clicked.connect(self.navigate_previous.emit)
        self.next_button.clicked.connect(self.navigate_next.emit)
        self.title_button.clicked.connect(self.title_clicked.emit)

        self._view_stack = QStackedWidget()
        self._day_view = self._create_day_view()
        self._month_view = self._create_month_view()
        self._year_view = self._create_year_view()
        self._view_stack.addWidget(self._day_view)
        self._view_stack.addWidget(self._month_view)
        self._view_stack.addWidget(self._year_view)
        root.addWidget(self._view_stack, 1)

        self._apply_styles()


    def _apply_styles(self) -> None:
        self.setStyleSheet(f"color: {self._text};")
        if hasattr(self, "_day_view"):
            self._day_view.setStyleSheet(self._day_view_stylesheet())
        for btn in (
            getattr(self, "prev_button", None),
            getattr(self, "title_button", None),
            getattr(self, "next_button", None),
        ):
            if btn is not None:
                btn.setForegroundColor(QColor(self._text))
                btn.setAccentColor(QColor(self._accent))
                btn.update()
        for btn in self._month_buttons + self._year_buttons:
            btn.setForegroundColor(QColor(self._text))
            btn.setAccentColor(QColor(self._accent))
            btn.update()
        for btn in self._day_buttons:
            btn.setForegroundColor(QColor(self._text))
            btn.setAccentColor(QColor(self._accent))
            btn.update()

        if self._last_vm is not None:
            self.update_view(self._last_vm)

    def _day_view_stylesheet(self) -> str:
        return f"""
            QLabel[weekday="true"] {{
                font-weight: bold; color: {self._text};
            }}
        """

    def _create_day_view(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(self._spacing_unit())

        widget.setStyleSheet(self._day_view_stylesheet())

        weekday_grid = QGridLayout()
        for i, name in enumerate(self._weekday_names):
            lbl = QLabel(name)
            lbl.setProperty("weekday", True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            weekday_grid.addWidget(lbl, 0, i)
            self._weekday_labels_widgets.append(lbl)
        layout.addLayout(weekday_grid)

        days_grid = QGridLayout()
        days_grid.setSpacing(max(1, self._spacing_unit() // 2))
        for i in range(42):
            btn = CalendarDayButton()
            btn.date_clicked.connect(self.date_clicked.emit)
            btn.date_context_menu.connect(self.date_context_menu.emit)
            self._day_buttons.append(btn)
            days_grid.addWidget(btn, i // 7, i % 7)
        layout.addLayout(days_grid)
        return widget

    def _create_month_view(self) -> QWidget:
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setSpacing(self._spacing_unit())
        min_w = max(50, self._font_unit() * 4)
        min_h = max(40, int(self._font_unit() * 2.5))
        for i in range(12):
            btn = Button(size=(0, 0), corner_radius=6, variant="surface", parent=widget)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            btn.setMinimumSize(min_w, min_h)
            btn.clicked.connect(lambda _=False, m=i + 1: self.month_selected.emit(self._current_year, m))
            btn.rightClicked.connect(
                lambda m=i + 1: self.month_context_menu.emit(self._current_year, m)
            )
            self._month_buttons.append(btn)
            grid.addWidget(btn, i // 3, i % 3)
        for row in range(4):
            grid.setRowStretch(row, 1)
        return widget

    def _create_year_view(self) -> QWidget:
        widget = QWidget()
        widget.setLayout(QGridLayout())
        widget.layout().setSpacing(self._spacing_unit())
        return widget

    def update_view(self, vm: CalendarViewModel) -> None:
        self._last_vm = vm
        self.title_button.setText(vm.navigation_title)
        self._set_button_availability(self.prev_button, vm.can_go_previous)
        self._set_button_availability(self.next_button, vm.can_go_next)
        self._current_year = vm.current_year

        if vm.view_mode == "days":
            self._view_stack.setCurrentWidget(self._day_view)
            self._update_day_view(vm)
        elif vm.view_mode == "months":
            self._view_stack.setCurrentWidget(self._month_view)
            self._update_month_view(vm)
        elif vm.view_mode == "years":
            self._view_stack.setCurrentWidget(self._year_view)
            self._update_year_view(vm)

    def _update_day_view(self, vm: CalendarViewModel) -> None:
        h = max(120, self.height())
        num_px = max(11, h // 28)
        sub_px = max(8, h // 42)

        for i, day in enumerate(vm.days):
            if i >= len(self._day_buttons):
                break
            btn = self._day_buttons[i]

            if not day.is_in_current_month:
                btn.hide()
                continue
            btn.show()

            is_weekend = day.date.dayOfWeek() >= 6
            has_messages = day.message_count and int(day.message_count) > 0
            btn.set_date(day.date)
            btn.set_weekend(is_weekend, QColor(self._weekend_bg))
            btn.set_disabled_export(day.is_disabled, QColor(self._disabled_bg))
            btn.set_data(bool(has_messages), QColor(self._data_bg))
            self._set_button_availability(btn, day.is_available)
            btn.blockSignals(True)
            btn.setChecked(day.is_selected, emit=False)
            btn.blockSignals(False)

            num = str(day.date.day())
            if day.is_selected and not day.is_disabled:
                selected_text = _contrast_color(QColor(self._accent))
                num_color = selected_text
                sub_text_color = selected_text
            elif day.is_disabled:
                num_color = QColor(self._disabled_text)
                sub_text_color = QColor(self._disabled_text)
            elif has_messages and day.is_available:
                num_color = QColor(self._data_text)
                sub_text_color = QColor(self._data_text)
            else:
                num_color = QColor(self._muted_text)
                sub_text_color = QColor(self._muted_text)

            strike = bool(day.is_disabled)

            if day.is_available:
                # «Балласт» сверху равной высоты с count: цифра остаётся по центру ячейки
                rows = [
                    ButtonRow(str(day.message_count), size=sub_px, color=QColor(0, 0, 0, 0)),
                    ButtonRow(
                        num, size=num_px, color=num_color,
                        strikethrough=strike, italic=strike,
                    ),
                    ButtonRow(
                        str(day.message_count), size=sub_px, color=sub_text_color,
                        strikethrough=strike,
                    ),
                ]
            else:
                rows = [
                    ButtonRow(
                        num, size=num_px, color=num_color,
                        strikethrough=strike, italic=strike,
                    )
                ]

            btn.setRows(rows, compact=True)
            btn.update()

    def _update_month_view(self, vm: CalendarViewModel) -> None:
        sub_color_obj = QColor(self._muted_text)
        title_px, sub_px = self._month_year_row_sizes()
        for mi in vm.months:
            idx = mi.month - 1
            if idx >= len(self._month_buttons):
                continue
            btn = self._month_buttons[idx]
            self._set_button_availability(btn, mi.is_available)
            self._set_period_disabled_export(btn, mi.is_disabled)

            strike = bool(mi.is_disabled)
            row_text = QColor(self._disabled_text if mi.is_disabled else self._text)
            row_sub = QColor(self._disabled_text if mi.is_disabled else sub_color_obj)
            btn.setRows(
                self._period_rows(
                    mi.name,
                    mi.message_count,
                    title_px=title_px,
                    sub_px=sub_px,
                    sub_color=row_sub,
                    strike=strike,
                    title_color=row_text,
                ),
                compact=True,
            )
            btn.setCornerRadiusPx(6)

    def _update_year_view(self, vm: CalendarViewModel) -> None:
        layout = self._year_view.layout()
        while item := layout.takeAt(0):
            if w := item.widget():
                w.deleteLater()

        self._year_buttons.clear()

        sub_color_obj = QColor(self._muted_text)
        title_px, sub_px = self._month_year_row_sizes()
        min_w = max(50, self._font_unit() * 4)
        min_h = max(40, int(self._font_unit() * 2.5))
        row, col = 0, 0
        for yi in vm.years:
            btn = Button(size=(0, 0), corner_radius=6, variant="surface", parent=self._year_view)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            btn.setMinimumSize(min_w, min_h)
            btn.clicked.connect(lambda _=False, y=yi.year: self.year_selected.emit(y))
            btn.rightClicked.connect(
                lambda y=yi.year: self.year_context_menu.emit(y)
            )
            self._set_button_availability(btn, yi.is_available)
            self._set_period_disabled_export(btn, yi.is_disabled)
            self._year_buttons.append(btn)

            layout.addWidget(btn, row, col)

            strike = bool(yi.is_disabled)
            row_text = QColor(self._disabled_text if yi.is_disabled else self._text)
            row_sub = QColor(self._disabled_text if yi.is_disabled else sub_color_obj)
            btn.setRows(
                self._period_rows(
                    yi.name,
                    yi.message_count,
                    title_px=title_px,
                    sub_px=sub_px,
                    sub_color=row_sub,
                    strike=strike,
                    title_color=row_text,
                ),
                compact=True,
            )
            btn.setCornerRadiusPx(6)

            col += 1
            if col > 2:
                col = 0
                row += 1
        layout.setRowStretch(row + 1, 1)

    def set_weekday_labels(self, names: list[str]) -> None:
        self._weekday_names = names
        for i, lbl in enumerate(self._weekday_labels_widgets):
            if i < len(names):
                lbl.setText(names[i])

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self.navigate_previous.emit()
        elif delta < 0:
            self.navigate_next.emit()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Пересчитываем шрифты строк дней/месяцев/годов при изменении размера.
        # Защита от рекурсии: ререндер не должен запускать ресайз заново.
        if getattr(self, "_in_resize_refresh", False):
            return
        if self._last_vm is None:
            return
        self._in_resize_refresh = True
        try:
            mode = self._last_vm.view_mode
            if mode == "days":
                self._update_day_view(self._last_vm)
            elif mode == "months":
                self._update_month_view(self._last_vm)
            elif mode == "years":
                self._update_year_view(self._last_vm)
        finally:
            self._in_resize_refresh = False
