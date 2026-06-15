# SLI UI Toolkit — Design Language

This document describes visual and interaction rules for custom-painted widgets.

For other needs:

- integration overview: [../../README.md](../../README.md)
- public widget reference: [API_CATALOG.md](API_CATALOG.md)
- internal layering: [../dev/ARCHITECTURE.md](../dev/ARCHITECTURE.md)

## Overview

The toolkit implements a custom theme-aware design language with the following principles:

- **Custom-painted controls** — all interactive widgets (checkbox, radio, slider, switch, combobox, spinbox) are painted entirely via `QPainter`, not styled via QSS.
- **Smooth animated transitions** — state changes (hover, check, toggle) use `QPropertyAnimation` with `OutCubic` easing and short durations (100–200 ms).
- **Accent-driven color** — a single accent color (from `ThemeManager`) propagates through all active/focus/selected states.
- **Light and dark themes** — two palette sets registered at startup; widgets resolve colors from the active palette at paint time. Light mode is a first-class target, and dark mode stays reliable because the same token system drives both palettes.
- **Compact geometry** — controls are sized for tool-dense UIs (20 px indicators, 22 px track heights, 44 px button defaults).

## Not Fluent, Not Material

The design was originally inspired by WinUI 3 / Fluent Design but has diverged significantly:

| Aspect | Fluent Design | SLI Toolkit |
|--------|---------------|-------------|
| Elevation | Acrylic/Mica layers, shadows | Flat with minimal shadow on flyouts only |
| Motion | Spring-based, reveal highlight | Simple OutCubic property animations |
| Typography | Segoe UI Variable, type ramp | System font, 3 label sizes |
| Color | Semantic tokens, layered tints | Single accent + palette-resolved colors |
| Density | Standard/Compact modes | Single compact-density mode |
| Borders | Rounded 4 px default | 2–8 px radius depending on context |
| Iconography | Segoe Fluent Icons | App-supplied SVG icons via resolver |

The result is a pragmatic, compact toolkit for image/video and text-processing tool UIs — not a faithful Fluent implementation.

## Color System

Colors are resolved through `ThemeManager` at runtime:

```python
theme = ThemeManager.get_instance()
palette = theme.current_palette()

accent = palette.get("accent")       # Primary interactive color
window = palette.get("Window")       # Background
text = palette.get("WindowText")     # Foreground text
base = palette.get("Base")           # Input field backgrounds
button = palette.get("Button")       # Button surface
```

### Semantic QSS Tokens

QSS files use `@token` placeholders resolved at theme-apply time:

- `@accent` — primary accent
- `@dialog.text` — text in dialogs
- `@dialog.background` — dialog surfaces
- `@dialog.border` — subtle borders
- `@dialog.input.background` — input field fill
- `@flyout.background` / `@flyout.border` — flyout surfaces
- `@list_item.background.hover` — hovered/current rows inside flyouts and menus
- `@input.border.thin` — hairline input borders

## Typography

Text uses the unified `Label` component. Prefer direct typography options for
local UI needs and register variants only when a preset is shared across multiple
surfaces.

| Use case | Recommended `Label` options |
|----------|-----------------------------|
| Section headers | `pixel_size=13, bold=True` |
| Body text | `pixel_size=12` |
| Captions/status text | `pixel_size=11` |
| Dense labels | `pixel_size=10, elide=True` |
| Constrained labels | `elide=True, expanding=True` |

Common options include `family`, `pixel_size`, `bold`, `italic`, `underline`,
`strike_out`, `color`, `color_token`, `alignment`, `elide`, `minimum_width`,
`expanding`, `word_wrap`, and `selectable`.

## Control Geometry

All controls share one **compact density mode**. There is no separate
"comfortable" / "touch" mode — the toolkit targets tool-dense desktop UIs.
Defaults below assume a 96-DPI logical baseline; Qt's `devicePixelRatio` keeps
them sharp on hi-DPI screens without per-widget tuning.

| Control | Key dimensions | Source constant |
|---------|---------------|-----------------|
| `CheckBox` | 20×20 px indicator, 4 px radius | `CheckBox.INDICATOR_SIZE` / `INDICATOR_RADIUS` |
| `RadioButton` | 20×20 px indicator, fully round | inherited from `CheckBox` |
| `Switch` | 44×22 px track, 12 px knob, 2 px knob margin | `Switch.TRACK_WIDTH` / `TRACK_HEIGHT` / `KNOB_DIAMETER` / `KNOB_MARGIN` |
| `Slider` | 5 px track height, 8 px thumb radius | `Slider.TRACK_HEIGHT` / `RADIUS` |
| `SpinBox` | Fixed 32 px height, width based on numeric range | `setFixedHeight(32)` |
| `TimeLineEdit` | Fixed 32 px `HH:mm` input + two right-side 22 px step buttons | `CustomLineEdit.setFixedHeight(32)` |
| `CustomLineEdit` | Fixed 32 px height | `setFixedHeight(32)` |
| `ComboBox` | 33 px fixed height, 8 px corner radius, 24 px arrow area | `ComboBox.BASE_HEIGHT` |
| `ScrollableComboBox` | 33 px fixed height | `setFixedHeight(33)` |
| `Button` (icon) | 44×44 px default, 22×22 px icon | `Button` constructor `size=` / `icon_size=` |
| `Button` (icon, dropdown menu trigger) | 36×36 px when used as a flyout anchor | `button.py:435` / `button.py:454` |
| `InstancesCounterButton` | 36×36 px capsule, 6 px corner radius | Thin `Button` regions subclass with `_OUTER_SIZE` / `_CORNER_RADIUS` |
| `LoadingSpinner` | 40×40 px | `setFixedSize(40, 40)` |
| `Dropdown menu row` | 40 px row height inside flyout container | `_dropdown_menu.py:26` |
| `TimelineWidget` | 25 px ruler, 72 px thumbnail strip, 180 px left gutter (140–320 px clamp), 18 px playhead handle | constants on `TimelineWidget` |

### Density Assumptions

- **Single density.** No `density="comfortable"` / `density="touch"` switch
  exists. Hosts that need looser spacing should wrap controls in their own
  layouts (extra `QSpacerItem`, larger margins on parent containers).
- **Minimum hit target.** 22 px is the smallest interactive size used in the
  toolkit (slider thumb radius doubled, switch track height, small step
  buttons). Buttons default to 44 px, which is comfortably above standard
  pointer-target guidelines and accommodates touch on mixed-input devices.
- **Vertical rhythm.** Form rows that mix inputs assume a shared 32–36 px row
  height: `CustomLineEdit` and `SpinBox` are 32 px, `ComboBox` is 33 px,
  flat `Button` and `InstancesCounterButton` are 36 px. Mixing these inside a
  single row keeps baselines visually aligned within ±2 px.
- **Icon sizing.** Default icon-only `Button` uses a 22×22 px icon inside a
  44×44 px container (≈50 % padding). When changing button size with
  `size=(w, h)`, also pass `icon_size=` to keep the ratio consistent.

### Extension Points

When defaults do not fit, the toolkit offers these escape hatches before you
should reach for a fork:

- **`Button` constructor.** `size=(w, h)`, `icon_size=`, `corner_radius=`,
  `show_underline=` and `variant=` cover most resizing/restyling needs
  without subclassing. See `BUTTON_API.md`.
- **`Label` options.** `pixel_size`, `family`, `expanding`, `elide`, and
  `minimum_width` let hosts tune typography per call site; register a
  `LabelVariantSpec` if the same combo recurs across surfaces.
- **`WidgetStyleTokens`.** For custom-painted host widgets, set tokens via
  `update_widget_style()` (Qt dynamic properties) and read them in
  `paintEvent` via `read_widget_style()`. The toolkit re-polishes the widget
  for you. See `sli_ui_toolkit.style`.
- **Palette overrides.** Pass a custom dict to
  `ThemeManager.register_palettes(...)` with the same keys as
  `FLUENT_LIGHT` / `FLUENT_DARK`. Required tokens must be present; optional
  ones fall back to the bundled defaults; app-specific tokens use a
  host-namespaced prefix (see the *Token Tiers* section).
- **Class-level geometry constants.** Slider `TRACK_HEIGHT`, Switch
  `TRACK_WIDTH`, ComboBox `BASE_HEIGHT`, etc. are class attributes — a
  short-lived subclass can override them without touching the painter.
  Treat this as a soft API: the names may change in a major release; pin a
  version if you rely on them.

Anything not on this list is internal. Reaching into `sli_ui_toolkit.ui...`
to monkey-patch private painters or layout helpers is allowed but not
supported across versions.

## Animation Timing

All transitions use `QEasingCurve.Type.OutCubic`:

| Transition | Duration |
|-----------|----------|
| Hover in/out | 100–120 ms |
| Check/toggle | 150–160 ms |
| Flyout open/close | 150 ms |
| Slider thumb press | 100 ms |

## Contrast Targets

Default palette token pairs aim for WCAG 2.1 AA:

- **4.5:1** for body/label text on its surface (`WindowText`/`Window`,
  `Text`/`Base`, `dialog.text`/`dialog.background`,
  `HighlightedText`/`Highlight`, etc.).
- **3.0:1** for large text, UI components, and focus indicators
  (`accent` versus `Window`/`Base`).

`accent` and `Highlight` intentionally diverge in dark mode: `accent` stays at
`#0096FF` for crisp focus rings against the dark surface, while `Highlight`
drops to `#0078D4` so that white selection text retains AA-grade contrast on
the larger filled selection background. Override one without the other only if
you've re-verified both targets.

Hosts that swap palettes should keep these targets — the
`tests/test_contrast.py` parametrized suite enforces them for the shipped
defaults and is a copy-paste-ready harness for app palettes.

## Interaction Patterns

- **Hover** — subtle brightness shift or outline emphasis.
- **Active/pressed** — accent fill or accent outline.
- **Focus** — accent border (1 px) on inputs.
- **Disabled** — reduced opacity (0.3–0.5), no hover response.

## Flyout & Overlay Pattern

Flyouts are in-window widgets (not native popups):

- Anchored to a trigger widget.
- Painted with rounded shadow (`draw_rounded_shadow`).
- Auto-hide on mouse leave with configurable delay.
- Only one flyout active at a time (`FlyoutManager`).

## Token Tiers

Palette tokens fall into three tiers. The split lets host applications know which
tokens they must set, which they can override, and which they can invent.

### Required

These tokens drive Qt's `QPalette` plus the toolkit accent. Every widget reads
at least one of them at paint time, so a host must provide all of them — either
by registering `FLUENT_LIGHT` / `FLUENT_DARK` from `palettes.py`, or by passing
its own dict with the same keys to `ThemeManager.register_palettes(...)`.

| Token | Light default | Dark default | Read by |
|-------|---------------|--------------|---------|
| `Window` | `#ffffff` | `#252525` | dialogs, surfaces, default backgrounds |
| `WindowText` | `#1f1f1f` | `#e8e8e8` | default text on `Window` |
| `Base` | `#ffffff` | `#252525` | input field backgrounds |
| `Text` | `#1f1f1f` | `#dfdfdf` | input text, label fallback |
| `Button` | `#f0f0f0` | `#3a3a3a` | `Button(variant="surface")`, fallbacks |
| `ButtonText` | `#000000` | `#e8e8e8` | button label fallback |
| `Highlight` | `#0078D4` | `#0078D4` | selection backgrounds (must keep AA 4.5:1 with `HighlightedText`) |
| `HighlightedText` | `#ffffff` | `#ffffff` | selected text |
| `accent` | `#0078D4` | `#0096FF` | every active/focus/checked state |

### Optional

These tokens have meaningful defaults in `FLUENT_LIGHT` / `FLUENT_DARK`. Hosts
can override any of them, individually or by passing a fully custom palette.
If a host omits one, the toolkit falls back to the default from `palettes.py`.

Grouped by widget family (full keys in `src/sli_ui_toolkit/palettes.py`):

- **Buttons** — `button.default.*`, `button.primary.*`, `button.dialog.default.*`,
  `button.toggle.background.*` (normal/hover/pressed/checked/checked.hover).
- **Inputs** — `input.border.thin`.
- **Flyouts & overlays** — `flyout.background`, `flyout.border`, `shadow.color`,
  `separator.color`.
- **List items** — `list_item.background.normal`, `list_item.background.hover`,
  `list_item.text.normal`, `list_item.text.rating`.
- **Dialogs** — `dialog.background`, `dialog.text`, `dialog.border`,
  `dialog.input.background`, `dialog.button.background`, `dialog.button.hover`,
  `dialog.button.ok.background`.
- **Labels** — `label.image.background`.
- **Help dialog** — `help.separator`, `help.code.background`, `help.nav.background`,
  `help.nav.border`, `help.nav.hover`, `help.nav.selected`, `help.nav.selected.text`.
- **Toasts** — `toast.background`, `toast.text`, `toast.border`.
- **Slider** — `slider.track.background`, `slider.track.unfilled`,
  `slider.thumb.outer`.
- **Switch** — `switch.track.off.border`, `switch.knob.off`, `switch.knob.on`,
  `switch.knob.border`, `switch.text`.
- **Tooltip** — `tooltip.background`, `tooltip.text`, `tooltip.border`.
- **Color dialog** — `color_dialog.background`, `color_dialog.text`,
  `color_dialog.input.background`, `color_dialog.input.border`.
- **Misc Qt roles** — `AlternateBase`, `ToolTipBase`, `ToolTipText`, `BrightText`.

### App-specific extensions

The toolkit does not know about these tokens — they are defined by the host
application for its own composite widgets and read through `WidgetStyleTokens`
(`sli_ui_toolkit.style.WidgetStyleTokens`, `update_widget_style`,
`read_widget_style`; also re-exported from `sli_ui_toolkit` for convenience).

Typical use:

```python
from sli_ui_toolkit.style import WidgetStyleTokens, update_widget_style

update_widget_style(my_widget, WidgetStyleTokens(
    background_color=palette["my_app.canvas.fill"],
    border_color=palette["my_app.canvas.outline"],
))
```

Rules for extension tokens:

- Pick a host-specific prefix (e.g. `my_app.*`) so they cannot collide with
  toolkit tokens.
- Resolve them in host code, not inside the toolkit.
- If a token becomes useful across multiple hosts, promote it into the toolkit
  palette and move it to the Optional tier with a documented default.

## Extension Guidance

When adding a new custom-painted control:

1. Inherit from the appropriate Qt base (`QWidget`, `QAbstractButton`, etc.).
2. Resolve colors from `ThemeManager.get_instance()` inside `paintEvent`.
3. Use `QPropertyAnimation` for state transitions — never `QTimer`-based manual interpolation.
4. Respect `WidgetStyleTokens` via `read_widget_style()` if the widget needs app-supplied colors.
5. Use compact geometry (no padding larger than 10 px, no controls taller than 44 px by default).
6. Connect to `theme.theme_changed` signal to trigger repaint on theme switch.
