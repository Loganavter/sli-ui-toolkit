# Inputs & Atomic Controls API

Text inputs, toggles, sliders, scroll areas, and small standalone atomic
widgets. See [BUTTON_API.md](BUTTON_API.md) for `Button` and
[LABELS_API.md](LABELS_API.md) for `Text` (the display widget).

## Text & Value Inputs

| Widget | Description |
|--------|-------------|
| `CustomLineEdit` | Painted single-line text input (no `QLineEdit`): the text is rendered by the toolkit painter pipeline, with caret, selection, clipboard, undo/redo and IME implemented in-widget. Rounded input paint, text padding, configurable alignment, theme-updated text color, placeholder, echo mode, validator, clear button. |
| `CheckBox` | Custom-painted checkbox. |
| `RadioButton` | Custom-painted radio button. |
| `Slider` | Custom-painted slider with accent track. |
| `SpinBox` | Custom-painted compact spinbox. |
| `Switch` | Custom-painted toggle switch. |
| `ComboBox` | Full custom-painted combo box with dropdown popup, keyboard typeahead, and keyboard navigation. `showDropdown(focus_index=…)` scrolls a row into view without changing `currentIndex`; `dropdown_row_widget(index)` returns that row for Find Action pulse. `typing_mode="jump"` (default) is file-manager typeahead; `"filter"` narrows the rows — see [Typing into a combo box](#typing-into-a-combo-box). |
| `ScrollableComboBox` | Combo box with mouse-wheel cycling. |
| `TimeLineEdit` | Compact toolkit-painted `HH:mm` input with validation/normalization, two right-side repeatable step buttons, and no native `QTimeEdit` chrome. |

### Typing into a combo box

`ComboBox(typing_mode=…)` / `setTypingMode(…)` picks what typing does:

- **`"jump"` (default)** — file-manager typeahead. The list keeps every row;
  keys extend a buffer (reset after `TYPEAHEAD_TIMEOUT_MS`, 900 ms) and the
  highlight walks to the first row matching the buffer in list order, wrapping
  at the end. Pressing the same key again after the timeout advances to the
  next match. Typing only moves the highlight — `currentIndexChanged` is not
  emitted; `Enter` (or a click) commits the highlighted row, `Up`/`Down` walk
  the highlight, `Backspace` shortens the buffer. The buffer is time-boxed,
  not visibility-bound: a transient close mid-typing keeps it (re-opening
  inside the timeout resumes the query), while `Escape`, an `Enter`/click
  commit, `clearSearch()` or the timeout itself end the session.
- **`"filter"`** — legacy: the visible rows narrow to the matches and the first
  match becomes `currentIndex` immediately.

`setSearchEnabled(False)` disables both typed modes. Hosts that route
unmodified keys globally (canvas shortcuts such as W/A/S/D/Q/E and Space) must
ask the focused widget first: `ComboBox.acceptsTextKeys()` returns whether
typing currently belongs to the field. Without that check the global route
eats the overlay-movement letters before the ComboBox sees them.

`ComboBox` selects on mouse release, the way a list does: a press on the field
opens the list, moving the pointer over the rows highlights the row under it,
and the release commits that row and closes. A release that lands on no row
commits nothing; a release back on the field is the opening click. Nothing in
the gesture moves the pointer (`QCursor.setPos` is a no-op on Wayland) or
depends on the popup moving under it.

`CustomLineEdit` is a painted single-line editor (rendered by the toolkit
painter pipeline; no stock text widget). Its public surface is the standard
line-edit API: `text`/`setText`, `textChanged`/`textEdited`/
`editingFinished`/`returnPressed`, `setPlaceholderText`,
`setValidator`/`hasAcceptableInput`, `setEchoMode` (+ `EchoMode`),
`setClearButtonEnabled`, `setReadOnly`, `setMaxLength`, `selectAll`/
`selectionStart`/`selectedText`/`setSelection`, `copy`/`cut`/`paste`/
`undo`/`redo`, and `cursorPosition`/`setCursorPosition`. The wheel scrolls
an overflowed line horizontally (ignoring the event when the text fits so
an enclosing scroller can take it). `SpinBox`,
`DoubleSpinBox` and `TimeLineEdit` build on it.

Opt-in submit preset — the standard single-shot submit-field contract
(`CustomLineEdit(submit_preset=True)` or `setSubmitPreset(True)`, off by
default): `Tab` on an empty field accepts the placeholder as starting text
(cursor at the end, no selection); `Enter` emits `submitted` with
`text().strip()` (or the placeholder when empty) and rewinds the view and
caret to the start. Plain fields keep exact `QLineEdit` behavior
(`returnPressed`/`editingFinished`, no `submitted` emission).

```python
ask = CustomLineEdit(submit_preset=True)
ask.setPlaceholderText("What matters here?")
ask.submitted.connect(host.ask_question)
```

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

`CustomLineEdit` takes its underline colour from its own token family rather
than from the button family: `input.underline`, with
`input.underline.focused` / `input.underline.disabled` for the two states. A
token, when the palette defines it, owns the colour including its alpha — a
disabled field no longer fakes "dimmer" by fading a still-bright button colour.
Explicit setters (`underline_color`, `focused_underline_color`, …) still win
over a token. Before a palette defines the tokens the field paints exactly what
it painted before, so the tokens can land later without a visual change now.

### State tokens: the field paints with its own keys

A field's text, plate, placeholder and selection wash are input-family palette
keys, not the dialog's or the surface's:

| Key | Painted as |
|---|---|
| `input.background` | the field plate (idle, pressed and expanded alike) |
| `input.text` | the text, the caret, the clear-button ink, the combobox label and chevron |
| `input.text.disabled` | a disabled field's text (and the no-token underline mix) |
| `input.placeholder` | the placeholder |
| `input.selection.background` | the selection wash; an alpha overlay that composites over the plate |
| `input.border.thin`, `input.underline*` | the hairline border and the underline (see above) |

`CustomLineEdit`, `SpinBox` and `TimeLineEdit` (the latter two inherit the line
edit's paint path) and the `ComboBox` field layers read these. A host that restyles its
inputs therefore no longer repaints dialog bodies: `dialog.text` and
`surface.background` are not what the field paints with. `ScrollableComboBox`
reads `input.text` for its label; its plate still comes from the shared button
variant layer (`variant="surface"` → `button.dialog.default.background`), which
is the next migration for that widget.

The dropdown card and its rows are a list surface, not the field — they keep
`list_item.background.hover` / `list_item.text.*`, and the card's plate stays a
neutral `surface.*`. The `ComboBox` field's hover plate still follows
`list_item.background.hover` because the palette ships no input hover key yet.

A palette that predates one of these keys keeps the previous colour at that
site (the field falls back to the enabled ink / the accent wash), so an older
host palette degrades instead of breaking.

### Per-instance colour overrides

One control can diverge from its family without recolouring every control
painted with that token. `TokenOverrideMixin` keeps a per-instance map of
`palette key -> QColor`; the painters resolve through `resolve_token(widget,
key)`, which answers, in order:

```text
explicit constructor/setter colour  >  instance override  >  family token  >  neutral fallback
```

```python
from sli_ui_toolkit.widgets import TokenOverrideMixin, resolve_token

combo.set_token_overrides({"input.background": QColor("#fff4e5")})
combo.token_overrides()                  # {"input.background": QColor(...)}
resolve_token(combo, "input.background") # the override
combo.clear_token_overrides("input.background")  # back to the family token
```

- Values are `QColor` or a colour literal (`"#fff4e5"`). A **palette key is not a
  value** — remapping a token for one widget is this map; remapping it for every
  widget is `ThemeManager.set_color`. A non-colour value is logged and dropped.
- The map is repaint-only: `ThemeManager` palettes are untouched, so two
  instances of the same widget can differ and a theme switch keeps the override.
- A key neither the widget nor the active palette defines logs once and paints
  `NEUTRAL_TOKEN_FALLBACK` (`#808080`) — never a silent black.
- Adopted today: `Button` (`background_color` / `set_background_color` write
  `Button.BACKGROUND_TOKEN`), `CustomLineEdit` (text, plate, placeholder,
  selection wash, all three underline states) — and therefore `SpinBox` /
  `TimeLineEdit`, which inherit its paint path — `CheckBox` (outline, label,
  hover/pressed plate, checked fill, check glyph), `Switch` (track, hover wash,
  knobs, label) and `Slider` (groove, value fill, thumb). Other families adopt the
  mixin when they are touched; `resolve_token` also works on a widget without
  the mixin (it simply has no overrides).

Wheel-scrollable widgets use the shared `wheel_requires_focus` policy. It
defaults to `False`, so wheel interaction works on hover without clicking first.
When a widget handles wheel input, it takes focus so focused visuals activate
consistently. Set it to `True` when a control should only react after focus. The
same policy is available on `Button`, `ComboBox`, `ScrollableComboBox`,
`InstancesCounterButton`, `Slider`, `SpinBox`, and `TimeLineEdit`.

A `ComboBox` open/close cycle is not a focus grant: a list opened while the
field had no focus hands focus back to whatever had it (or to nothing), so the
wheel policy keeps holding after the list closes. That includes the pointer
press that opens the list — Qt focuses the field from the press itself, and the
close still returns focus to the pre-press widget. A list opened from a focused
field (Tab, Enter), or committed with the keyboard after a mouse-opened list,
keeps the field focused when it closes.

```python
spin = SpinBox(wheel_requires_focus=True)
slider = Slider(wheel_requires_focus=True)
button = Button(icon="line_weight", wheel_requires_focus=True)

spin.setWheelRequiresFocus(False)
```

`CheckBox(text=None, parent=None, *, tristate=False, row=False)` and
`RadioButton(text=None, parent=None)` paint themselves through the shared
`Button` pipeline (there is no stock `QCheckBox`/`QRadioButton` underneath).

`CheckBox` answers Qt's check-state surface. Two-state by default
(`setChecked`/`isChecked`); with `tristate=True` — or `setTristate(True)` —
clicks and `Space` cycle Unchecked → PartiallyChecked → Checked,
`checkState()`/`setCheckState()` speak `Qt.CheckState`, and `stateChanged(int)`
fires on every real state change (click, `Space`, `setChecked`,
`setCheckState`, the tri-state cycle) exactly once, in the order a stock
`QCheckBox` uses on that path (`toggled` then `stateChanged` for a gesture and
`setCheckState`; `stateChanged` then `toggled` for a `setChecked` write). The
indeterminate state paints as a dash in a filled indicator; `isChecked()` is
true for it, exactly as in Qt.

`row=True` releases the standalone 36x36 control square: the checkbox keeps its
one-line height but has no minimum width and no maximum size, so a layout can
stretch it across a settings row (horizontal `Minimum`, vertical `Fixed`). The
default geometry and look are unchanged.

```python
check = CheckBox("Enable feature")
tri = CheckBox("Mixed", tristate=True)
tri.setCheckState(Qt.CheckState.PartiallyChecked)
row_check = CheckBox("Enable feature", row=True)
radio = RadioButton("Option A")
```

**State colours are the box's own.** `CheckBox` and `RadioButton` share the
`checkbox.*` family: `checkbox.border` is the outline, `checkbox.text` /
`checkbox.text.disabled` the label, `checkbox.background.hover` /
`checkbox.background.pressed` the indicator's hover and pressed plate, and the
existing `checkbox.check` / `checkbox.background.checked` the checked mark and
fill. `accent` remains the checked radio dot and the focus ring. Overriding
those keys restyles the box without touching dialogs.

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

**State colours are the slider's own.** The groove is `slider.track.unfilled`,
the filled value `slider.track.filled` (`slider.track.hover` while the thumb is
hovered, `slider.track.disabled` when the widget is disabled), the thumb plate
`slider.thumb.outer` / `slider.thumb.disabled`. `accent` stays the edit-mode
affordance and the keyboard focus ring.

**Keyboard edit mode.** A `Slider` changes its value only after an explicit
`Enter`: arrows move the navigation ring until then. `Enter` enters edit mode
(the groove border and thumb ring turn accent), where the arrows and
`W`/`A`/`S`/`D` adjust the value, `Enter` again commits, and `Esc` reverts to
the value captured on entry. Ask for the state with `slider.is_editing()`
(`bool`); navigation sections use it to decide whether arrows belong to the
control or to the ring — a control without `is_editing()` keeps the older
behaviour. See `docs/dev/NAVIGATION.md` §1.1.

`SpinBox(parent=None, default_value=0, *, alignment=Qt.AlignmentFlag.AlignCenter, wheel_requires_focus=False, underline_color=None, underline_thickness=None, focused_underline_color=None, focused_underline_thickness=None, single_step=1, show_step_buttons=False, step_button_width=None, field_height=32)`
shares the alignment/underline/`wheel_requires_focus` knobs documented above
for `CustomLineEdit`, plus range/value control:

```python
spin = SpinBox(default_value=50, alignment=Qt.AlignmentFlag.AlignRight)
spin.setRange(0, 100)
```

`show_step_buttons=True` gives the field Qt's own ▲/▼ gutter — one narrow
column on the right, up above down, `STEP_BUTTON_WIDTH` (20 px by default,
override with `step_button_width`) wide. The arrows step by `singleStep`, go
inert at the range bound on their side, and `setStepButtonsVisible(False)`
returns a plain field; the text area shrinks by exactly the gutter. The gutter
defaults off, so a token-free `SpinBox` keeps its old geometry.
`field_height` (design px, 32 by default) is the field height — the stock
`QSpinBox` row the host mirrors is 29.

```python
count = SpinBox(default_value=4, show_step_buttons=True, field_height=29, step_button_width=20)
```

`DoubleSpinBox` takes the same three arguments plus `single_step` / `decimals`
and steps by its float `singleStep`. The step is never finer than the field can
*show*: `setDecimals(0)` on a field built with `single_step=0.1` raises the step
to `1`, because a press that moves the value by a tenth under a text that stays
`2` is an arrow that does nothing. `setDecimals` re-snaps the stored value onto
that coarser grid. `Stepper` keeps its wide side-by-side gauge (`step=`,
`setStep`) on top of the same shared gutter.

The whole spin family keeps Qt's cursor split: an I-beam over the text (it is
still edited by hand) and an arrow over the ▲/▼ gutter and its edges, decided
by region on hover, so the pointer stops switching within the non-text part of
the field.

`Switch(parent=None)` takes no constructor config beyond `parent` — state
text and its visibility are runtime setters:

```python
switch = Switch()
switch.set_state_texts("Enabled", "Disabled")  # default: "On" / "Off" (translated)
switch.set_show_state_text(False)
```

The switch paints `switch.track.off.border` (the off outline),
`switch.track.hover` (the hover wash), `switch.track.disabled` (a disabled
track), `switch.knob.off` / `switch.knob.on` / `switch.knob.border` and
`switch.text` / `switch.text.disabled`; `accent` remains the checked track.

## Scrolling

| Widget | Description |
|--------|-------------|
| `MinimalistScrollBar` | Thin minimalist scrollbar for custom scroll areas. |
| `OverlayScrollArea` | Scroll area with overlay-style thin scrollbars. |
| `SurfaceScrollArea` | `OverlayScrollArea` that paints its surface from a theme token (default `dialog.background`), or pins viewport + content transparent. |

`MinimalistScrollBar` is a plain `QScrollBar` subclass — `orientation`/
`parent` only (idle/hover/drag thickness are fixed internally).
`OverlayScrollArea` takes a declarative policy object plus individual
kwargs (kwargs win over the config), and every field stays tunable at
runtime through setters:

```python
from sli_ui_toolkit.widgets import OverlayScrollArea, OverlayScrollbarConfig

area = OverlayScrollArea()
area.setWidget(content)
area.set_corner_radius(12)               # default: 8px, clips the viewport
area.set_reserve_scrollbar_space(False)  # bar floats over content instead of reserving a margin
area.set_scrollbar_width(14)             # reserved gutter width, default: MINIMAL_SCROLLBAR_WIDTH (10)
area.set_scrollbar_gap(2)                # gap between bar and right edge, default: 0
area.set_scrollbar_auto_hide(None)       # keep the bar visible once shown (default: 1.2s idle fade)
inset = area.overlay_scrollbar_inset()   # px content should leave clear when space isn't reserved

# ...or as one preset object (ctor wins over per-field kwargs only when set):
policy = OverlayScrollbarConfig(reserve_space=True, reserve_width=10, gap=0, auto_hide_seconds=None)
area = OverlayScrollArea(config=policy)
area.set_scrollbar_config(policy)        # same policy, applied live
policy = area.scrollbar_config()         # read the live policy back

# Getters for every field:
area.reserve_scrollbar_space()           # -> bool
area.scrollbar_width()                   # -> int
area.scrollbar_gap()                     # -> int
area.scrollbar_auto_hide_seconds()       # -> float | None
```

`ListPanel` forwards the same policy without baking in app defaults
(`None` = toolkit defaults); per-field runtime tweaks stay on
`panel.scroll_area.set_*`:

```python
from sli_ui_toolkit.widgets import OverlayScrollbarConfig

panel = ListPanel(..., scrollbar_config=OverlayScrollbarConfig(auto_hide_seconds=None))
panel.set_scrollbar_config(OverlayScrollbarConfig(reserve_space=False))
```

Wheel scrolling is Chrome/Firefox-style: wheel deltas accumulate into a
target scroll position and the viewport eases toward it (~60fps, the ticker
stops when the target is reached). Touchpad `pixelDelta` and `ScrollBegin`
phases are handled; thumb drags, keyboard scrolling, and programmatic
`setValue` cancel the glide and jump directly. The overlay bar fades out
after 1.2s of inactivity and re-fades in on scroll activity (hovering or
dragging it also keeps it around) — `set_scrollbar_auto_hide(None)` disables
that. `MinimalistScrollBar` thumb thickness and opacity interpolate between
idle/hover/drag states instead of snapping.

`overlay_scrollbar_inset()` is a single fixed value — the bar's maximum
width plus a small margin — so content never sits flush against the thumb in
any state, and hosts don't have to chase the idle/hover/drag thickness. It
returns `0` when nothing overflows (or when `reserve_scrollbar_space` is on,
since the bar then gets its own viewport margin).

`SurfaceScrollArea(parent=None, *, surface_token="dialog.background")` is an
`OverlayScrollArea` that also owns its surface. Stock `QScrollArea`
viewports and `setWidget`-flipped content widgets auto-fill the QPalette
`Window` role, which hosts keep darker than the dialog surface token — the
scroll area instead resolves the token to a widget-level
`background-color` stylesheet (cascades to the viewport and the content
widget, survives `QStyle::polish`) and re-tints it on `theme_changed`:

```python
from sli_ui_toolkit.widgets import SurfaceScrollArea

area = SurfaceScrollArea()                 # token fill: dialog.background
area.setWidget(content)
area.set_surface_token("flyout.background")  # any token; re-tinted live
area.set_surface_token(None)                 # transparent: ancestor paints
```

With `surface_token=None` the viewport and the content widget are pinned
transparent, so a host ancestor that paints the surface (e.g. a pane fill)
shows through — the same pattern `SimpleOptionsFlyout` uses for its panel.

The scrollbar's public API is deliberately small:

- `overlay_scrollbar_max_inset()` — the always-on static estimate
  (bar width + gap + margin) for callers that must reserve space before the
  bar's visibility is known (column counting that also determines overflow),
  or when no live `OverlayScrollArea` instance is available.
- `MINIMAL_SCROLLBAR_WIDTH` — the bar's fixed widget width, for positioning
  the bar itself. Gap, margin, thumb thicknesses and track padding are
  internal to the bar.

Widgets that lay out around a `MinimalistScrollBar` — combobox dropdown
overlays, flyout list views, the timeline widget — read these instead of
hardcoding widths.

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
`set_title(title)` updates it at runtime. The frame and the legend read the
dialog family's `dialog.border` / `dialog.text` over `surface.background` (the
file declares `# token-family: dialog`): a group box is dialog-body chrome, and
a palette without a frame family must not repaint it. `CustomGroupBuilder` is a
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
