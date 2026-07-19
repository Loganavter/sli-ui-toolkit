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

# Popup menu (app-owned — Button has no built-in menu)
from sli_ui_toolkit.widgets import entries_from_callbacks, popup_context_menu_for_anchor

menu_items = [('Copy', copy_action), ('Paste', paste_action)]
btn = Button(icon='menu', size=(36, 36))
btn.clicked.connect(
    lambda: popup_context_menu_for_anchor(
        btn.window(), btn, entries_from_callbacks(menu_items)
    )
)

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

By default each region tracks its own hover/press/checked state and paints
independently. Pass `group=` on regions that should react as a single capsule:
hover, press, and checked on any grouped region mirror the state to every
region sharing the same group, so they highlight together. Release on a
sibling region of the same group still fires the press region's click. `regionClicked` keeps emitting the
actually-clicked region id; connect once and handle either.

Do **not** put a real layout gap (`HorizontalSplit(gap=…)` or a custom split
that inserts pixels) *between* siblings that share `group=` if you also rely
on the default per-region `BackgroundLayer` fill — hover/press fills still
clip per region, so a gap can show as a dead strip in the capsule color.
Ripple is different: grouped regions share one wave painted once over the
united group rect, so a layout gap inside the group does not punch a hole
in the ripple. Prefer `gap=0` (and abutting rects) for a solid capsule; the
controller already expands each grouped region's fill path by a half-pixel
hairline so antialiased seams stay closed when rects abut. Apps that need
extra insurance sometimes nudge contiguous rects to overlap by 1 px (see
session-picker `_SeamlessHorizontalSplit` in Improve-ImgSLI).

Pointer moves *inside* a group do not clear and re-set `HOVERED` — the link
set stays hovered and only `_hovered_region` changes (needed for
`hover_compose="stack"` and to avoid a one-frame flicker of the shared wash).

Pointer over a **layout gap** between regions (or outer inset still inside the
widget) keeps the previous hover sticky: clearing would flash the shared row
wash. `hoverHitTest` likewise treats the full widget rect as hovered so
`HoverCoordinator` does not deactivate mid-gap.

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

A region has no rounding of its own by default — its path is a plain rect.
The capsule look comes from `BackgroundLayer` clipping each region's fill to
the intersection of that plain rect and the *whole button's* outer rounded
path (built from the button-level `corner_radius`/`corner_radii`). That clip
already rounds the outer edges of the first/last region in a group and keeps
the shared inner edge square — **you do not need to set per-region
`corner_radii` to get a seamless capsule; it happens automatically.** Only set
`corner_radii` on a region when you want *that region* to deviate from the
whole button's rounding (e.g. a smaller radius on one side, or a fully custom
shape via `path_fn`). Borders are whole-button only: `BackgroundLayer` skips
the border stroke entirely for any region whose rect differs from the
button's rect, so a grouped/split button is outlined once around the full
capsule, never per-region.

Content rendering inside grouped regions is **not** clipped to the region path
— glyph antialiasing and any overflow can spill into a sibling region of the
same group, which keeps text near the boundary from being visually trimmed.

Underline is whole-button only, same as `badge`/`divider`/
`show_strike_through`: `setShowUnderline`/`setUnderlineColor` always draw a
single line under the full widget rect, regardless of `regions=`/`group=`.
`ButtonRegion.show_underline`/`underline_color`/`underline_thickness` still
exist as fields, but only as internal storage for the `"_main"` region used
when converting between the imperative (`Button(show_underline=...)`) and
declarative (`ButtonSpec`) constructors — setting them on any other region
has no visual effect; there is no per-region underline override.

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

#### Custom `layers=` and paint order

`Button(..., layers=[...])` replaces the default painter pipeline. Each layer
declares a `scope`:

| `scope` | When it runs |
|---------|----------------|
| `"region"` (default) | Once per region, **before** any widget-scoped layer — same pass as `BackgroundLayer`, `RippleLayer`, `ContentLayer`. Regions that share `group=` are painted as one cluster with **layer-major** order (all backgrounds in the group, then ripple, then content) so a shared ripple is not covered by a sibling fill. Ungrouped regions stay region-major (needed for `z_index` overlays). |
| `"widget"` | Once for the whole button, **after** every region pass — used by badge, underline, divider, strikethrough |

Paint order matters when you supply a custom fill for a multi-region row (e.g.
one rounded list-item background behind several clickable zones):

- A **fill** that must sit *under* text/icons must use `scope = "region"`
  (draw once from a chosen region id such as `"_main"`, using `ctx.rect` for
  the full button bounds — `scoped_to` only sets `region_rect`).
- If that fill uses `scope = "widget"`, it paints **after** `ContentLayer` and
  will cover region content. Rows look empty even though `ButtonRegion` data is
  correct.
- Overlays that should sit *on top* of content (selection indicator, badge)
  can stay `scope = "widget"`.

When replacing `layers=`, include `ContentLayer()` (and usually `RippleLayer()`)
if the button still has icon/text/`rows` content — omitting them is another
way to get blank capsules.

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
| `pixmap` | `QPixmap \| QImage \| path \| None` | `None` — photographic cover for the region (preferred over `icon=` for photos) |
| `image_fill` | `"cover" \| "contain" \| "stretch"` | `"cover"` — how `pixmap` scales into the region rect |
| `toggle` | `bool` | `False` |
| `long_press` | `bool` | `False` |
| `long_press_ms` | `int` | `600` |
| `menu` | `list[tuple[str, Any]] \| None` | `None` |
| `action` | `str \| None` | `None` |
| `action_data` | `Any` | `None` |
| `action_callback` | `Callable[[str, Any], None] \| None` | `None` |
| `badge` | `int \| str \| None` | `None` |
| `variant` | `str \| None` | `None` |
| `custom_bg_color` | `QColor \| None` | `None` — **tint seed**, not an opaque fill; see [Background sources](#background-sources) |
| `override_bg_color` | `QColor \| None` | `None` — **exact opaque base** fill (not a freeze); see [Background sources](#background-sources) |
| `override_border_color` | `QColor \| None` | `None` |
| `hover_color` | `QColor \| None` | `None` — local hover overlay; `None` → standard theme/custom hover |
| `hover_compose` | `"replace" \| "stack"` | `"replace"` — one hover layer; `"stack"` → ambient + local under `group=` |
| `bg_locked` | `bool` | `False` — when `True`, base only (no hover/pressed/`hover_color`) |
| `icon_size_px` | `int \| None` | `None` |
| `show_strike_through` | `bool` | `False` |
| `enabled` | `bool` | `True` |
| `cursor` | `QCursor \| None` | `None` |
| `rect_fn` | `RectFn \| None` | `None` |
| `path_fn` | `PathFn \| None` | `None` |
| `z_index` | `int` | `0` |
| `corner_radii` | `tuple[int, int, int, int] \| None` | `None` — rounds the region **background**; when `pixmap=` is set, also **clips** the image (crop radii) |
| `group` | `str \| None` | `None` |

Note that `checked` is **not** a `ButtonRegion` field — a region's checked
state is runtime-only (see below), not part of its static config.

#### Cover / thumbnail images

Use `pixmap=` + `image_fill=` for scene previews and other photos. Do **not**
stuff a `QPixmap` into `icon=` — `IconContent` always draws a centered square
glyph at `icon_size`.

```python
from PySide6.QtGui import QPixmap
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, VerticalSplit

thumb = QPixmap("preview.jpg")
card = Button(
    regions=[
        ButtonRegion(
            id="cover",
            pixmap=thumb,
            image_fill="cover",
            corner_radii=(10, 10, 0, 0),  # fill + image crop
            weight=2.0,
            group="card",
        ),
        ButtonRegion(
            id="text",
            rows=[
                ButtonRow(text="Project", size=13, weight="bold"),
                ButtonRow(text="2h ago", size=11),
            ],
            weight=1.0,
            group="card",
            corner_radii=(0, 0, 10, 10),
        ),
    ],
    split=VerticalSplit(),
    size=(168, 120),
    corner_radius=10,
)
# Spec-editable at runtime:
card.update_region("cover", pixmap=new_thumb, corner_radii=(12, 12, 0, 0))
```

`pixmap` content fills the **full region rect** (ignores button
`content_padding`). Glyph `icon`/`rows` still respect padding.

#### Background sources

Three ways to pick the **base** fill (first paint layer), then optional state
overlays:

| Mechanism | Base | Hover / pressed |
|-----------|------|-----------------|
| `variant=` | Theme tokens | Theme hover/pressed (or `hover_color` if set) |
| `custom_bg_color=` / `set_background_color()` | Derived **tint** palette normal | Derived hover/pressed, or `hover_color` |
| `override_bg_color=` / `set_override_bg_color()` | **Exact** pixel color (opaque if you pass opaque) | Same as variant overlays (unlocked), unless locked |

##### `custom_bg_color` is a tint, not a solid chip

Passing a color into `custom_bg_color=` (ctor / region) or
`set_background_color()` does **not** paint that RGB as an opaque fill.
`derive_custom_palette()` turns it into a low-alpha tint over whatever shows
through the button:

| Variant | Idle (`normal`) alpha | Notes |
|---------|----------------------|--------|
| `default` | ~18% of the seed color | No own border |
| `surface` | ~18% + ~40% tint border | Card-like separation |
| `ghost` | idle transparent; hover/pressed tint | |

So the seed is a **hue/value hint for a translucent wash**, composited over the
host surface (page, shelf, dialog body). Consequences that surprise people:

- A **darker** seed darkens the host — usually readable.
- A **lighter** seed barely lightens the host — often looks like “color did
  nothing”, especially on an already light shelf.
- Matching the parent’s lightness and expecting a raised/lowered chip will
  fail; you only get a faint wash.

**When you need an opaque chip** that is literally lighter or darker than the
parent (toolbar on a tinted panel, header controls on a rounded shelf, etc.),
use `override_bg_color=` / `set_override_bg_color(color)` with the exact
`QColor` you want. That path skips tint derivation and paints the color as the
base layer.

```python
# Wrong for “lighter than shelf”: becomes ~18% alpha wash → almost invisible
button.set_background_color(shelf.lighter(108))

# Right: opaque base; hover/pressed overlays still apply unless bg_locked
button.set_override_bg_color(shelf.lighter(108))
```

`set_override_bg_color(color)` matches `override_bg_color`: it is an exact
**base**, not a kill-switch. Interactive overlays remain unless you call
`set_bg_locked(True)` / set region `bg_locked=True` (calendar selected /
disabled-export days do this).

When both `override_bg_color` and `custom_bg_color` are set, override wins as
base; custom is ignored for fill.

#### Hover compose & conflicts

`hover_compose` (default `"replace"`):

```python
Button(
    regions=[
        ButtonRegion(id="plate", rows=[...], group="row", hover_compose="stack"),
        ButtonRegion(
            id="run",
            icon="enter",
            group="row",
            hover_compose="stack",
            hover_color=QColor(0, 120, 215, 80),
        ),
    ],
    split=HorizontalSplit(),
)
```

- **`replace`** (BC): every HOVERED region (including group-mirrored siblings)
  paints one hover overlay = `hover_color` or standard.
- **`stack`**: only meaningful with `group=`. All siblings get a reduced-alpha
  **ambient** standard hover; the pointer region (`_hovered_region`) then paints
  a full **local** overlay (`hover_color` or standard). Without `group=`,
  `stack` behaves as `replace`.

Precedence:

1. `bg_locked` → base only.
2. Base = override → custom normal → variant normal.
3. Hover overlays (if unlocked + HOVERED) per compose rules above.
4. Pressed overlay on top when PRESSED (no `pressed_color` yet).

Custom `layers=` that omit `BackgroundLayer` ignore these fields unless your
layer reads them.

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

For new complex controls, `ButtonSpec` groups regions with split/divider/shape
under one immutable object; `ButtonSpec.regions` is a plain
`tuple[ButtonRegion, ...]` (there is no separate declarative region type —
see `docs/dev/BUTTON_REGION_ARCHITECTURE.md`):

```python
from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    ButtonSpec,
    Divider,
    ShapeSpec,
    VerticalSplit,
)

btn = Button.from_spec(
    ButtonSpec(
        regions=(
            ButtonRegion(id="add", icon="add"),
            ButtonRegion(id="amount", icon="settings", action="amount.reset"),
        ),
        split=VerticalSplit(),
        divider=Divider(),
        shape=ShapeSpec(size=(36, 36), corner_radius=6, icon_size=18),
    )
)
btn.regionClicked.connect(handle_region)
btn.actionTriggered.connect(handle_action)
```

`action`/`action_data`/`action_callback` on `ButtonRegion` work identically
whether the button was built via `regions=[...]` or `spec=`/`from_spec(...)`.

### Popup menus (app-owned)

`Button` does not embed dropdown menus (removed in 3.1.0). Open a
`ContextMenu` from `clicked`; slide distance and duration come from
`FlyoutTimingConfig` (`dropdown_drop_offset_px`, `flyout_animation_duration_ms`)
unless you pass `animation_distance` / `animation_duration_ms`:

```python
from sli_ui_toolkit.widgets import entries_from_labeled_data, popup_context_menu_for_anchor

button = Button(icon="mode")
button.clicked.connect(
    lambda: popup_context_menu_for_anchor(
        button.window(),
        button,
        entries_from_labeled_data([("RGB", "rgb"), ("SSIM", "ssim")], current="rgb"),
    )
)
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
    content_padding: float | tuple[float, float, float, float] = 0.0,
    corner_radius: int | None = None,
    variant: str = "default",
    density: str = "normal",
    defer_click: bool | int | str | None = None,
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
| `content_padding` | `float \| tuple[float, float, float, float]` | `0.0` | Inset (px) applied to the content draw rect only (icon/text/rows), from the edges of the whole button — or of each region's rect when `regions=` is used. A single float applies uniformly to all four sides (CSS-margin-style); a 4-tuple gives independent `(left, top, right, bottom)` insets — needed for e.g. a bottom-only reserve, since a uniform inset has no visible effect on already-centered content. Background, capsule, and hit-test rect are unaffected. |
| `corner_radius` | `int` | `None` | Corner radius (auto-calculated if None) |
| `variant` | `str` | `"default"` | Color variant: "default", "surface", "ghost". Deprecated aliases warn. |
| `density` | `str` | `"normal"` | Visual density: "normal", "compact" |
| `defer_click` | `bool \| int \| str \| None` | `None` | `None` inherits `get_default_defer_click()`; `False` sync; `True` next tick; `int` ms; `"ripple"` awaits `get_ripple_duration_ms()` (see [Press animations](#press-animations--blocking-handlers)) |
| `regions` | `list[ButtonRegion]` | `None` | Optional multi-region model. If omitted, Button creates a single `_main` region from the flat constructor params. |
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

# Emitted immediately after clicked (useful for rapid click detection)
button.shortClicked.connect(on_short_click)

# Multi-region signals
button.regionClicked.connect(lambda region_id: ...)
button.regionPressed.connect(lambda region_id: ...)
button.regionReleased.connect(lambda region_id: ...)
button.regionToggled.connect(lambda region_id, checked: ...)
button.regionLongPressed.connect(lambda region_id: ...)
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
button.set_background_color(QColor('#4488ff'))  # Tint seed (~18% wash), not opaque
button.set_override_bg_color(QColor('blue'))  # Exact opaque base (hover still applies)
button.set_bg_locked(True)                    # Optional: freeze to base only
button.set_hover_color(QColor(0, 120, 215, 80))
button.set_hover_compose("stack")             # ambient + local under group=

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

# Content padding — inset for icon/text/rows only, background/hit-test untouched
button.setContentPadding(6.0)  # uniform, all sides
button.setContentPadding((0.0, 0.0, 0.0, 4.0))  # left, top, right, bottom — bottom-only reserve
padding = button.getContentPadding()  # always returns (left, top, right, bottom)

# Density
button.setDensity('compact')
density = button.getDensity()

# Footer mode (visual hint)
button.set_footer_mode(True)
```

### Capability Management

```python
from sli_ui_toolkit.ui.widgets.buttons.capabilities import (
    ButtonCapability, LongPressCapability,
)

# Attach a capability
button.attach_capability(LongPressCapability(delay_ms=800), region_id="main")

# Get attached capability
lp_cap = button.get_capability(LongPressCapability, region_id="main")
if lp_cap:
    # ... use capability

# Detach capability
button.detach_capability(LongPressCapability, region_id="main")
```

New controls should usually describe behavior with `ButtonSpec` instead of
attaching capabilities manually. Direct capability attachment remains available
for specialized toolkit internals.

`BehaviorSpec` subclasses (`ClickBehavior`, `ToggleBehavior`,
`LongPressBehavior`) may carry `action=`, `data=`, and
`callback=`. When a behavior is triggered, `Button` emits
`actionTriggered(action_id, data)` and calls the callback if one was supplied.

The toolkit does not ship a built-in scroll/value-counter capability. Subclass
`ButtonCapability` and override `handle_wheel_event(event) -> bool` to react to
wheel input on a region — `Button`'s `wheelEvent` duck-types over every
capability attached to the target region and calls the hook automatically. See
the "Wheel counter (app-level recipe)" card in `demo/pages/buttons_page.py` for
a full example (custom capability + custom `Layer` for value rendering).

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
    marquee=False,                              # Loop left→right when text overflows
)
```

When ``marquee=True`` and the painted text is wider than the row, `Button`
scrolls that **single** row left→right via the shared
[`marquee_text`](../helpers) helper (default **30 logical px/s**, matching
Android `TextView` `MARQUEE_DP_PER_SECOND`; HTML ``<marquee>`` default is ~70
px/s and feels too fast for titles). Active marquee rows ignore horizontal
``content_padding`` and crawl edge-to-edge in the region (static rows still
respect padding). Do **not** marquee composite status lines such as
``"just now · Image Compare"`` — put the overflowing label on its own row
instead. Short text is unchanged (no animation).

For ``QLabel`` / toolkit ``Label`` use the same helper:

```python
from sli_ui_toolkit.widgets import Label, apply_marquee

Label("Long title…", marquee=True, elide=False)
# or later:
apply_marquee(any_qlabel)
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

`"primary"` is a deprecated alias for `"surface"` and emits
`DeprecationWarning`. Old button widget names such as `AutoRepeatButton`,
`IconButton`, `ToolButton`, and `ButtonGroupContainer` are lookups only and
will be removed in `0.3.0`.

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

### Menu Button (ContextMenu)

```python
from sli_ui_toolkit.widgets import entries_from_callbacks, popup_context_menu_for_anchor

def on_copy():
    print("Copied!")

btn = Button(icon='edit')
btn.clicked.connect(
    lambda: popup_context_menu_for_anchor(
        btn.window(),
        btn,
        entries_from_callbacks([
            ('Copy', on_copy),
            ('Paste', on_paste),
            ('Delete', lambda: print("Deleted!")),
        ]),
    )
)
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

# Exact brand base; hover overlays stay unless locked
btn.set_override_bg_color(QColor('#0066cc'))
# btn.set_bg_locked(True)  # flat chip, no hover

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

## Internal timers (advanced)

```python
# Long-press timer is owned by LongPressCapability
_lp_timer = btn._lp_timer
```

## Integration with CalendarDayButton

```python
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.day_button import CalendarDayButton

day_btn = CalendarDayButton()
day_btn.set_date(QDate(2026, 6, 1))
day_btn.set_weekend(True, QColor(100, 150, 255))  # Light blue
day_btn.set_data(True, QColor(0, 200, 0))        # Has data, green
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Popup menu not showing | Wire `button.clicked` → `popup_context_menu_for_anchor` with non-empty entries |
| Long press not triggering | Increase `long_press_ms` (default 600) |
| Colors not applying | Prefer `variant=` / `custom_bg_color=` for themed **tints**; `set_override_bg_color()` for an exact opaque base (add `set_bg_locked(True)` only when you need a flat locked chip) |
| Chip won’t go lighter than parent | `set_background_color` / `custom_bg_color` is a ~18% alpha tint — it darkens hosts but barely lightens them. Use `set_override_bg_color()` for an opaque lighter/darker chip (see [Background sources](#background-sources)) |
| Unlocked override still shows hover | Call `set_bg_locked(True)` when you need a flat locked chip — unlocked override is exact **base** fill only |
| Underline not visible | Call `setShowUnderline(True)` |
| Multi-region button looks empty (no text/icons) | Custom fill with `scope="widget"` paints after `ContentLayer` and covers content — use `scope="region"` for under-content fills (see [Custom layers and paint order](#custom-layers-and-paint-order)); also ensure `layers=` still includes `ContentLayer()` |
| Dead strip / gap in ripple between regions | Prefer `gap=0` between siblings that share `group=` (best for BackgroundLayer fills). Grouped ripple is painted once over the united group rect, so layout gaps do not punch a hole in the wave (see [Linking regions](#linking-regions-into-one-visual-capsule)) |

## Press animations & blocking handlers

Buttons play a Material-style ripple animation from the press point. The ripple
is driven by a `QTimer` that ticks every ~16 ms on the **main GUI thread**, same
as every other Qt animation. Duration ~280 ms (`RippleEffect.DURATION_MS`),
alpha ~12 % (light) / ~16 % (dark) — aligned with the Material Design 3 motion
tokens.

### Why animations may freeze

If a `clicked` handler does heavy synchronous work (e.g. re-applies the QSS
theme to all widgets, scans the filesystem, rebuilds a large model), the GUI
event loop is blocked until the handler returns. While it is blocked:

- the ripple `QTimer` cannot fire — the wave appears to stutter or freeze on
  whatever frame the press caught;
- hover transitions, scroll popups, and any other animation stalls too.

This is a **Qt-wide constraint**, not a bug in the ripple layer. QSS polish and
widget-tree mutation are inherently GUI-thread-bound — they cannot run on a
worker thread alongside the ripple timer.

### `defer_click` and process-wide defaults

`Button(defer_click=None)` (constructor default) inherits the process-wide
policy from `get_default_defer_click()`. Toolkit library default is `False`
(sync emit). Hosts that want every button to finish its ripple before
`clicked` typically set this once at startup:

```python
from sli_ui_toolkit import (
    DEFER_CLICK_AWAIT_RIPPLE,
    configure_toolkit,
    set_default_defer_click,
    set_ripple_duration_ms,
)

# Parallel process-wide knobs (same idea as flyout timings):
set_ripple_duration_ms(280)                 # system ripple length
set_default_defer_click(DEFER_CLICK_AWAIT_RIPPLE)  # await that length

# Or via configure_toolkit(...):
configure_toolkit(
    ripple_duration_ms=280,
    default_defer_click=DEFER_CLICK_AWAIT_RIPPLE,
)
```

Per-button override still works: `False` / `True` / `int` ms /
`DEFER_CLICK_AWAIT_RIPPLE`, or `btn.set_defer_click(...)`. When set, both
`clicked` / `shortClicked` and `regionClicked` are delayed (multi-region
cards that wire only `regionClicked` still get the wait).

```python
from sli_ui_toolkit.widgets import Button, DEFER_CLICK_AWAIT_RIPPLE

btn = Button(
    text="Apply",
    variant="surface",
    # omit defer_click to use the process default, or force:
    defer_click=DEFER_CLICK_AWAIT_RIPPLE,
)
btn.clicked.connect(apply_settings)  # may re-apply QSS + retranslate
```

What this **does**: the press animation plays to completion on a free event
loop; only then does the heavy handler run.

What this **does not** do: it does not make QSS/polish asynchronous. The UI may
still freeze *after* the ripple — just not *during* it.

`ThemeManager.set_theme` (toolkit ≥ 3.1.5) also defaults to `await_ripples=True`:
if any button ripple is still active when theme apply is requested, the blocking
work is deferred until that wave ends (same idea, for callers that do not own
the button).

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
QSS, mutating widget trees) cannot be moved off-thread; for those, finish the
ripple first (`defer_click=DEFER_CLICK_AWAIT_RIPPLE` / process default, and/or
`ThemeManager.set_theme`’s `await_ripples`) so the freeze happens *after* the
press feedback, not during it.

## See Also

- [Architecture](../dev/ARCHITECTURE.md) - Toolkit and button subsystem boundaries
