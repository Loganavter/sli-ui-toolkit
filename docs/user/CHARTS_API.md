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
| `TimelineWidget` | Keyframe timeline with thumbnail strip, grouped tracks, ruler, playhead, zoom/scroll, range selection. Feed via `set_data()` (snapshots or `source: TimelineDataSource`). |
| `TimelineCallbacks` | Callback hooks: `should_show_track`, `visible_channels`, `is_track_active`, `localize_token`, `localize_value`, `lane_value_color`, `prominent_track_ids`. |
| `TimelineDataSource` | Typed `set_data(source=...)` shape (`snapshots`/`fps`/`duration`/`timeline_model`). Import: `sli_ui_toolkit.ui.widgets.composite.timeline_widget.models`. |
| `StripBand` | Opt-in `QRhiWidget` band over the timeline's strip row: the host draws the tiles in one GPU pass (`set_renderer`), the toolkit owns placement (`place`/`band_rect`) and the view (`set_view`/`view`). Wired through `TimelineWidget.enable_strip_band()`. |
| `TIMELINE_TOKENS` | Every `timeline.*` color/alpha token (see wash alphas below). Import: `sli_ui_toolkit.ui.widgets.composite.timeline_widget`. |

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

`TimelineWidget(snapshots=None, parent=None, store=None, callbacks: TimelineCallbacks | None = None, *, accent_color=None, canvas_bg=None, track_bg=None, grid_color=None, text_color=None)`
takes its data hooks through `TimelineCallbacks`, and its actual content
through `set_data(snapshots, fps=None, timeline_model=None, duration=None)`
or the typed overload `set_data(source=...)`, where `source` is a
`TimelineDataSource` (`snapshots`/`fps`/`duration`/`timeline_model`
members; explicit non-`None` arguments win over `source`, non-matching
`source` objects are ignored fail-open).
The five `*_color`/`*_bg` constructor kwargs override the matching
`ThemeManager` token per-instance (`None`, the default, keeps the theme
value); each has a matching runtime setter (`set_accent_color`,
`set_canvas_background_color`, `set_track_background_color`,
`set_grid_color`, `set_text_color`), same shape as `CalendarWidget`'s
color kwargs below. Individual tracks/channels can still override the
accent further via their own `accent_color` field, which wins over the
widget-level `accent_color`.

Zoom is a single scalar committed through `viewport.commit_zoom`:
`set_zoom(zoom, *, anchor="cursor"|"center")` clamps to
`[min_zoom, 1.0]`; `set_pps(pps, *, anchor=...)` converts via
`zoom = pps / base_pps` and delegates to `set_zoom` (zero/negative/NaN
`pps` clamps to min zoom, never crashes).
`get_pixels_per_second()` reads the current `pps = zoom * base_pps`;
`get_visible_thumbnail_frame_indices(overscan_blocks=1)` returns the
representative frame per visible thumbnail block. Signals:
`zoomChanged(float)` on zoom commits, `viewportChanged()` /
`viewportChangedState(object)` on zoom or geometry changes.

`TimelineCallbacks` fields: `should_show_track`, `visible_channels`,
`is_track_active`, `localize_token`, `localize_value`,
`lane_value_color` (per-lane value-color override — a `LaneValueColorFn`
callable or a `TimelineLaneColorDelegate` object with a
`lane_value_color(*, track_id, track_kind, channel_kind, value)` method;
a valid `QColor`/color string wins, `None`/invalid/exception falls
through fail-open), plus `prominent_track_ids: set[str]`.

Every timeline color resolves through `ThemeManager` `timeline.*`
tokens. `TIMELINE_TOKENS` lists them all, including the accent-wash
alphas `timeline.group.wash.track.alpha` (22 light, 46 dark),
`timeline.group.wash.first.alpha` (18, 42),
`timeline.group.wash.channel.alpha` (10, 24), and
`timeline.ruler.minor.tick.alpha` (180, 150). Hosts override any entry
via `register_palettes` (for an alpha token the registered `QColor`'s
alpha channel carries the value); otherwise the per-theme default
applies via `theme.timeline_alpha(tm, token)`, which is also what
`render._wash_alpha` collapses to.

```python
timeline = TimelineWidget(
    callbacks=TimelineCallbacks(prominent_track_ids={"opacity"}),
    accent_color="#3A7AFE",
)
timeline.set_data(snapshots, fps=30, duration=12.5)
timeline.set_grid_color("#444444")
```

### GPU filmstrip band (`StripBand`)

The strip row can be rendered by the host as one GPU pass instead of
per-tile `QPainter.drawPixmap`. The toolkit supplies the widget and the view
plumbing; the host supplies the drawing:

```python
from sli_ui_toolkit.widgets import TimelineWidget


def draw_tiles(command_buffer, band):
    # band.view() -> (scroll_x, zoom); band.band_rect() in parent coords;
    # band.device_pixel_ratio() / band.device_pixel_size() for the texture.
    ...


def drop_textures():
    ...


band = timeline.enable_strip_band(render=draw_tiles, release=drop_textures)
```

`enable_strip_band(render=None, release=None)` creates the child once, injects
the pair, places it over the strip row and returns it; `disable_strip_band()`
drops it and restores the `QPainter` thumbnail path. While the band is visible
the timeline paints the strip background but no tiles underneath it. The band
is a child widget, so it composites above the parent's paint: the ruler, track
rows, gutter labels, footer and scrollbar are outside its rect and untouched,
while anything the parent draws *across* the strip row (the playhead line, the
selection wash) has to be drawn by the `render` callback — it receives the band,
so `band.view()` and `band.band_rect()` are its inputs.

`StripBand(QRhiWidget)` itself:
`set_renderer(render=None, release=None)` / `renderer()`,
`set_view(scroll_x, zoom)` / `view()` (synchronous — no timer, no settle gate),
`set_band_rect(rect)` / `band_rect()` / `place(rect)` (parent coordinates),
`device_pixel_ratio()` (live, unrounded) / `device_pixel_size()`.
`initialize()` creates nothing and `releaseResources()` forwards to the
injected `release`: Qt's callbacks are the only entry points, and there is no
readback (`QImage`/framebuffer grab) anywhere in the band.

A host that drives its own scroll area (or mutates zoom outside `set_zoom`)
calls `timeline.sync_strip_band()` after each tick; the widget already does it
on resize and on every viewport commit. Import the class from
`sli_ui_toolkit.widgets`, `sli_ui_toolkit.ui.widgets.composite`, or
`sli_ui_toolkit.ui.widgets.composite.timeline_widget`.

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
