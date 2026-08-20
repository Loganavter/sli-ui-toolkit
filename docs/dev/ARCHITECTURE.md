# sli-ui-toolkit Architecture

This document explains how the toolkit is laid out, which imports are public, and where new code should go.

If you need something else:

- integration overview: [../../README.md](../../README.md)
- public reference: [../user/API_CATALOG.md](../user/API_CATALOG.md)
- visual conventions: [DESIGN_LANGUAGE.md](DESIGN_LANGUAGE.md)

## What This Package Is

`sli-ui-toolkit` is a reusable PySide6 UI layer with three main responsibilities:

- preserve the SLI name as **Shared Lightweight Interface**;
- provide custom-painted widgets and small reusable composites;
- provide shared UI infrastructure such as theming, icon resolution, i18n, flyout management, and workers;
- keep host-app specifics outside the toolkit and inject them through configuration hooks.

It is not a full application framework. App-specific icons, translations, business logic, and resource-folder conventions should stay in the host app.

## Public Surface

The toolkit intentionally exposes a small number of public entry points.

### Stable imports

- `sli_ui_toolkit`
  Bootstrap/configuration helpers and a few common primitives.
- `sli_ui_toolkit.widgets`
  Main public widget catalog.
- `sli_ui_toolkit.theme`
  `ThemeManager`.
- `sli_ui_toolkit.managers`
  `FlyoutManager`, `UiFont` / `ui_font(...)`, flyout show policies.
- `sli_ui_toolkit.i18n`
  Translation manager and `tr(...)`.
- `sli_ui_toolkit.icons`
  Icon resolver configuration.

### Internal imports

Everything under `sli_ui_toolkit.ui...` is implementation detail first.

Direct imports from internal modules are acceptable only when:

- a public re-export does not exist yet;
- the module is intentionally specialized and not meant for the broad public surface;
- you are working on toolkit internals themselves.

As a rule, application code should prefer `sli_ui_toolkit.widgets`.

## Layering

The package is easiest to understand as five layers.

### 1. Bootstrap and shared services

Files:

- `__init__.py`
- `theme.py`
- `i18n.py`
- `icons.py`
- `config.py`
- `core/`
- `workers/`

Responsibilities:

- startup configuration hooks;
- theme registration and theme switching;
- translation lookup;
- icon resolution;
- generic worker helpers;
- low-level shared utilities.

This layer should not depend on app code.

### 2. Public aggregation

Files:

- `widgets.py`
- `ui/widgets/atomic/__init__.py`
- `ui/widgets/composite/__init__.py`
- `ui/widgets/buttons/__init__.py`
- `ui/widgets/comboboxes/__init__.py`

Responsibilities:

- re-export public widgets from their implementation folders;
- keep import ergonomics stable when internals move.

### 3. Low-level widgets

Folders:

- `ui/widgets/atomic/`
- `ui/widgets/buttons/`
- `ui/widgets/comboboxes/`

Responsibilities:

- standalone input and display widgets;
- custom-painted controls;
- small self-contained UI primitives.

Use these folders when a widget can stand on its own without needing a higher-level shell.

Examples:

- `Button` lives in `ui/widgets/buttons/`
- `ComboBox` lives in `ui/widgets/comboboxes/`
- `CheckBox`, `Slider`, `CustomLineEdit`, `MinimalistScrollBar` live in `ui/widgets/atomic/`

### 4. Composite widgets

Folder:

- `ui/widgets/composite/`

Responsibilities:

- reusable multi-widget assemblies;
- flyouts, dialog shells, console widgets, help dialogs, and similar “assembled” controls;
- package-level reusable UX patterns.

Use this layer when the unit is bigger than one primitive and has meaningful internal structure.

Examples:

- `SidebarDialogShell`
- `MarkdownHelpDialog`
- `ProcessConsoleWidget`
- `AdaptiveTabStrip`, which owns tab painting, add/close controls, and
  adaptive close-button layout while the host owns document/session lifecycle

`ui/widgets/composite/adaptive_tab_strip/` is split by widget boundary:
`widget.py` is the thin host facade (row layout, close-button policy, the
QTabBar-like surface), `tab_bar.py` is the painted tab bar itself, and
`close_button.py` is the close-slot machinery (`_CloseButtonSlot`,
`CloseButtonPolicy`, the tab-background layer).

Same pattern for the other folder splits: `list_panel/` (facade in
`widget.py`; selection is a state-owning `MarqueeSelectionModel` in
`selection.py`, drop-target math is pure in `drag_drop.py`, item/position
transforms are pure in `rows.py`), `sidebar_nav_list/` (facade; row
spec/factory in `rows.py`, pure icon resolution in `icons.py`, geometry
debug dump as module functions in `debug.py`), `toast/` (one module per
class: `progress_bar.py`, `notification.py`, `manager.py`),
`inspector/code.py` (the Code section is a self-contained
`CodeSectionEditor` widget), and `text_view/document_mode.py` (the
document-mode selection state is a plain `DocumentSelection` model —
widget-free, canvas delegates).

`ui/inspector/` follows the same model: `view.py` holds only
`InspectorWindow` (tabs/toolbar) + the `_InspectionPane` owner; section
rendering, the Code section, and the Layout/Constructor trees are mixins in
`rendering.py` / `code.py` / `tree.py`, with value formatting in
`fields.py`.

### 5. Specialized UI families

Folders:

- `ui/widgets/composite/base_flyout/`
- `ui/widgets/composite/calendar_widget/`
- `ui/widgets/composite/timeline_widget/`
- `ui/widgets/composite/sunburst_chart/`
- `ui/widgets/composite/unified_flyout/`
- `ui/widgets/list_items/`
- `ui/widgets/overlays/`

Responsibilities:

- isolated feature families with multiple internal files;
- widgets that are too large to keep as single-module composites.

If a widget family starts needing private helpers, models, renderers, or interaction controllers, it should become a folder like this.

`base_flyout/` is the flyout shell split by concern: `widget.py` is a thin
facade; `geometry.py` holds the pure placement math (point specs,
alignment, slide deltas); `animation.py` owns ALL fade state in a
`FlyoutFadeController` (the widget only references it); style, content
building, placement, show/hide lifecycle and the FlyoutManager contract
live in `style.py` / `builder.py` / `placement.py` / `lifecycle.py` /
`contract.py`. State-owning helpers take the widget as an explicit
argument where they must touch it (grab/update); decision logic is pure.
Mixins precede `QWidget` in the MRO so their overrides
(`show`/`hide`/`raise_`/`paintEvent`) win while `super()` still resolves
to QWidget's methods.

The same split applies to `ui/windows/custom_title_bar/` (zones/balance in
`zones.py`, the min/max/close buttons as a real self-contained child
widget `WindowControlsCluster` in `window_controls.py` — it owns its own
buttons, slots and window-state refresh — the drag surface in `drag.py`,
fill/paint/theme hooks in `appearance.py`); the old module path stays a
thin re-export shim.

## Directory Map

This is the practical meaning of the main folders.

### `ui/widgets/atomic/`

Simple widgets.

Put code here when:

- the widget is small;
- the widget has little or no internal decomposition;
- it is a basic primitive.

Do not put large subsystems here just because they are “single controls”.
`ComboBox` belongs in `ui/widgets/comboboxes/`.

`atomic/combobox.py` and `atomic/comboboxes.py` are thin re-export shims.
Canonical imports: `sli_ui_toolkit.widgets` or
`sli_ui_toolkit.ui.widgets.comboboxes`.

### `ui/widgets/buttons/`

The unified button system.

Typical internal split:

- public re-export;
- main widget facade (`Button`);
- declarative specs (`ButtonSpec`, `ButtonRegion`, behavior/shape specs);
- controller/runtime state (`ButtonController`);
- painter/layers;
- menu/dropdown helpers;
- group container.

Use this folder as the model for any control family that grows beyond one file.

`Button` is a thin `QWidget` facade. Extend specs, controller routing, layouts,
or renderer layers rather than growing ad-hoc state on the widget.

### `ui/widgets/comboboxes/`

ComboBox family.

Current split:

- `combo_box.py`
  Main `ComboBox`.
- `_overlay.py`
  Popup rendering and interaction.
- `_search.py`
  Search and ranking helpers.
- `_models.py`
  Small internal item model.
- `capabilities/`
  ComboBox-specific composable gesture/interaction behavior (e.g.
  `GearDragCapability`, the press-hold/drag-to-scrub gesture), attached via
  the `Button.attach_capability()` `ComboBox` inherits. Mirrors
  `buttons/capabilities/` (`ButtonCapability`, `LongPressCapability`).
- `scrollable_combobox.py`
  Separate lightweight widget with different behavior.

This is the expected pattern for future medium-sized control families.

### `ui/widgets/composite/`

Reusable multi-widget assemblies.

A composite belongs here when:

- it owns layout and coordination between child widgets;
- it is not just a thin wrapper around a single primitive;
- it can be reused in multiple dialogs or apps.

### `ui/widgets/helpers/`

Pure UI helpers and drawing helpers.

This folder should contain code that:

- has no app-specific meaning;
- is reusable across multiple widgets;
- does not need widget ownership.

Typical examples:

- underline drawing;
- shadow drawing;
- overlay geometry calculations.

### `ui/managers/`

Shared UI stateful managers.

Use this layer for singleton-like or coordination objects such as:

- `ThemeManager`
- flyout manager / auto-hide coordination
- delayed action helpers
- `NavigationManager` — arrow-key navigation coordinator (see
  `docs/dev/NAVIGATION.md` for the full trial-dispatch contract and wiring
  guide)
- `WidgetDescriptor` / `WidgetRegistry` — unified widget self-description

#### `WidgetDescriptor` (unified widget self-description)

Replaces three parallel systems with one declaration:

| Old system | Section in `WidgetDescriptor` | What it provides |
|---|---|---|
| `InspectSpec` | `inspect: InspectSection` | family, config, state, tokens, docs |
| `NavigationSpec` | `navigation: NavigationSection` | navigate, focus_first, focus_last |
| `ActionDescriptor` | `action: ActionSection` | action_id, label, shortcut, run |

Widgets declare a `WidgetDescriptor` as a class or instance attribute:

```python
class MyWidget(QWidget):
    # Instance-level (set in __init__):
    def __init__(self):
        super().__init__()
        self.widget_descriptor = WidgetDescriptor(
            family="MyWidget",
            navigation=my_toolbar_rows_section,  # any NavigationSection impl
        )
```

`navigation` holds a `NavigationSection` *implementation* (a
`ToolbarRowsSection`, `IconListNavSection`, or any other object satisfying
the `owns`/`navigate`/`focus_first`/`focus_last`/`extra_keys` Protocol in
`ui/managers/navigation_manager.py`) — it is a Protocol, not a
constructible dataclass, so build the section itself first and assign it.
Call `register_navigation(owner)` to read it back off and register it with
`NavigationManager` — see `docs/dev/NAVIGATION.md` for the full guide,
including `NavRowBuilder` for accumulating a page's rows in order.

The `WidgetRegistry` singleton collects descriptors. Consumers
(`NavigationManager`, inspector, palette) query the registry.

**Backward compatibility:** `WidgetRegistry.get_for_class()` auto-converts
existing `inspect_spec = InspectSpec(...)` declarations to `WidgetDescriptor`
via `WidgetDescriptor.from_inspect_spec()`. No code changes needed for
widgets that only use `InspectSpec`.

### `ui/services/`

UI-related services that are not widgets.

Examples:

- icon services;
- window prewarm helpers.

### `workers/`

Generic async helpers built around Qt worker primitives.

Keep this folder generic. If a worker knows app business rules, it belongs in the app, not here.

## Import Rules

Use these rules to keep the package readable.

### Allowed

- widgets depend on `ThemeManager`, helpers, and small shared config;
- composite widgets depend on atomic widgets, buttons, comboboxes, helpers, and managers;
- public aggregators re-export from implementation modules;
- private modules inside one widget family can import each other.

### Avoid

- helpers importing widgets;
- atomic widgets importing composite widgets;
- broad sideways imports between unrelated widget families;
- business logic in toolkit widgets;
- app resource conventions inside toolkit code.

If two widget families start depending on each other heavily, there is usually a missing lower-level helper or service.

## How To Add New Code

Use this decision tree.

### Add to `atomic/`

When the new thing is:

- a small standalone control;
- a label, line edit, spinner, switch, checkbox, or similarly small primitive.

### Add a new folder like `buttons/` or `comboboxes/`

When the control family:

- is still one conceptual widget type;
- already needs private helpers, painter logic, popup logic, models, or internal state modules;
- benefits from keeping a thin public re-export and several private files.

### Add to `composite/`

When the new thing:

- assembles multiple existing widgets;
- owns a layout shell or interaction shell;
- is reusable but not “atomic”.

### Add a specialized subfolder under `composite/`

When the composite itself becomes a subsystem with:

- models;
- scene/view layers;
- rendering helpers;
- multiple interaction modes.

## How To Move Code Without Breaking Apps

Safe pattern when relocating an implementation:

1. Move the real implementation to a better folder.
2. Keep the previous module path as a thin import shim (or update all call
   sites in the same change if the path was never public).
3. Keep `widgets.py` exporting the same public names.
4. Update docs to point to the canonical location.

## Host-App Boundary

Keep these outside the toolkit:

- app icon enums and asset paths;
- app resource directory conventions;
- app translation content;
- app business rules and state transitions;
- app-specific plugins or controllers.

The toolkit should accept those via:

- `configure_icon_resolver(...)`
- `configure_i18n(...)`
- `configure_toolkit(...)`
- constructor parameters and thin app adapters.

Good example:

- `MarkdownHelpDialog` in the toolkit is generic.
- `help_sections.py` provides generic ordered-markdown discovery.
- the app-specific help adapter stays in the app and only chooses resource paths, title, icon, and language.

## Common Mistakes

- Treating `README.md` as the full API manual.
- Adding app-specific behavior directly into toolkit widgets.
- Importing deep internal modules from app code when a public re-export exists.
- Keeping a growing widget in one giant file after it has clearly become a widget family.
- Duplicating shared painting or geometry logic instead of moving it into `helpers/`.

## Current High-Level Shape

If you just need the mental model, it is this:

- bootstrap/configuration at the package root;
- stable public widget exports in `widgets.py`;
- primitives in `atomic/`, `buttons/`, and `comboboxes/`;
- reusable assembled widgets in `composite/`;
- larger specialized subsystems in their own subfolders;
- host-app specifics injected from outside.
