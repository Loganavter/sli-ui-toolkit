# Inputs & Atomic Controls API

Text inputs, toggles, sliders, scroll areas, and small standalone atomic
widgets. See [BUTTON_API.md](BUTTON_API.md) for `Button` and
[LABELS_API.md](LABELS_API.md) for `Label`.

## Text & Value Inputs

| Widget | Description |
|--------|-------------|
| `CustomLineEdit` | Themed line edit with rounded input paint, text padding, configurable text alignment, theme-updated text color, and focus normalization. |
| `CheckBox` | Custom-painted checkbox. |
| `RadioButton` | Custom-painted radio button. |
| `Slider` | Custom-painted slider with accent track. |
| `SpinBox` | Custom-painted compact spinbox. |
| `Switch` | Custom-painted toggle switch. |
| `ComboBox` | Full custom-painted combo box with dropdown popup, type-to-search matching, and keyboard navigation. `showDropdown(focus_index=…)` scrolls a row into view without changing `currentIndex`; `dropdown_row_widget(index)` returns that row for Find Action pulse. |
| `ScrollableComboBox` | Combo box with mouse-wheel cycling. |
| `TimeLineEdit` | Compact toolkit-painted `HH:mm` input with validation/normalization, two right-side repeatable step buttons, and no native `QTimeEdit` chrome. |

Text inputs accept Qt alignment flags or string alignment values:

```python
name = CustomLineEdit(alignment="left")
time = TimeLineEdit(alignment="center", wheel_requires_focus=False)
count = SpinBox(default_value=42, alignment="right", wheel_requires_focus=False)

name.setTextAlignment("center")
time.setStepButtonsVisible(False)
```

Toolkit-painted inputs expose the same underline configuration names as
`Button`: `underline_color`, `underline_thickness`, `setUnderlineColor(...)`,
and `setUnderlineThickness(...)`. `CustomLineEdit`, `SpinBox`, `TimeLineEdit`,
and `ComboBox` support these options.

```python
name = CustomLineEdit(underline_color=QColor("#0078D4"), underline_thickness=1.5)
combo = ComboBox(underline_thickness=1.0)

name.setUnderlineColor(QColor("#0078D4"))
combo.setUnderlineThickness(1.5)
```

`CustomLineEdit`, `SpinBox`, `TimeLineEdit`, and `ComboBox` also support
separate focused underline styling. The base `underline_*` options apply when
the field is not focused; focused options apply only while the field has focus.

```python
name = CustomLineEdit(
    underline_color=QColor("#808080"),
    underline_thickness=1.0,
    focused_underline_color=QColor("#0078D4"),
    focused_underline_thickness=1.5,
)

name.setFocusedUnderlineColor(QColor("#0078D4"))
name.setFocusedUnderlineThickness(1.5)
```

Wheel-scrollable widgets use the shared `wheel_requires_focus` policy. It
defaults to `False`, so wheel interaction works on hover without clicking first.
When a widget handles wheel input, it takes focus so focused visuals activate
consistently. Set it to `True` when a control should only react after focus. The
same policy is available on `Button`, `ComboBox`, `ScrollableComboBox`,
`InstancesCounterButton`, `Slider`, `SpinBox`, and `TimeLineEdit`.

```python
spin = SpinBox(wheel_requires_focus=True)
slider = Slider(wheel_requires_focus=True)
button = Button(icon="line_weight", wheel_requires_focus=True)

spin.setWheelRequiresFocus(False)
```

`CheckBox(text=None, parent=None)` and `RadioButton(text=None, parent=None)`
are theme-painted repaints of `QCheckBox`/`QRadioButton` — the only
custom-typed constructor arguments are `text`/`parent`; everything else
(tristate, `setChecked`, `setCheckState`, ...) is the standard Qt API.

```python
check = CheckBox("Enable feature")
radio = RadioButton("Option A")
```

`Slider` adds track/thumb geometry and an optional custom track painter on
top of `QSlider`:

```python
from PySide6.QtCore import Qt

slider = Slider(
    Qt.Orientation.Horizontal,
    track_thickness=6,       # default: 5px
    thumb_radius=10,         # default: 8px
    show_value_fill=False,   # hide the accent "progress" overlay
    wheel_requires_focus=True,
)
slider.setTrackPainter(lambda painter, rect: ...)  # paint gradient/checkerboard content
slider.setShowValueFill(False)
slider.setTrackThickness(8)
slider.setThumbRadius(9)
```

`SpinBox(parent=None, default_value=0, *, alignment=Qt.AlignmentFlag.AlignCenter, wheel_requires_focus=False, underline_color=None, underline_thickness=None, focused_underline_color=None, focused_underline_thickness=None)`
shares the alignment/underline/`wheel_requires_focus` knobs documented above
for `CustomLineEdit`, plus range/value control:

```python
spin = SpinBox(default_value=50, alignment=Qt.AlignmentFlag.AlignRight)
spin.setRange(0, 100)
```

`Switch(parent=None)` takes no constructor config beyond `parent` — state
text and its visibility are runtime setters:

```python
switch = Switch()
switch.set_state_texts("Enabled", "Disabled")  # default: "On" / "Off" (translated)
switch.set_show_state_text(False)
```

## Scrolling

| Widget | Description |
|--------|-------------|
| `MinimalistScrollBar` | Thin minimalist scrollbar for custom scroll areas. |
| `OverlayScrollArea` | Scroll area with overlay-style thin scrollbars. |

Neither widget takes constructor kwargs beyond the standard
`orientation`/`parent` (`MinimalistScrollBar`, a plain `QScrollBar`
subclass — idle/hover/drag thickness are fixed internally) and `parent`
(`OverlayScrollArea`). `OverlayScrollArea` behavior is configured through
runtime setters:

```python
from sli_ui_toolkit.widgets import OverlayScrollArea

area = OverlayScrollArea()
area.setWidget(content)
area.set_corner_radius(12)               # default: 8px, clips the viewport
area.set_reserve_scrollbar_space(False)  # bar floats over content instead of reserving a margin
inset = area.overlay_scrollbar_inset()   # px content should leave clear when space isn't reserved
```

## Other Atomic

| Widget | Description |
|--------|-------------|
| `LoadingSpinner` | Animated conical-gradient loading spinner. |
| `CustomGroupWidget` / `CustomGroupBuilder` | Grouped widget container with builder pattern. |

`LoadingSpinner(parent=None)` has no constructor config beyond `parent` —
size (fixed 40x40 px) and animation speed (15ms tick) are fixed; use
`start()`/`stop()`/`is_spinning()` to control the animation.

`CustomGroupWidget(title_text="", parent=None)` draws a titled border frame
around whatever is added via `add_widget(widget)`/`add_layout(layout)`;
`set_title(title)` updates it at runtime. `CustomGroupBuilder` is a
chainable wrapper over the same API:

```python
from sli_ui_toolkit.widgets import CustomGroupBuilder, CustomGroupWidget, LoadingSpinner

spinner = LoadingSpinner()
spinner.start()

group = CustomGroupWidget("Output")
group.add_widget(some_widget)

group2 = (
    CustomGroupBuilder()
    .add(widget_a)
    .add_layout(some_layout)
    .build(title="Advanced")
)
```

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
