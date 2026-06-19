from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor

from sli_ui_toolkit.ui.widgets.composite.calendar_widget.day_button import CalendarDayButton


def test_calendar_day_button_does_not_take_focus(qapp):
    button = CalendarDayButton()

    assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_calendar_day_button_starts_ripple_on_press(qtbot):
    button = CalendarDayButton()
    button.setFixedSize(48, 48)
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)

    qtbot.mousePress(button, Qt.MouseButton.LeftButton, pos=QPoint(24, 24))

    assert button._ripple.is_active()


def test_calendar_day_button_selection_wins_over_data_background(qapp):
    button = CalendarDayButton()
    data_color = QColor("#808080")

    button.set_data(True, data_color)
    assert button.getBackgroundColor() == data_color
    assert button._override_bg_color is None

    button.setChecked(True, emit=False)
    assert button.getBackgroundColor() is None
    assert button._override_bg_color is not None
