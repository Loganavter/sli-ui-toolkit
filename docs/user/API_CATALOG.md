# SLI UI Toolkit — Full API Catalog

All public names are importable from `sli_ui_toolkit.widgets` unless noted otherwise.

This document is the public reference.

If you are onboarding instead of looking up a symbol, start with [../../README.md](../../README.md).
If you are changing internals, also read [../dev/ARCHITECTURE.md](../dev/ARCHITECTURE.md).

---

## Import Layers

### `from sli_ui_toolkit import ...`

Small convenience surface for app bootstrap and commonly used primitives.

Exports:

- `Label`, `LabelConfig`, `LabelVariantSpec`, `register_label_variant`, `get_label_variant`
- `GenericWorker`, `WorkerSignals`
- `ThemeManager`
- `TranslationManager`, `ToolkitTranslationEvents`
- `WidgetStyleTokens`, `read_widget_style`, `update_widget_style`
- `configure_i18n`, `configure_toolkit`, `FlyoutTimingConfig`
- `tr`, `get_current_language`, `emit_language_changed`, `translation_events`
- `get_log_directory`, `get_unique_filepath`, `resource_path`
- `setup_logging`, `setup_simple_logging`
- `install_application_tooltips`, `set_application_tooltips_enabled`, `application_tooltips_enabled`
- `CustomTitleBar`, `TitleBarMenu`, `TitleBarMenuStrip`, `TitleBarPresets`
- `WindowChrome`, `WindowChromeConfig`, `WindowControlsConfig`
- `decorate_dialog`, `apply_frameless`, `set_frameless_runtime`
- Popup menus: `ContextMenu`, `popup_context_menu_for_anchor`, `entries_from_labeled_data` — see **ContextMenu** in widgets catalog

See [WINDOW_CHROME_API.md](WINDOW_CHROME_API.md) for title bar zones, menu strips, and flyout anchors.

### `from sli_ui_toolkit.widgets import ...`

Main public widget catalog — everything below.

### `from sli_ui_toolkit.style import ...`

Canonical home for `WidgetStyleTokens`, `read_widget_style`,
`update_widget_style`, and `icon_size_qsize`. Also re-exported from
`sli_ui_toolkit` and `sli_ui_toolkit.widgets`.

Implementation-specific imports are also available for toolkit internals, for
example `sli_ui_toolkit.ui.widgets.comboboxes.ComboBox`. Prefer
`sli_ui_toolkit.widgets` for application code. Thin shims under
`sli_ui_toolkit.ui.widgets.atomic.combobox*` re-export the same types.

---

## Atomic Widgets

### Button (unified)

Composable `Button` with icons, text, toggle, long-press, badges, menus, and
multi-region layouts.

```python
from PySide6.QtGui import QColor

from sli_ui_toolkit.widgets import (
    Button,
    ButtonGroup,
    ButtonRegion,
    ButtonSpec,
    ClickBehavior,
    Divider,
    ShapeSpec,
    VerticalSplit,
)

# Icon-only toggle
btn = Button(AppIcon.MAGNIFIER, toggle=True)

# Icon pair (unchecked/checked icons)
btn = Button(icon=(AppIcon.VERTICAL, AppIcon.HORIZONTAL), toggle=True)

# Text button in dialog
btn = Button(text="Browse…", variant="surface")

# Icon + text with dialog/action surface style
btn = Button(AppIcon.SAVE, text="Save", variant="surface")

# Long press support
btn = Button(AppIcon.DELETE, long_press=True, background_color=QColor("#D93025"))

# Popup menu (app-owned ContextMenu)
from sli_ui_toolkit.widgets import entries_from_labeled_data, popup_context_menu_for_anchor

btn = Button(AppIcon.MODE)
btn.clicked.connect(
    lambda: popup_context_menu_for_anchor(
        btn.window(),
        btn,
        entries_from_labeled_data([("Option A", "a"), ("Option B", "b")], current="a"),
    )
)

# Badge overlay
btn = Button(AppIcon.MAGNIFIER, toggle=True, badge="3")

# Split button with two independently clickable regions
btn = Button(
    regions=[
        ButtonRegion(id="add", icon="add"),
        ButtonRegion(id="remove", icon="remove", enabled=can_remove),
    ],
    split=VerticalSplit(),
    divider=Divider(),
)
btn.regionClicked.connect(lambda region_id: ...)

# Linked regions: shared hover/press state across a "card"-style capsule
btn = Button(
    regions=[
        ButtonRegion(id="icon", icon="photo", group="card"),
        ButtonRegion(id="text", rows=[...], group="card"),
    ],
    split=HorizontalSplit(),
)

# Arbitrary path-shaped regions are supported through path_fn/z_index
btn = Button(
    regions=[
        ButtonRegion(id="base", rect_fn=lambda r: r, z_index=0),
        ButtonRegion(id="center", rect_fn=lambda r: r, path_fn=diamond_path, z_index=10),
    ],
)

# Declarative spec API
btn = Button.from_spec(
    ButtonSpec(
        regions=(
            ButtonRegion(id="add", icon="add", action="counter.add"),
            ButtonRegion(id="remove", icon="remove"),
        ),
        split=VerticalSplit(),
        divider=Divider(),
        shape=ShapeSpec(size=(36, 36), corner_radius=6),
    )
)
```

**Constructor parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `icon` | icon / (icon, icon) | Single icon or (unchecked, checked) pair |
| `text` | str | Text label (with or without icon) |
| `toggle` | bool | Checkable on/off behavior |
| `long_press` | bool | Emit `longPressed` after hold delay |
| `badge` | str/int | Small overlay badge text |
| `show_underline` | bool | Bottom color underline |
| `underline_color` | QColor/list/None | Explicit underline color or color segments |
| `underline_thickness` | float/None | Explicit underline thickness in pixels |
| `menu` | list | Dropdown menu items |
| `variant` | str | Visual variant (see below) |
| `wheel_requires_focus` | bool | Require focus before wheel events reach attached capabilities (see BUTTON_API.md's Capability Management section) |
| `regions` | list[ButtonRegion] | Optional multi-region content/behavior model |
| `split` | SplitLayout | Region geometry (`HorizontalSplit`, `VerticalSplit`, `GridSplit`, `CustomSplit`) |
| `divider` | Divider/None | Optional whole-widget divider rendering between split regions |
| `spec` | ButtonSpec | Declarative control description used by `Button.from_spec(...)` |
| `size` | (w, h) | Fixed size |
| `parent` | QWidget | Parent widget |

**Variants:**

| Variant | Theme prefix | Border | Use case |
|---------|-------------|--------|----------|
| `"default"` | `button.toggle` | no | Toolbar toggles (default) |
| `"primary"` | `button.primary` | yes | Deprecated alias for `"surface"`; removed in 0.3.0 |
| `"surface"` | `button.dialog.default` | yes | Dialog buttons |
| `"ghost"` | transparent | no | Invisible until hovered |
| `"subtle"` | Window color | no | Blends with background |

**Signals:**

| Signal | Description |
|--------|-------------|
| `clicked` | Click or short-click (when `long_press=True`) |
| `shortClicked` | Alias for click in long-press mode |
| `toggled(bool)` | Toggle state changed |
| `longPressed` | Long press detected |
| `rightClicked` | Right mouse button |
| `middleClicked` | Middle mouse button |
| `regionClicked(str)` | Region click by id |
| `regionPressed(str)` / `regionReleased(str)` | Region press/release by id |
| `regionToggled(str, bool)` | Region toggle state changed |
| `regionLongPressed(str)` | Region long press detected |
| `actionTriggered(str, object)` | Declarative behavior action id and payload |

**Runtime methods:**

| Method | Description |
|--------|-------------|
| `setUnderlineColor(QColor\|list\|None)` | Set underline color |
| `setUnderlineThickness(float\|None)` | Set underline thickness in pixels |
| `setBadge(str)` | Update badge text |
| `setBadgeStyle(filled=..., background_color=..., border_color=..., text_color=...)` | Configure badge outline/fill colors. Badges are outline-only by default. |
| `set_footer_mode(bool)` | Flat top, rounded bottom (for footer buttons) |
| `set_show_strike_through(bool)` | Red diagonal strikethrough |
| `set_override_bg_color(QColor)` | Exact base fill (hover/pressed still apply unless locked) |
| `set_bg_locked(bool)` | When True, paint base only (no hover/pressed overlays) |
| `set_hover_color(QColor \| None)` | Widget/`_main` local hover overlay (`None` = standard) |
| `set_hover_compose("replace"\|"stack")` | Apply hover compose mode to every region |
| `set_background_color(QColor)` | Custom seed → derived palette |
| `set_regions(list[ButtonRegion], split=..., divider=...)` | Replace region geometry/content at runtime. Reconciles by region id — same-id regions keep their hover/ripple/capability state, not a full reset |
| `set_spec(ButtonSpec)` | Replace the full declarative control description at runtime |
| `update_region(region_id, **changes)` | Replace one or more static `ButtonRegion` fields on a single region, leaving other regions and this region's runtime state untouched (see [BUTTON_API.md](BUTTON_API.md#updating-one-region-at-runtime)) |
| `setRegionChecked(region_id, checked, emit=True)` | Set a region's CHECKED state from code — generalizes `setChecked()`, which is hardcoded to `"_main"` |
| `region(region_id)` | Live `RegionHandle` exposing both static config and runtime state as plain attributes, e.g. `button.region("copy").checked = True` |
| `region_states(region_id)` | Read-only `frozenset[ButtonState]` snapshot for one region |
| `regions()` | Copy of the current `list[ButtonRegion]` (mutating the returned list has no effect — use `update_region`/`set_regions`) |
| `setFlyoutOpen(bool)` | Visual state for attached flyout |

**Underline scaling:** underline thickness and arc radius scale proportionally with widget height (baseline: 32 px). This ensures visibility on high-DPI / large UI modes.

### ButtonGroup

Container that groups buttons with a shared label.

```python
group = ButtonGroup([btn1, btn2, btn3], label="View")
```

### Other Button Widgets

| Widget | Description |
|--------|-------------|
| `InstancesCounterButton` | Segmented add/remove counter button implemented as a thin `Button` regions subclass. |

Deprecated button widget names such as `IconButton`, `ToggleIconButton`,
`ScrollableIconButton`, `AutoRepeatButton`, `ToolButton`, `ToolButtonWithMenu`,
`ButtonGroupContainer`, `ButtonType`, and `ButtonMode` are lookups only. Explicit
imports emit `DeprecationWarning`; these names are not in `__all__` and will be
removed in `0.3.0`.

### ContextMenu

`ContextMenu` is a theme-aware native `QMenu` for right-click commands. It is
intended for app/domain context actions such as rename, duplicate, remove,
properties, and submenus. Compared with flyouts, it uses Qt's menu behavior for
focus, keyboard navigation, submenus, and native popup lifecycle.

```python
from sli_ui_toolkit.widgets import ContextMenuBuilder

menu = (
    ContextMenuBuilder()
    .action("rename", "Rename", shortcut="F2")
    .action("duplicate", "Duplicate")
    .separator()
    .action("remove", "Remove", danger=True)
    .build(parent, on_triggered=lambda action_id, data: ...)
)
menu.popup_at(global_pos)
```

Public names:

| Name | Description |
|------|-------------|
| `ContextMenu` | `QMenu` subclass built from declarative entries. |
| `ContextMenuAction` | Action item model: id, text, icon, enabled, checked, danger, shortcut, data, children. |
| `ContextMenuSeparator` | Separator model. |
| `ContextMenuSection` | Group of entries with optional disabled title. |
| `ContextMenuBuilder` | Chainable builder for common menus. |
| `entries_from_labeled_data(items, current=..., checkable=...)` | Build checkable picker entries from `[(label, data), ...]`. |
| `entries_from_callbacks(items)` | Build command entries from `[(label, callback_or_data), ...]`. |
| `popup_context_menu_for_anchor(parent, anchor, entries, ...)` | Anchor-aligned dropdown (replaces removed `Button.menu` / `DropdownMenu`). |
| `show_context_menu(parent, global_pos, entries, on_triggered=...)` | Convenience function that builds and pops up a menu. |

### Labels

`Label` is the unified text component. Set the typography and behavior directly,
or start from a registered variant when a shared preset is useful.

```python
from sli_ui_toolkit.widgets import Label, LabelConfig

title = Label("Settings", variant="group-title")
body = Label("Ready", pixel_size=12)
caption = Label("Secondary status", pixel_size=11)
custom = Label(
    config=LabelConfig(
        text="Pinned",
        pixel_size=10,
        bold=True,
        color_token="accent",
        elide=True,
        minimum_width=80,
    )
)
```

**Common options:**

| Option | Description |
|--------|-------------|
| `text` | Label text. |
| `variant` | Optional registered preset name. |
| `family` | Font family override. |
| `pixel_size` | Font size in pixels. |
| `bold` / `italic` / `underline` / `strike_out` | Font styling flags. |
| `color` / `color_token` | Explicit `QColor` or `ThemeManager` token. |
| `alignment` | Qt alignment flags. |
| `elide` | Elide overflowing text with an ellipsis. |
| `minimum_width` | Minimum width used by size hints. |
| `expanding` | Use an expanding horizontal size policy. |
| `word_wrap` | Enable wrapped multiline text. |
| `selectable` | Enable mouse/keyboard text selection. |

**Built-in presets:**

| Variant | Size | Weight | Behavior |
|---------|------|--------|----------|
| `"body"` | 12 px | Normal | Standard body text |
| `"caption"` | 11 px | Normal | Small secondary/status text |
| `"compact"` | 10 px | Normal | Dense elided text |
| `"group-title"` | 13 px | Bold | Section headers |
| `"adaptive"` | 12 px | Normal | Expanding elided text |

| Widget | Description |
|--------|-------------|
| `Label` | Unified themed text label with direct typography and behavior options. |
| `LabelConfig` | Declarative configuration object for `Label`. |
| `LabelVariantSpec` | Typography/color variant registry entry. |
| `DropZoneLabel` | Label with drag-and-drop zone visuals and file accept logic. |

### Inputs

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

### Scrolling

| Widget | Description |
|--------|-------------|
| `MinimalistScrollBar` | Thin minimalist scrollbar for custom scroll areas. |
| `OverlayScrollArea` | Scroll area with overlay-style thin scrollbars. |

### Other Atomic

| Widget | Description |
|--------|-------------|
| `LoadingSpinner` | Animated conical-gradient loading spinner. |
| `CustomGroupWidget` / `CustomGroupBuilder` | Grouped widget container with builder pattern. |

---

## Composite Widgets

### TopTabBar / TopTabHost

Horizontal content-section tabs for dialogs (export settings, wizards). Twin of
`IconListWidget` on the other axis — not for closable workspace documents.

```python
from sli_ui_toolkit.widgets import TopTabHost

tabs = TopTabHost()
tabs.addTab(standard_page, "Standard")
tabs.addTab(manual_page, "Manual")
tabs.currentChanged.connect(on_tab_changed)
```

`TopTabBar` alone is enough when the host already owns a stack. Tab chrome is
painter-driven (`top_tab` Button variant); do not style tabs with QSS.

Implementation lives under `sli_ui_toolkit.ui.widgets.composite.top_tab_bar/`
(`bar`, `host`, `pane`, `chrome`, `tab_button`, …) — import the public types
from `sli_ui_toolkit.widgets`.

### AdaptiveTabStrip

Compact workspace-style tabs with a trailing add button and adaptive close
buttons.

```python
from sli_ui_toolkit.widgets import AdaptiveTabStrip, CloseButtonPolicy

tabs = AdaptiveTabStrip(
    add_icon=AppIcon.ADD,
    close_icon=AppIcon.CLOSE,
    close_policy=CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT,
    single_tab_closable=True,
)
tabs.addRequested.connect(create_workspace)
tabs.tabCloseRequested.connect(close_workspace)
tabs.currentChanged.connect(activate_workspace)
```

The strip reserves close-button width for every tab, so switching the selected
tab never changes tab widths. With the default close policy, every close button
is shown while full-size tabs fit; otherwise only the current tab keeps one.

`AdaptiveTabStrip` exposes common `QTabBar`-style methods such as `addTab`,
`removeTab`, `count`, `setCurrentIndex`, `setTabData`, and `tabData`. The
underlying widgets are available as `tab_bar` and `add_button`.

### Flyouts & Panels

| Widget | Description |
|--------|-------------|
| `BaseFlyout` | Base class for anchored flyout widgets. |
| `SimpleOptionsFlyout` | Flyout displaying a list of clickable text options. |
| `IconActionFlyout` / `IconAction` | Customizable horizontal flyout for icon action buttons. |
| `IndexedToggleFlyout` | Flyout with numbered toggle slots (show/hide per instance). |
| `UnifiedFlyout` | Full-featured dual-pane overlay list with drag-drop reordering, session management, animated open/close. Import: `sli_ui_toolkit.ui.widgets.composite.unified_flyout`. |

`BaseFlyout.show_aligned(anchor_widget, anchor_point="bottom-center", flyout_point="top-center", ...)`
aligns a named point on the anchor to a named point on the flyout. Point strings
use vertical-horizontal tokens such as `"top-left"`, `"center-right"`, or
`"bottom-center"`; the `"center"` half can be omitted for centered edge points,
for example `"top"`. Shorter `position="top"` / `"bottom-left"` forms are also
accepted (deprecated alias of the point API).

### Dialogs & Navigation

| Widget | Description |
|--------|-------------|
| `SidebarDialogShell` | Sidebar + stacked pages dialog container. |
| `ScrollableDialogPage` | Ready-made scrollable page for dialog content. |
| `IconListWidget` / `IconListItem` | Icon-based navigation list for sidebar shells. Selected icons support `selected_icon_mode="invert"` (default color inversion) or `"replace"` with `selected_icon=` / `(normal_icon, selected_icon)` pairs. |
| `TopTabBar` / `TopTabItem` / `TopTabHost` | Horizontal content-section tabs (axis twin of `IconListWidget`). `TopTabBar` is the painted strip; `TopTabHost` adds a bordered page stack with folder-tab chrome and a `QTabWidget`-like API (`addTab`, `setCurrentIndex`, `setTabText`, …). Not for closable workspace docs — use `AdaptiveTabStrip` there. |
| `MarkdownHelpDialog` / `MarkdownHelpSection` | Markdown→HTML help dialog (`QTextBrowser`) with anchors, TOC, and `help://slug#anchor` navigation. Useful for tests and simple HTML help. |
| `HelpDocumentView` | Native widget-tree help page renderer (controlled markdown subset, figures, kbd, links). Prefer for illustrated manuals; see Improve-ImgSLI `docs/dev/HELP_SYSTEM.md`. |

Markdown help section discovery helpers are intentionally not exported from
`sli_ui_toolkit.widgets`. Import them only where needed from
`sli_ui_toolkit.ui.widgets.composite.help_sections`.

Block parsers for `HelpDocumentView` live under
`sli_ui_toolkit.ui.widgets.composite.help_document`
(`parse_help_blocks`, `FigureBlock`, …).

### Path & File

| Widget | Description |
|--------|-------------|
| `OutputPathSection` | Combined output-directory + filename form section. |

### Console & Logging

| Widget | Description |
|--------|-------------|
| `LogConsoleWidget` / `LogConsoleEntry` | Read-only themed console for app log messages. |
| `ProcessConsoleWidget` | `QProcess`-driven console for live command output with stdin input. |

### Notifications

| Widget | Description |
|--------|-------------|
| `ToastManager` / `ToastNotification` / `ToastAction` / `ToastProgressBar` | In-window transient toasts. `show_toast(content, actions=...)` accepts strings, custom content widgets, `ToastAction` entries, action specs, or action widgets. Progress uses painted `ToastProgressBar` (accent fill, rounded track). |

### Data Visualization

| Widget | Description |
|--------|-------------|
| `SunburstChartWidget` | Sunburst/donut chart (`QGraphicsView`-based). Feed `SunburstSegmentData` list. Signals: `segment_clicked`, `segment_hover_*`. Center text color follows `dialog.text` or `set_center_text_color(...)`. |
| `SunburstSegmentData` | Dataclass: start_angle, span_angle (radians), inner/outer radius, color, segment_id. |
| `SunburstSegmentItem` | Individual chart segment (`QGraphicsPathItem`). |
| `CalendarWidget` | Three-level calendar (days/months/years) with `QStackedWidget`. Feed `CalendarViewModel` via `update_view()`. |
| `CalendarDayButton` | Individual day button with `date_clicked`/`date_context_menu` signals. |
| `CalendarDayInfo` / `CalendarMonthInfo` / `CalendarYearInfo` | Per-cell data for calendar. |
| `CalendarViewModel` | Full calendar view state (year, month, day, view_mode, navigation). |
| `TimelineWidget` | Keyframe timeline with thumbnail strip, grouped tracks, ruler, playhead, zoom/scroll, range selection. Feed via `set_data()`. |
| `TimelineCallbacks` | Callback hooks: `should_show_track`, `visible_channels`, `is_track_active`, `localize_token`, `localize_value`, `prominent_track_ids`. |

### Drag & Drop

| Widget | Description |
|--------|-------------|
| `DragGhostWidget` | Semi-transparent ghost widget shown during drag operations. |

---

## Overlays (from `sli_ui_toolkit.ui.widgets.overlays`)

| Widget | Description |
|--------|-------------|
| `TopLevelInWindowOverlay` | Modal full-window in-window overlay that can host arbitrary `QWidget` content. Children can be placed by `OverlaySlot` around an anchor or with explicit overlay-local geometry. Emits `dismissed()`. |
| `OverlaySlot` / `OverlayItem` | Slot enum and item metadata used by `TopLevelInWindowOverlay`. |
| `DragDropOverlay` | Transparent drag/drop zone painter built on `TopLevelInWindowOverlay`; keeps pointer transparency and the existing `set_overlay_state(...)` API. |

---

## List Items (from `sli_ui_toolkit.ui.widgets.list_items`)

| Widget | Description |
|--------|-------------|
| `RatingItem` | Star-rating list item with interactive hover and click. |

---

## Helpers (from `sli_ui_toolkit.widgets`)

| Name | Description |
|------|-------------|
| `apply_editable_text_behavior(widget)` | Normalize QLineEdit focus/enter behavior. |
| `calculate_centered_overlay_geometry(...)` | Compute centered overlay position relative to parent. |
| `draw_bottom_underline(painter, ...)` | Draw a themed bottom underline on a widget. Prefer widget-level underline APIs for `Button`, `CustomLineEdit`, and `ComboBox`. |
| `draw_rounded_shadow(painter, ...)` | Draw a rounded drop shadow behind a rect. |
| `UnderlineConfig` | Configuration dataclass for underline painting. |

## Style Tokens (from `sli_ui_toolkit.style`)

Also re-exported from `sli_ui_toolkit` and `sli_ui_toolkit.widgets` for
convenience. `sli_ui_toolkit.style` is the canonical public path.

| Name | Description |
|------|-------------|
| `WidgetStyleTokens` | Resolved style token set for custom painters. |
| `read_widget_style(widget)` | Read Qt dynamic properties into `WidgetStyleTokens`. |
| `update_widget_style(widget, *, update_geometry=False)` | Re-polish a widget after dynamic-property changes and repaint. |
| `icon_size_qsize(px, fallback=22)` | Build a `QSize(px, px)` from a token value with a fallback. |

---

## i18n System (`sli_ui_toolkit.i18n`)

| Name | Description |
|------|-------------|
| `I18nStateError` | Raised when code tries to mutate translation state outside the supported API. |
| `TranslationManager` | Singleton: loads `<i18n_root>/<lang>/*.json`, merges with `en/` fallback, caches per language. |
| `configure_i18n(i18n_root=...)` | Set path to i18n directory. |
| `tr(key, language=None, default=None)` | Pure translation lookup for a dotted key (e.g. `"dialog.save.title"`). Passing `language=` reads that language without changing global UI state. |
| `get_current_language()` | Return currently loaded language code. |
| `translation_events()` | Return `ToolkitTranslationEvents` with guarded `language_changed(str)` signal. Connect/disconnect are public; direct `.emit(...)` is blocked because it desynchronizes translation state. |
| `emit_language_changed(lang)` | Official path for global UI language changes; updates current language and emits `language_changed`. |

---

## Managers (`sli_ui_toolkit.managers`)

| Name | Description |
|------|-------------|
| `ThemeManager` | Palette + QSS theme application singleton. |
| `FlyoutManager` | Ensures only one registered flyout is active at a time. |
| `DelayedActionTimer` | Single-shot delayed callback wrapper. |
| `SettleGate` | Restartable quiet-period gate with optional per-pulse work (resize: cheap refit + deferred heavy pass). |
| `AnchoredFlyoutAutoHide` | Auto-hide helper for anchored flyouts. |

---

## Services (`sli_ui_toolkit.services`)

| Name | Description |
|------|-------------|
| `prewarm_widget_window(app, widget)` | Show/hide offscreen to warm rendering/layout. |
| `prewarm_widget_window_once(app, widget)` | Idempotent per-widget prewarm. |
| `OffscreenPrewarmAware` | Protocol for widgets needing prewarm hooks. |

---

## Workers (`sli_ui_toolkit.workers` / top-level)

| Name | Description |
|------|-------------|
| `GenericWorker` | `QRunnable`-based worker with result/error/progress signals. |
| `WorkerSignals` | Signal set (result, error, finished, progress). |

---

## Icons (`sli_ui_toolkit.icons`)

| Name | Description |
|------|-------------|
| `configure_icon_resolver(resolver=..., named_icons=...)` | Set icon resolution strategy and named icon map. |
| `resolve_icon(name_or_enum)` | Resolve an icon name/enum to QIcon. |
| `get_named_icon(name)` | Get QIcon by semantic name. |
| `get_icon_by_name(name)` / `get_icon_by_path(path)` | Direct icon lookup. |
| `get_themed_icon(name)` | Get theme-aware icon variant. |
| `IconService` | Service class for icon loading/caching. |

---

## Configuration Hooks

| Function | Module | Description |
|----------|--------|-------------|
| `configure_toolkit(timings=..., overlay_resolver=..., dragdrop_service=...)` | `sli_ui_toolkit.config` | Overlay layer resolution, drag-drop, timing constants. |
| `configure_icon_resolver(resolver=..., named_icons=...)` | `sli_ui_toolkit.icons` | Icon resolution strategy. |
| `configure_i18n(i18n_root=...)` | `sli_ui_toolkit.i18n` | Path to JSON translation directory. |

`overlay_resolver` is used by in-window surfaces such as button dropdown menus
and flyouts. A host overlay object should provide `host`, `attach(widget)`,
`anchor_rect(anchor)`, and `clamp_rect(rect, margin=...)`. Button dropdown menus
fall back to the top-level window when no overlay layer is resolved. Their
surface uses `flyout.background` / `flyout.border`; rows use
`list_item.background.hover` only for hover/current feedback.

---

## Tooltip System

| Name | Description |
|------|-------------|
| `install_application_tooltips(app)` | Install global custom tooltip rendering. |
| `set_application_tooltips_enabled(bool)` | Enable/disable custom tooltips globally. |
| `application_tooltips_enabled()` | Query current tooltip state. |
| `PathTooltip` | Singleton tooltip renderer (internal, used by timeline and other widgets). |

---

## Reuse Guidance

All widgets are generic and safe for reuse in any PySide6 application. No widget imports application-specific modules.

Safe first choices for new code:

- `Button` with appropriate `variant` — covers icons, toggles, long-press, menus, text
- `ButtonGroup` for grouped toolbar sections
- Labels, `CustomLineEdit`
- `SidebarDialogShell` + `ScrollableDialogPage`
- `OutputPathSection`
- `LogConsoleWidget` / `ProcessConsoleWidget`
- `ToastManager`
- `SunburstChartWidget` / `CalendarWidget` / `TimelineWidget`
- `ThemeManager` + tooltip helpers
- `GenericWorker`
