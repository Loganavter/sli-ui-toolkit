# Data Visualization API

Sunburst/donut charts, a three-level calendar, and a keyframe timeline.

| Widget | Description |
|--------|-------------|
| `SunburstChartWidget` | Sunburst/donut chart (`QGraphicsView`-based). Feed `SunburstSegmentData` list. Signals: `segment_clicked`, `segment_hover_*`. Center text color follows `dialog.text` or `set_center_text_color(...)`. |
| `SunburstSegmentData` | Dataclass: start_angle, end_angle (radians), inner/outer radius, color, node_id. |
| `SunburstSegmentItem` | Individual chart segment (`QGraphicsPathItem`). |
| `CalendarWidget` | Three-level calendar (days/months/years) with `QStackedWidget`. Feed `CalendarViewModel` via `update_view()`. |
| `CalendarDayButton` | Individual day button with `date_clicked`/`date_context_menu` signals. |
| `CalendarDayInfo` / `CalendarMonthInfo` / `CalendarYearInfo` | Per-cell data for calendar. |
| `CalendarViewModel` | Full calendar view state (year, month, day, view_mode, navigation). |
| `TimelineWidget` | Keyframe timeline with thumbnail strip, grouped tracks, ruler, playhead, zoom/scroll, range selection. Feed via `set_data()`. |
| `TimelineCallbacks` | Callback hooks: `should_show_track`, `visible_channels`, `is_track_active`, `localize_token`, `localize_value`, `prominent_track_ids`. |

`SunburstChartWidget(parent=None)` takes no constructor config; appearance
is set through runtime setters and `set_segments(...)`:

```python
from PySide6.QtGui import QColor

from sli_ui_toolkit.widgets import (
    CalendarViewModel,
    CalendarWidget,
    SunburstChartWidget,
    SunburstSegmentData,
    TimelineCallbacks,
    TimelineWidget,
)

chart = SunburstChartWidget()
chart.set_background_color(QColor("#1E1E1E"))
chart.set_gap_color(QColor(0, 0, 0, 80))
chart.set_center_text_color(QColor("#FFFFFF"))
chart.set_segments(
    [
        SunburstSegmentData(
            start_angle=0.0, end_angle=1.57,
            inner_radius=0.4, outer_radius=1.0,
            color="#3A7AFE", label="A", node_id="a",
        )
    ],
    center_text="42%",
    center_font_scale=1.2,  # default: 1.0
)
```

`CalendarWidget(parent=None, *, weekday_labels=None, accent_color=None, hover_color=None, text_color=None, bg_color=None, data_bg=None, weekend_bg=None, disabled_bg=None)`
overrides individual theme tokens per-instance (anything left `None` falls
back to the active theme). Feed view state via `update_view(vm)`.

```python
calendar = CalendarWidget(accent_color="#3A7AFE", weekend_bg="#2A2A2A")
calendar.update_view(
    CalendarViewModel(current_year=2026, current_month=8, view_mode="days")
)
```

`TimelineWidget(snapshots=None, parent=None, store=None, callbacks: TimelineCallbacks | None = None)`
takes its data hooks through `TimelineCallbacks`, and its actual content
through `set_data(snapshots, fps=None, timeline_model=None, duration=None)`:

```python
timeline = TimelineWidget(callbacks=TimelineCallbacks(prominent_track_ids={"opacity"}))
timeline.set_data(snapshots, fps=30, duration=12.5)
```

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
