"""Misc page — Calendar, PreviewPanel и одиночные виджеты."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.composite import PreviewPanel
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.models import (
    CalendarMonthInfo,
    CalendarViewModel,
    CalendarYearInfo,
    build_default_view_model,
)
from sli_ui_toolkit.widgets import (
    Button,
    CalendarWidget,
    DragGhostWidget,
    Label,
)

from demo.components import GalleryPage


class MiscPage(GalleryPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Misc",
            subtitle="Календарь, preview, drag-ghost и прочие одиночные виджеты.",
            source_file=__file__,
            parent=parent,
        )

        cal = CalendarWidget()
        cal.setMinimumSize(320, 280)
        self._cal_state = QDate.currentDate()
        self._cal_mode = "days"
        self._cal_disabled_days: set[tuple[int, int, int]] = set()
        self._cal_disabled_months: set[tuple[int, int]] = set()
        self._cal_disabled_years: set[int] = set()

        def _refresh_calendar():
            if self._cal_mode == "months":
                vm = CalendarViewModel(
                    current_year=self._cal_state.year(),
                    current_month=self._cal_state.month(),
                    current_day=self._cal_state.day(),
                    view_mode="months",
                    months=[
                        CalendarMonthInfo(
                            year=self._cal_state.year(),
                            month=i,
                            name=QDate(self._cal_state.year(), i, 1).toString("MMM"),
                            message_count=str(i * 3),
                            is_available=True,
                            is_disabled=(self._cal_state.year(), i) in self._cal_disabled_months,
                        )
                        for i in range(1, 13)
                    ],
                    navigation_title=str(self._cal_state.year()),
                )
            elif self._cal_mode == "years":
                start = self._cal_state.year() - 5
                vm = CalendarViewModel(
                    current_year=self._cal_state.year(),
                    current_month=self._cal_state.month(),
                    current_day=self._cal_state.day(),
                    view_mode="years",
                    years=[
                        CalendarYearInfo(
                            year=y,
                            name=str(y),
                            message_count=str((y - start + 1) * 9),
                            is_available=True,
                            is_disabled=y in self._cal_disabled_years,
                        )
                        for y in range(start, start + 12)
                    ],
                    navigation_title=f"{start}-{start + 11}",
                )
            else:
                vm = build_default_view_model(
                    self._cal_state.year(),
                    self._cal_state.month(),
                    self._cal_state.day(),
                )
                for item in vm.days:
                    key = (item.date.year(), item.date.month(), item.date.day())
                    item.is_disabled = key in self._cal_disabled_days
            cal.update_view(vm)

        def _prev():
            if self._cal_mode == "years":
                self._cal_state = self._cal_state.addYears(-12)
            elif self._cal_mode == "months":
                self._cal_state = self._cal_state.addYears(-1)
            else:
                self._cal_state = self._cal_state.addMonths(-1)
            _refresh_calendar()

        def _next():
            if self._cal_mode == "years":
                self._cal_state = self._cal_state.addYears(12)
            elif self._cal_mode == "months":
                self._cal_state = self._cal_state.addYears(1)
            else:
                self._cal_state = self._cal_state.addMonths(1)
            _refresh_calendar()

        def _title_clicked():
            self._cal_mode = "months" if self._cal_mode == "days" else "years"
            _refresh_calendar()

        def _month_selected(year: int, month: int):
            self._cal_state = QDate(year, month, min(self._cal_state.day(), QDate(year, month, 1).daysInMonth()))
            self._cal_mode = "days"
            _refresh_calendar()

        def _year_selected(year: int):
            self._cal_state = QDate(year, self._cal_state.month(), 1)
            self._cal_mode = "months"
            _refresh_calendar()

        def _toggle_day(date: QDate):
            key = (date.year(), date.month(), date.day())
            if key in self._cal_disabled_days:
                self._cal_disabled_days.remove(key)
            else:
                self._cal_disabled_days.add(key)
            _refresh_calendar()

        def _toggle_month(year: int, month: int):
            key = (year, month)
            if key in self._cal_disabled_months:
                self._cal_disabled_months.remove(key)
            else:
                self._cal_disabled_months.add(key)
            _refresh_calendar()

        def _toggle_year(year: int):
            if year in self._cal_disabled_years:
                self._cal_disabled_years.remove(year)
            else:
                self._cal_disabled_years.add(year)
            _refresh_calendar()

        cal.navigate_previous.connect(_prev)
        cal.navigate_next.connect(_next)
        cal.title_clicked.connect(_title_clicked)
        cal.month_selected.connect(_month_selected)
        cal.year_selected.connect(_year_selected)
        cal.date_clicked.connect(lambda date: (setattr(self, "_cal_state", date), setattr(self, "_cal_mode", "days"), _refresh_calendar()))
        cal.date_context_menu.connect(_toggle_day)
        cal.month_context_menu.connect(_toggle_month)
        cal.year_context_menu.connect(_toggle_year)
        _refresh_calendar()
        self.add_card("CalendarWidget", cal, "Клик по заголовку переключает дни/месяцы/годы; правый клик toggles disabled state.")

        try:
            preview = PreviewPanel("File preview", show_actions=True)
            preview.setMinimumHeight(120)
            self.add_card("PreviewPanel", preview, "Панель просмотра с edit/save/revert.")
        except Exception as e:
            self.add_card("PreviewPanel", Label(f"requires setup: {e}", pixel_size=11))

        try:
            ghost_holder = QWidget()
            gh = QHBoxLayout(ghost_holder)
            gh.setContentsMargins(0, 0, 0, 0)
            ghost = DragGhostWidget(ghost_holder)
            gh.addWidget(ghost)
            gh.addWidget(Label("Используется во время drag&drop", pixel_size=11))
            gh.addStretch()
            self.add_card("DragGhostWidget", ghost_holder)
        except Exception:
            pass

        self.add_stretch()
