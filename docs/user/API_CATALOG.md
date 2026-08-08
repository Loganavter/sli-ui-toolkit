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
    BackgroundLayer,
    Button,
    ButtonGroup,
    ButtonRegion,
    ButtonSpec,
    ClickBehavior,
    Divider,
    DrawContext,
    Layer,
    OverlayPainterCallback,
    OverlayPainterLayer,
    RippleLayer,
    ShapeSpec,
    VerticalSplit,
    default_layers,
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

# Photographic cover (scene thumbnails) — pixmap fills the region; corner_radii
# also clips the image. Prefer this over icon=QIcon(pixmap).
btn = Button(
    regions=[
        ButtonRegion(
            id="cover",
            pixmap=thumb_pixmap,
            image_fill="cover",
            corner_radii=(10, 10, 0, 0),
            group="card",
        ),
        ButtonRegion(id="text", rows=[...], group="card"),
    ],
    split=VerticalSplit(),
)
btn.update_region("cover", pixmap=new_thumb, corner_radii=(12, 12, 0, 0))

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
| `underline_thickness` | float/None | Explicit underline thickness in pixels (uncapped) |
| `underline_tongue_reach` | float/None | How high (px) the underline's end caps climb the sides; `0` = square ends, `None` = matches corner radius |
| `underline_ring` | bool | Draw the underline as a closed frame around the whole button instead of a bottom band |
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
| `setUnderlineThickness(float\|None)` | Set underline thickness in pixels (uncapped) |
| `setUnderlineTongueReach(float\|None)` | Set how high the underline's end caps climb the sides |
| `setUnderlineRing(bool)` | Draw the underline as a closed frame instead of a bottom band |
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

**Underline scaling:** underline thickness, tongue reach, and arc radius scale proportionally with widget height (baseline: 32 px). This ensures visibility on high-DPI / large UI modes.

**Underline geometry:** the band is built from rounded-rect path boolean ops (never a stroked arc), so it cannot spill past the button's own rounded corners at any thickness. See `underline_tongue_reach`/`underline_ring` above and [BUTTON_API.md](BUTTON_API.md#custom-styling) for the full explanation and an example.

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

Theme-aware native `QMenu` for right-click commands. Full reference,
constructor/builder API, and `defer_trigger` details:
**[CONTEXT_MENU_API.md](CONTEXT_MENU_API.md)**.

| Name | Description |
|------|-------------|
| `ContextMenu` / `ContextMenuBuilder` / `ContextMenuAction` | Declarative right-click menus with a chainable builder. |
| `popup_context_menu_for_anchor` / `show_context_menu` | Convenience popup helpers. |

### Labels

Unified themed text component (`Label`), typography options, and built-in
presets: **[LABELS_API.md](LABELS_API.md)**.

| Widget | Description |
|--------|-------------|
| `Label` / `LabelConfig` / `LabelVariantSpec` | Unified themed text label, its config object, and variant registry entry. |
| `DropZoneLabel` | Label with drag-and-drop zone visuals and file accept logic. |

### Inputs & Other Atomic Controls

Text inputs, toggles, sliders, scroll areas, spinners, and grouped
containers — constructor kwargs, underline/wheel-focus policy, and runtime
setters for every widget below: **[INPUTS_API.md](INPUTS_API.md)**.

| Widget | Description |
|--------|-------------|
| `CustomLineEdit` | Themed line edit with rounded input paint and configurable alignment/underline. |
| `CheckBox` / `RadioButton` | Custom-painted checkbox/radio. |
| `Slider` | Custom-painted slider with accent track and optional custom track painter. |
| `SpinBox` | Custom-painted compact spinbox. |
| `Switch` | Custom-painted toggle switch. |
| `ComboBox` / `ScrollableComboBox` | Custom-painted combo box family. |
| `TimeLineEdit` | Compact toolkit-painted `HH:mm` input. |
| `MinimalistScrollBar` / `OverlayScrollArea` | Thin/overlay-style scrollbars. |
| `LoadingSpinner` | Animated conical-gradient loading spinner. |
| `CustomGroupWidget` / `CustomGroupBuilder` | Grouped widget container with builder pattern. |

---

## Composite Widgets

### Tabs

Two independent tab families — content-section tabs vs. closable workspace
tabs. Full constructor options and behavior: **[TABS_API.md](TABS_API.md)**.

| Widget | Description |
|--------|-------------|
| `TopTabBar` / `TopTabHost` | Horizontal content-section tabs for dialogs (export settings, wizards). Not for closable workspace documents. |
| `AdaptiveTabStrip` | Compact workspace-style tabs with a trailing add button and adaptive close buttons. |

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

Sidebar-shell dialogs, in-dialog navigation lists, and markdown/native help
viewers — constructor options and a full wiring example:
**[DIALOGS_API.md](DIALOGS_API.md)**.

| Widget | Description |
|--------|-------------|
| `SidebarDialogShell` / `ScrollableDialogPage` | Sidebar + stacked pages dialog container, and a ready-made scrollable content page. |
| `IconListWidget` / `IconListItem` | Icon-based navigation list for sidebar shells. |
| `MarkdownHelpDialog` / `MarkdownHelpSection` | Markdown→HTML help dialog (`QTextBrowser`) with anchors, TOC, and `help://slug#anchor` navigation. |
| `HelpDocumentView` | Native widget-tree help page renderer (controlled markdown subset, figures, kbd, links). |

### Console, Logging & Notifications

Live process/log consoles and transient toast notifications — constructor
kwargs and `show_toast`/`append_message` signatures:
**[FEEDBACK_API.md](FEEDBACK_API.md)**.

| Widget | Description |
|--------|-------------|
| `LogConsoleWidget` / `LogConsoleEntry` | Read-only themed console for app log messages. |
| `ProcessConsoleWidget` | `QProcess`-driven console for live command output with stdin input. |
| `ToastManager` / `ToastNotification` / `ToastAction` / `ToastProgressBar` | In-window transient toasts with actions and progress. |

### Data Visualization

Sunburst/donut charts, a three-level calendar, and a keyframe timeline —
full dataclass fields and runtime setters: **[CHARTS_API.md](CHARTS_API.md)**.

| Widget | Description |
|--------|-------------|
| `SunburstChartWidget` / `SunburstSegmentData` / `SunburstSegmentItem` | Sunburst/donut chart (`QGraphicsView`-based). |
| `CalendarWidget` / `CalendarDayButton` / `CalendarViewModel` | Three-level calendar (days/months/years). |
| `TimelineWidget` / `TimelineCallbacks` | Keyframe timeline with thumbnail strip, grouped tracks, zoom/scroll, range selection. |

---

## Overlays (from `sli_ui_toolkit.ui.widgets.overlays`)

In-window modal surfaces, drag/drop zone painters, and rubber-band selection
— constructor options and the `close_on_*` flag matrix:
**[OVERLAYS_API.md](OVERLAYS_API.md)**.

| Widget | Description |
|--------|-------------|
| `TopLevelInWindowOverlay` | Modal full-window in-window overlay hosting arbitrary `QWidget` content. |
| `OverlaySlot` / `OverlayItem` | Slot enum and item metadata. |
| `DragDropOverlay` | Transparent drag/drop zone painter. |
| `MarqueeBandOverlay` / `MarqueeBandGesture` | Pointer-transparent selection rubber-band + Wayland-safe drag tracker. |

---

## List Items

Row widgets meant to be dropped into a host-owned list/flyout, imported from
`sli_ui_toolkit.widgets`: **[LIST_ITEMS_API.md](LIST_ITEMS_API.md)**.

| Widget | Description |
|--------|-------------|
| `RatingListItem` | Star-rating list item with interactive hover and click. |
| `EditableListItem` | Row with inline-editable text, an optional checkbox, and a delete button. |

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
| `ThemeManager` | Palette + QSS theme application singleton. `set_theme` batches top-level updates across apply + `theme_changed`; `suspend_widget_updates()` is available for nested wrappers. |
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

See [CONFIGURATION.md](CONFIGURATION.md) for the full startup sequence,
every parameter, defaults, and what happens if a hook is skipped. Quick
reference:

| Function | Module | Description |
|----------|--------|-------------|
| `configure_toolkit(timings=..., overlay_resolver=..., dragdrop_service=..., ripple_duration_ms=..., default_defer_click=...)` | `sli_ui_toolkit.config` | Overlay layer resolution, drag-drop, timing constants, button ripple duration + default click deferral. |
| `set_ripple_duration_ms(ms)` / `get_ripple_duration_ms()` | `sli_ui_toolkit` / `widgets` | Process-wide Material ripple length (keeps `RippleEffect.DURATION_MS` in sync). |
| `set_default_defer_click(value)` / `get_default_defer_click()` | `sli_ui_toolkit` / `widgets` | Process-wide default for `Button(defer_click=None)`. Use `DEFER_CLICK_AWAIT_RIPPLE` to await the system ripple. |
| `configure_icon_resolver(resolver=..., named_icons=...)` | `sli_ui_toolkit.icons` | Icon resolution strategy. |
| `configure_i18n(i18n_root=...)` | `sli_ui_toolkit.i18n` | Path to JSON translation directory. |
| `ThemeManager.get_instance().register_palettes(light_palette=..., dark_palette=...)` / `.set_theme(name, app)` | `sli_ui_toolkit.theme` | Register color tokens and pick the active light/dark theme. |
| `setup_logging(app_name, debug_enabled=False, debug_env_var=None)` | `sli_ui_toolkit` | Route toolkit log records into the host app's logger/handlers. |
| `install_application_tooltips(app)` | `sli_ui_toolkit` | Install the toolkit's themed hover-tooltip event filter app-wide. |

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
- `LogConsoleWidget` / `ProcessConsoleWidget`
- `ToastManager`
- `SunburstChartWidget` / `CalendarWidget` / `TimelineWidget`
- `ThemeManager` + tooltip helpers
- `GenericWorker`
