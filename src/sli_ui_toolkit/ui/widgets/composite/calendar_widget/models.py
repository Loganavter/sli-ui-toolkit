from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QDate

@dataclass
class CalendarDayInfo:
    date: QDate
    message_count: str = ""
    is_available: bool = False
    is_disabled: bool = False
    is_selected: bool = False
    is_in_current_month: bool = True

@dataclass
class CalendarMonthInfo:
    year: int
    month: int
    name: str
    message_count: str = ""
    is_available: bool = False
    is_disabled: bool = False

@dataclass
class CalendarYearInfo:
    year: int
    name: str
    message_count: str = ""
    is_available: bool = False
    is_disabled: bool = False

@dataclass
class CalendarViewModel:
    current_year: int
    current_month: int
    current_day: int = 1

    view_mode: str = "days"

    days: list[CalendarDayInfo] = field(default_factory=list)
    months: list[CalendarMonthInfo] = field(default_factory=list)
    years: list[CalendarYearInfo] = field(default_factory=list)

    can_go_previous: bool = True
    can_go_next: bool = True
    navigation_title: str = ""

    def get_current_date(self) -> QDate:
        return QDate(self.current_year, self.current_month, self.current_day)


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def build_default_view_model(year: int, month: int, day: int = 1) -> "CalendarViewModel":
    """Zero-config view-model that fills 6×7 days for the given month.

    All days in the current month are available; padding days from neighbouring
    months are present but flagged ``is_in_current_month=False`` so the widget
    hides them.
    """
    first = QDate(year, month, 1)
    # QDate.dayOfWeek: Monday=1 … Sunday=7 → leading blanks before day 1.
    leading_blanks = first.dayOfWeek() - 1
    grid_start = first.addDays(-leading_blanks)

    days: list[CalendarDayInfo] = []
    for i in range(42):
        d = grid_start.addDays(i)
        in_month = (d.month() == month and d.year() == year)
        days.append(
            CalendarDayInfo(
                date=d,
                message_count="",
                is_available=in_month,
                is_disabled=False,
                is_selected=(in_month and d.day() == day),
                is_in_current_month=in_month,
            )
        )

    title = f"{_MONTH_NAMES[month - 1]} {year}"
    return CalendarViewModel(
        current_year=year,
        current_month=month,
        current_day=day,
        view_mode="days",
        days=days,
        navigation_title=title,
    )
