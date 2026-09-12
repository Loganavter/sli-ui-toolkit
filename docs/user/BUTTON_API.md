# Button Component API Reference

## Quick Start

### Basic Button

```python
from sli_ui_toolkit.ui.widgets.buttons import Button

# Icon button
btn = Button(icon='settings', size=(36, 36))

# Text button
btn = Button(text='Click me', size=(100, 40))

# Icon + text
btn = Button(icon='play', text='Start', size=(100, 40))
```

### Button with Features

```python
# Toggle button
btn = Button(icon='eye_open', toggle=True, size=(36, 36))
btn.toggled.connect(on_toggled)  # Emitted when toggled

# Long-press detection
btn = Button(icon='delete', long_press=True, long_press_ms=600)
btn.longPressed.connect(on_long_press)

# Menu button
menu_items = [
    ('Copy', copy_action),
    ('Paste', paste_action),
    ('Delete', delete_action),
]
btn = Button(icon='menu', menu=menu_items)
btn.menuTriggered.connect(on_menu_item)

# Multi-row text button
rows = [
    ButtonRow(text='Title', size=14, weight='bold'),
    ButtonRow(text='Subtitle', size=11),
]
btn = Button(rows=rows, toggle=True, size=(60, 50))
```

### Button Regions

Use `regions=` when one visual button capsule needs multiple independently
clickable areas. Existing one-region buttons keep the same API and signals.

```python
from sli_ui_toolkit.widgets import Button, ButtonRegion, Divider, VerticalSplit

btn = Button(
    regions=[
        ButtonRegion(id="top", icon="add"),
        ButtonRegion(id="bottom", icon="remove", enabled=can_remove),
    ],
    split=VerticalSplit(),
    divider=Divider(),
    size=(36, 36),
)
btn.regionClicked.connect(handle_region)
```

#### Linking regions into one visual capsule

By default each region tracks its own hover/press state and paints
independently. Pass `group=` on regions that should react as a single capsule:
hover/press on any grouped region mirrors the state to every region sharing the
same group, so they highlight together. Release on a sibling region of the same
group still fires the press region's click. `regionClicked` keeps emitting the
actually-clicked region id; connect once and handle either.

```python
from sli_ui_toolkit.widgets import Button, ButtonRegion, HorizontalSplit
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow

card = Button(
    regions=[
        ButtonRegion(id="icon", icon=icon, group="card", weight=1.0),
        ButtonRegion(
            id="text",
            group="card",
            weight=5.0,
            rows=[
                ButtonRow(text="Title", size=15, weight="bold"),
                ButtonRow(text="Description", size=12),
            ],
        ),
    ],
    split=HorizontalSplit(),
    size=(0, 76),
    corner_radius=10,
)
card.regionClicked.connect(lambda _id: open_card())
```

This unblocks icon-plus-multi-line-text content: keep the icon in its own
region and the rows in a sibling region, link both with `group=`, and the whole
capsule behaves as one button.

The grouped paint shares background/state but each region still rounds its own
rect. For a seamless capsule, set per-region `corner_radii` so the inner edge
is squared and only the outer edge is rounded. Content rendering inside grouped
regions is **not** clipped to the region path — glyph antialiasing and any
overflow can spill into a sibling region of the same group, which keeps text
near the boundary from being visually trimmed.

Regions may also use arbitrary `QPainterPath` hit areas. `rect_fn` supplies the
region's content/bounding rect, `path_fn` supplies the true clickable/painted
shape, and `z_index` controls overlapping hit priority.

```python
from PySide6.QtGui import QPainterPath

def diamond_path(rect):
    path = QPainterPath()
    c = rect.center()
    r = min(rect.width(), rect.height()) * 0.25
    path.moveTo(c.x(), c.y() - r)
    path.lineTo(c.x() + r, c.y())
    path.lineTo(c.x(), c.y() + r)
    path.lineTo(c.x() - r, c.y())
    path.closeSubpath()
    return path

btn = Button(
    regions=[
        ButtonRegion(id="base", icon="remove", rect_fn=lambda r: r, z_index=0),
        ButtonRegion(
            id="center",
            icon="add",
            rect_fn=lambda r: r,
            path_fn=diamond_path,
            z_index=10,
        ),
    ],
    size=(40, 40),
)
```

Background, content, ripple, and hit-testing are clipped to the path. Dividers
are still layout-line based; custom path-shaped separators should be rendered
as a dedicated layer.

#### ButtonRegion fields

`ButtonRegion` mirrors most of `Button`'s own constructor parameters, plus a
few region-only layout fields (`weight`, `rect_fn`, `path_fn`, `z_index`,
`group`, `cursor`). It does **not** carry `size`, `density`,
`wheel_requires_focus`, `defer_click`, `split`, `divider`, `config`, `layers`,
or `parent` — those apply to the whole `Button`, not one region.

| Field | Type | Default |
|-------|------|---------|
| `id` | `str` | *(required)* |
| `weight` | `float` | `1.0` |
| `icon` | `Any` | `None` |
| `text` | `str` | `""` |
| `rows` | `list[ButtonRow] \| None` | `None` |
| `toggle` | `bool` | `False` |
| `long_press` | `bool` | `False` |
| `long_press_ms` | `int` | `600` |
| `menu` | `list[tuple[str, Any]] \| None` | `None` |
| `badge` | `int \| str \| None` | `None` |
| `variant` | `str \| None` | `None` |
| `custom_bg_color` | `QColor \| None` | `None` |
| `override_bg_color` | `QColor \| None` | `None` |
| `override_border_color` | `QColor \| None` | `None` |
| `show_underline` | `bool \| None` | `None` |
| `underline_color` | `Any` | `None` |
| `underline_thickness` | `float \| None` | `None` |
| `icon_size_px` | `int \| None` | `None` |
| `show_strike_through` | `bool` | `False` |
| `enabled` | `bool` | `True` |
| `cursor` | `QCursor \| None` | `None` |
| `rect_fn` | `RectFn \| None` | `None` |
| `path_fn` | `PathFn \| None` | `None` |
| `z_index` | `int` | `0` |
| `corner_radii` | `tuple[int, int, int, int] \| None` | `None` |
| `group` | `str \| None` | `None` |

Note that `checked` is **not** a `ButtonRegion` field — a region's checked
state is runtime-only (see below), not part of its static config.

#### Reading region state: `region_states`, `iter_regions`, `regions()`

```python
# Snapshot of a single region's live ButtonState set (frozenset, read-only)
states = button.region_states("copy")
is_hovered = ButtonState.HOVERED in states

# The current list of ButtonRegion configs (a copy — mutating it does nothing)
current = button.regions()

# Iterate regions during custom painting, each yielded with a scoped DrawContext
for ctx in button.iter_regions(paint_ctx):
    ...
```

#### Updating one region at runtime

Two problems come up once a button has more than one region: changing one
region's static appearance (icon/text/color/...) without touching the others,
and setting a region's checked state from code (not a user click). Both are
solved without hand-rolling list surgery:

```python
# Change one or more static fields on a single region.
# Internally this reconciles through set_regions() by region id, so every
# other region — and this region's own hover/ripple runtime state — is left
# untouched. It is *not* a full re-creation of the region list.
button.update_region("copy", text="Copied!", icon="check")

# Set a region's CHECKED state programmatically — the same effect a user
# click would have on a toggle=True region. Generalizes setChecked(), which
# is hardcoded to the implicit "_main" region and predates multi-region support.
button.setRegionChecked("copy", True)
```

For the common case of syncing several fields on one region — or reading and
writing several fields together — `button.region(region_id)` returns a live
handle that exposes both static config and runtime state as plain attributes,
so callers don't need to know which storage a field lives in:

```python
handle = button.region("copy")
handle.checked            # -> reads runtime ButtonState.CHECKED
handle.checked = True     # -> button.setRegionChecked("copy", True)
handle.text = "Copied!"   # -> button.update_region("copy", text="Copied!")
handle.enabled = False    # -> button.update_region("copy", enabled=False),
                          #    which also flips the region's DISABLED state
handle.hovered            # read-only — driven by mouse events, raises on write
handle.pressed            # read-only, same as above
```

`button.region(region_id)` raises `ValueError` immediately if the id doesn't
exist. `update_region`/`setRegionChecked` are the underlying primitives if you
need to update several regions in a loop without allocating a handle per call.

**Why `set_regions()` is safe to call repeatedly:** it reconciles the new
region list against the old one by `region.id`
(`ButtonController.set_spec`). A region whose id is reused keeps its existing
hover/press/ripple runtime state and any attached capabilities; only regions
whose id disappears from the new list have their runtime state and
capabilities torn down. So replacing one `ButtonRegion` in a list you already
have and calling `set_regions()` again — which is exactly what
`update_region` does — is cheap and non-disruptive, not a full reset.

For new complex controls, prefer the declarative spec API. It keeps content,
style, behavior, layout, and runtime state separate internally:

```python
from sli_ui_toolkit.widgets import (
    Button,
    ButtonSpec,
    ClickBehavior,
    ContentSpec,
    Divider,
    RegionSpec,
    ShapeSpec,
    VerticalSplit,
)

btn = Button.from_spec(
    ButtonSpec(
        regions=(
            RegionSpec(id="add", content=ContentSpec(icon="add")),
            RegionSpec(
                id="amount",
                content=ContentSpec(icon="settings"),
                behaviors=(
                    ClickBehavior(action="amount.reset"),
                ),
            ),
        ),
        split=VerticalSplit(),
        divider=Divider(),
        shape=ShapeSpec(size=(36, 36), corner_radius=6, icon_size=18),
    )
)
btn.regionClicked.connect(handle_region)
btn.actionTriggered.connect(handle_action)
```

Need scroll-wheel-driven behavior on a region? Attach a custom
`ButtonCapability` that implements `handle_wheel_event()` — see
[Capability Management](#capability-management) below and the
"Wheel counter (app-level recipe)" demo card in `demo/pages/buttons_page.py`.

## Constructor Parameters

```python
Button(
    icon: Any = None,
    text: str = "",
    rows: list[ButtonRow] | None = None,
    toggle: bool = False,
    long_press: bool = False,
    long_press_ms: int = 600,
    badge: int | None = None,
    show_underline: bool = False,
    menu: list[tuple[str, Any]] | None = None,
    size: tuple[int, int] = (36, 36),
    icon_size: int = 22,
    corner_radius: int | None = None,
    variant: str = "default",
    density: str = "normal",
    defer_click: bool = False,
    regions: list[ButtonRegion] | None = None,
    split: SplitLayout | None = None,
    divider: Divider | None = None,
    spec: ButtonSpec | None = None,
    config: ButtonConfig | None = None,
    parent: QWidget | None = None,
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `icon` | `Any` | `None` | Icon name or tuple of (unchecked, checked) |
| `text` | `str` | `""` | Single-line text content |
| `rows` | `list[ButtonRow]` | `None` | Multi-line text with individual styling |
| `toggle` | `bool` | `False` | Toggleable button (on/off state) |
| `long_press` | `bool` | `False` | Detect press-and-hold |
| `long_press_ms` | `int` | `600` | Time (ms) before long-press triggers |
| `badge` | `int` | `None` | Number badge (top-right corner) |
| `show_underline` | `bool` | `False` | Show underline decoration |
| `menu` | `list[tuple]` | `None` | Dropdown menu items: [(label, action), ...] |
| `size` | `(int, int)` | `(36, 36)` | Fixed size (width, height) |
| `icon_size` | `int` | `22` | Icon pixel size |
| `corner_radius` | `int` | `None` | Corner radius (auto-calculated if None) |
| `variant` | `str` | `"default"` | Color variant: "default", "surface", "ghost". Deprecated compatibility values warn. |
| `density` | `str` | `"normal"` | Visual density: "normal", "compact" |
| `defer_click` | `bool` | `False` | Emit `clicked`/`shortClicked` on the next event-loop tick (see [Press animations & blocking handlers](#press-animations--blocking-handlers)) |
| `regions` | `list[ButtonRegion]` | `None` | Optional multi-region model. If omitted, Button creates a single `_main` region from the legacy parameters. |
| `split` | `SplitLayout` | `None` | Geometry strategy for regions: `HorizontalSplit`, `VerticalSplit`, `GridSplit`, or `CustomSplit`. |
| `divider` | `Divider` | `None` | Optional whole-widget divider between regions. |
| `spec` | `ButtonSpec` | `None` | Declarative control description. Prefer `Button.from_spec(spec)` for new complex controls. |
| `config` | `ButtonConfig` | `None` | Use ButtonConfig dataclass instead of params |
| `parent` | `QWidget` | `None` | Parent widget |

## Signals

```python
button = Button(...)

# Emitted when clicked (left button)
button.clicked.connect(on_clicked)

# Emitted on left button press
button.pressed.connect(on_pressed)

# Emitted on left button release
button.released.connect(on_released)

# Emitted when toggled (toggle=True only)
button.toggled.connect(lambda checked: print(f"Toggled: {checked}"))

# Emitted after long press timeout (long_press=True only)
button.longPressed.connect(on_long_press)

# Emitted on right click
button.rightClicked.connect(on_right_click)

# Emitted on middle click
button.middleClicked.connect(on_middle_click)

# Emitted when menu item selected (menu=items only)
button.menuTriggered.connect(on_menu_item)

# Emitted immediately after clicked (useful for rapid click detection)
button.shortClicked.connect(on_short_click)

# Multi-region signals
button.regionClicked.connect(lambda region_id: ...)
button.regionPressed.connect(lambda region_id: ...)
button.regionReleased.connect(lambda region_id: ...)
button.regionToggled.connect(lambda region_id, checked: ...)
button.regionLongPressed.connect(lambda region_id: ...)
button.regionMenuTriggered.connect(lambda region_id, data: ...)
button.actionTriggered.connect(lambda action_id, data: ...)
```

## Properties & Methods

### State Management

```python
# Toggle state ("_main" region on single-region buttons)
button.setChecked(True)          # Set toggle state (if toggle=True)
is_checked = button.isChecked()  # Get toggle state

# Multi-region equivalents — see "Updating one region at runtime" above
button.setRegionChecked("copy", True)
button.update_region("copy", enabled=False, text="Copied!")
button.region("copy").checked = True
```

### Visual Properties

```python
# Badge (number indicator)
button.setBadge(5)               # Show "5" badge
button.setBadge(None)            # Hide badge
button.setBadgeStyle(filled=True)
button.setBadgeStyle(
    filled=True,
    background_color=QColor("#D93025"),
    border_color=QColor("#D93025"),
    text_color=QColor("#ffffff"),
)

# Text content
button.setText("New text")
button.getText()

# Rows (multi-line)
rows = [
    ButtonRow(text='Line 1', size=14, weight='bold'),
    ButtonRow(text='Line 2', size=11),
]
button.setRows(rows, compact=False)  # compact=True centers block vertically

# Icon
button.setIcon('new_icon_name')

# Colors
button.set_override_bg_color(QColor('blue'))  # Override background

# Underline
button.setShowUnderline(True)
button.setUnderlineColor(QColor('red'))
button.setShowUnderline(False)

# Strike-through (error indicator)
button.set_show_strike_through(True)

# Variant
button.setVariant('surface')
variant = button.getVariant()

# Size & spacing
button.setIconSize(QSize(24, 24))
button.setIconSizePx(24)
button.setCornerRadiusPx(8)

# Density
button.setDensity('compact')
density = button.getDensity()

# Footer mode (visual hint)
button.set_footer_mode(True)
```

### Capability Management

```python
from sli_ui_toolkit.ui.widgets.buttons.capabilities import (
    ButtonCapability, LongPressCapability, MenuCapability
)

# Attach a capability
button.attach_capability(MenuCapability([("Open", "open")]), region_id="menu")

# Get attached capability
menu_cap = button.get_capability(MenuCapability, region_id="menu")
if menu_cap:
    # ... use capability

# Detach capability
button.detach_capability(MenuCapability, region_id="menu")
```

New controls should usually describe behavior with `ButtonSpec` instead of
attaching capabilities manually. Direct capability attachment remains supported
for compatibility and specialized toolkit internals.

`BehaviorSpec` subclasses (`ClickBehavior`, `ToggleBehavior`,
`LongPressBehavior`, `MenuBehavior`) may carry `action=`, `data=`, and
`callback=`. When a behavior is triggered, `Button` emits
`actionTriggered(action_id, data)` and calls the callback if one was supplied.

The toolkit does not ship a built-in scroll/value-counter capability. Subclass
`ButtonCapability` and override `handle_wheel_event(event) -> bool` to react to
wheel input on a region — `Button`'s `wheelEvent` duck-types over every
capability attached to the target region and calls the hook automatically. See
the "Wheel counter (app-level recipe)" card in `demo/pages/buttons_page.py` for
a full example (custom capability + custom `Layer` for value rendering).

### Menu Management

```python
# Set/update menu items
menu_items = [('Item 1', action1), ('Item 2', action2)]
button.set_menu_items(menu_items)

# Show menu programmatically
button.show_menu()
```

## ButtonRow API

```python
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow

row = ButtonRow(
    text='Row text',
    size=12,                                    # Font pixel size
    weight='normal',                            # 'normal' or 'bold'
    color=QColor('blue'),                       # Text color (optional)
    ratio=0.5,                                  # Height fraction of button
    h_align=Qt.AlignmentFlag.AlignHCenter,     # Horizontal alignment
)
```

## ButtonConfig API

```python
from sli_ui_toolkit.ui.widgets.buttons import ButtonConfig

config = ButtonConfig(
    icon='settings',
    text='Settings',
    rows=None,
    toggle=False,
    long_press=False,
    long_press_ms=600,
    badge=None,
    show_underline=False,
    menu=None,
    size=(36, 36),
    icon_size=22,
    corner_radius=None,
    variant='default',
    density='normal',
)

# Use config instead of parameters
button = Button(config=config)
```

## Variants

Predefined color schemes (use `setVariant()` or `variant=` param):

```python
# Available variants
"default"    # Toolbar/toggle appearance
"surface"    # Neutral surface action
"ghost"      # Transparent until hovered
```

`"primary"` is a deprecated compatibility alias for `"surface"` and emits
`DeprecationWarning`. Legacy button widget names such as `AutoRepeatButton`,
`IconButton`, `ToolButton`, and `ButtonGroupContainer` are compatibility
lookups only and will be removed in `0.3.0`.

## Density

Visual spacing/sizing (use `setDensity()` or `density=` param):

```python
"normal"     # Default spacing and size
"compact"    # Reduced spacing (for tight layouts)
```

## Examples

### Toggle with Badge

```python
btn = Button(
    icon=('eye_open', 'eye_closed'),
    toggle=True,
    badge=3,
    size=(40, 40),
)
btn.toggled.connect(lambda checked: print(f"Visible: {checked}"))
```

### Menu Button

```python
def on_copy():
    print("Copied!")

def on_paste():
    print("Pasted!")

btn = Button(
    icon='edit',
    menu=[
        ('Copy', on_copy),
        ('Paste', on_paste),
        ('Delete', lambda: print("Deleted!")),
    ],
)
btn.menuTriggered.connect(lambda action: action())
```

### Multi-row Calendar Button

```python
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow

btn = Button(
    rows=[
        ButtonRow(text='25', size=16, weight='bold'),
        ButtonRow(text='Mon', size=10),
    ],
    toggle=True,
    size=(50, 70),
    corner_radius=4,
    variant='ghost',
)
btn.toggled.connect(lambda checked: print(f"Date selected: {checked}"))
```

### Custom Styling

```python
btn = Button(
    text='Custom',
    size=(100, 40),
    variant='surface',
)

# Override colors
btn.set_override_bg_color(QColor('#0066cc'))      # Background

# Add underline
btn.setShowUnderline(True)
btn.setUnderlineColor(QColor('white'))

# Add error indicator
btn.set_show_strike_through(True)
```

### Long-Press Action

```python
btn = Button(
    icon='delete',
    long_press=True,
    long_press_ms=800,
    size=(36, 36),
)

def on_delete():
    print("Deleted!")

btn.clicked.connect(lambda: print("Short click"))
btn.longPressed.connect(on_delete)
```

## Backwards Compatibility

Old code still works:

```python
# These still work from button.py attributes
_lp_timer = btn._lp_timer               # Returns LongPressCapability's timer
```

## Integration with CalendarDayButton

```python
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.day_button import CalendarDayButton

day_btn = CalendarDayButton()
day_btn.set_date(QDate(2026, 6, 1))
day_btn.set_weekend(True, QColor(100, 150, 255))  # Light blue
day_btn.set_data(True, QColor(0, 200, 0))        # Has data, green

# New painter architecture handles rendering
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Menu not showing | Verify `menu=[(label, action), ...]` param |
| Long press not triggering | Increase `long_press_ms` (default 600) |
| Colors not applying | Use `set_override_bg_color()` or variant |
| Underline not visible | Call `setShowUnderline(True)` |

## Press animations & blocking handlers

Buttons play a Material-style ripple animation from the press point. The ripple
is driven by a `QTimer` that ticks every ~16 ms on the **main GUI thread**, same
as every other Qt animation. Duration ~280 ms, alpha ~12 % (light) / ~16 %
(dark) — aligned with the Material Design 3 motion tokens.

### Why animations may freeze

If a `clicked` handler does heavy synchronous work (e.g. re-applies the QSS
theme to all widgets, scans the filesystem, rebuilds a large model), the GUI
event loop is blocked until the handler returns. While it is blocked:

- the ripple `QTimer` cannot fire — the wave appears to stutter or freeze on
  whatever frame the press caught;
- hover transitions, scroll popups, and any other animation stalls too.

This is a **Qt-wide constraint**, not a bug in the ripple layer.

### `defer_click=True`

Pass `defer_click=True` to schedule the `clicked` / `shortClicked` signals on
the **next event-loop tick** via `QTimer.singleShot(0, …)`. The press visually
completes (ripple, depress, release event) before the handler starts.

```python
btn = Button(
    text="Switch theme",
    variant="surface",
    defer_click=True,   # let the ripple frame land before the heavy slot
)
btn.clicked.connect(theme_manager.toggle)   # slow: re-applies QSS everywhere
```

What this **does**: gives the ripple at least one frame to render before the
blocking work starts, so the press feels acknowledged.

What this **does not** do: it does not make the handler asynchronous. The
animation will still stall mid-flight once the slow slot starts running.

### Ripple color: overlay vs state-transition gradient

By default the ripple is a semi-transparent black (light theme) or white (dark
theme) overlay — a standard M3 "state layer".

For toggle buttons it auto-upgrades to a **state-layer transition**: during
the ripple the button is repainted with the previous state's background, and
a circle of the next state's background grows from the click point outward.
When the animation ends, the BackgroundLayer continues painting the new state
seamlessly. Non-toggle buttons keep the overlay behaviour unless overridden.

Explicit override for any button:

```python
btn = Button(text="Apply", variant="surface")
btn.setRippleColors(QColor("#e0e0e0"), QColor("#0078d4"))
# … later
btn.clearRippleColors()   # back to default (overlay or auto-toggle gradient)
```

Both colors must be non-None to enable the gradient mode; passing a None for
either falls back to the default. Alpha is interpolated along with RGB.

### Better: move the work off the GUI thread

For truly responsive feedback, run the heavy logic in a `QThread`, a
`QtConcurrent`-style worker, or chunk it with `QCoreApplication.processEvents()`
between steps. Operations that are inherently GUI-thread-bound (re-applying
QSS, mutating widget trees) cannot be moved off-thread and will always stall
animations; `defer_click=True` is the best mitigation available there.

## See Also

- [Architecture](../dev/ARCHITECTURE.md) - Toolkit and button subsystem boundaries
