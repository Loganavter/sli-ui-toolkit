# Changelog

## 0.2.5

### Fixed
- Guard `DropdownMenu` outside-click filter cleanup so early Qt hide events cannot fail before the filter state is initialized.

## 0.2.4

### Removed
- Legacy `Fluent*` aliases (`FluentCheckBox`, `FluentComboBox`, `FluentRadioButton`, `FluentSlider`, `FluentSpinBox`, `FluentSwitch`). Use the neutral class names (`CheckBox`, `ComboBox`, `RadioButton`, `Slider`, `SpinBox`, `Switch`).
- Button variant `subtle` — it was visually indistinguishable from `ghost`; use `ghost` instead.
- `DialogActionBar`, `DirectoryPickerRow`, and `FavoritePathActions` were removed from the public API. Compose these simple rows directly with PyQt layouts plus toolkit `Button` / `CustomLineEdit`.
- `Button.set_color(...)` was removed; use `Button.setUnderlineColor(...)` for underline configuration.
- `ColorOptionsFlyout` was removed from the public API; use the customizable `IconActionFlyout` for icon action flyouts.
- **Legacy icon-button family removed**: `IconButton`, `SimpleIconButton`, `ToggleIconButton`, `ScrollableIconButton`, `ToggleScrollableIconButton`, `LongPressIconButton`, `NumberedToggleIconButton`, `UnifiedIconButton`, `AutoRepeatButton`, `CustomButton`, `ToolButton`, `ToolButtonWithMenu`, `MagnifierInstancesButton`, `ButtonGroupContainer`, `ButtonType`, `ButtonMode`. They were all backwards-compatibility aliases for the composable `Button`. Replace any usage with `Button(...)` plus the appropriate keyword arguments (`toggle=True`, `scrollable=(min,max)`, `long_press=True`, `menu=[...]`, `icon=...`, etc.).
- `FlyoutIconButton` removed — compose `Button` + `IconActionFlyout` directly (or wire your own hover-trigger button as the flyout demos do).
- `OutputPathSection` removed — assemble a directory picker row from `CustomLineEdit` + `Button(text="Browse", variant="surface")` directly. The original class was a thin convenience wrapper with too many constructor knobs.
- `SidebarNavList` removed — use `IconListWidget` directly; its `set_items()` accepts the same `(label, icon)` tuples that `set_nav_items()` did.
- `ToastManager.show_toast(..., action_text=..., on_action=...)` was removed. Pass `actions=[ToastAction(...)]`, action widgets, or action specs instead.

### Added
- Bundle a default icon pack (`add`, `add_circle`, `delete`, `edit`, `save`, `check`, `chevron-down`, `photo`, `settings`, `calendar`, `chart`, `download`, `folder_open`, `help`, `incognito`, `quick_save`, `remove`, `sync`, `text-manipulator`) under `sli_ui_toolkit/resources/assets/icons/` so `Button(icon="add")` works out of the box.
- `CustomGroupBuilder` now supports the `builder.add(widget).build(title=…)` API in addition to the static `create_styled_group(title)`.
- `CalendarViewModel.build_default_view_model(year, month, day)` helper — populates a 6×7 grid for the given month so the widget renders with no host glue.
- Export `UnifiedFlyout` and `FlyoutMode` from `sli_ui_toolkit.widgets`.
- `DropZoneLabel` paints its own rounded dashed border with idle / drag-active states; no QSS or host code required.

### Changed
- `CustomLineEdit`, `SpinBox`, and `TimeLineEdit` now accept configurable text alignment; `SpinBox` and `TimeLineEdit` use compact content-based sizing, and `TimeLineEdit` embeds two right-side repeatable minute step buttons.
- Wheel-scrollable controls (`Button(scrollable=...)`, `ComboBox`, `ScrollableComboBox`, `InstancesCounterButton`, `Slider`, `SpinBox`, `TimeLineEdit`) now share a `wheel_requires_focus` policy; by default they react on hover without requiring a prior click.
- `Button.set_footer_mode(...)` no longer overwrites a button's configured corner radius, so live radius changes and explicit `corner_radius` values are preserved.
- `Button` now preserves an explicit `corner_radius=0` instead of falling back to the default rounded radius.
- Button underline drawing now uses a single underline layer with configurable color/thickness, no separate bottom-edge decoration, and no darkened square corners when `corner_radius=0`; `CustomLineEdit` and `ComboBox` now expose matching underline color/thickness APIs for their own painted underlines; the demo button playground now uses an icon so icon size changes are visible.
- `UnifiedFlyout` panel rendering ported from improve-imgsli v9.0.0: the panel paints its own `flyout.background`/`flyout.border`/8px-radius surface (so it renders correctly without a host QSS sheet), uses 4-px content padding on all sides, caps scrolling at ~7.5 visible rows, and `_calc_panel_total_size` widens the panel to fit the longer of the content hint, the anchor button, or a 200px floor.
- `DropZoneLabel` no longer changes appearance on normal mouse hover; it only highlights during an accepted drag operation.
- Icon+text `Button` content now uses the configured icon size instead of capping icons at 16px.
- Toolkit-painted icons are normalized from their non-transparent bounds before drawing so padded SVG/glyph sources render at the requested visual size.
- `IconListWidget` / `SidebarNavList` now build normal and selected icon states from normalized pixmaps instead of handing raw padded icons to `QListWidget`.
- Default `Button` badges now match Improve-ImgSLI v9 text-only rendering; pill/outline badge styling is used only when `setBadgeStyle(...)` is explicitly configured.
- `SunburstChartWidget` center text now resolves from theme text color by default and can be overridden with `set_center_text_color(...)`; segment labels choose black/white contrast from the segment fill.
- Demo pages now show interactive states for sunburst hover/click, MarkdownHelpDialog anchors, SidebarDialogShell stacked pages, composite actions, list selection, and EditableListItem delete/checkbox behavior.
- `CalendarDayButton` now paints selected/data/weekend backgrounds before text instead of tinting over the finished button, so selected text color stays visible.
- `LogConsoleWidget`, `ProcessConsoleWidget`, and `PreviewPanel` now use rounded theme-aware text surfaces with borders; `ProcessConsoleWidget` uses toolkit `CustomLineEdit` for command input.
- The demo calendar title now switches days/months/years, and month/year selections update the visible calendar state.
- `IconActionFlyout` now closes when its anchor button is clicked again and after an action is selected.
- Button action menus no longer mark the last clicked item as current; checkmarks are shown only when callers explicitly use `set_current_by_data(...)`.
- `FontSettingsFlyout` now paints its own rounded flyout background/border, uses fallback UI labels when i18n is not configured, and draws color swatches without the square native `QPushButton` background.
- `FontSettingsFlyout` open animation now starts from the final panel corner instead of offsetting away from the trigger; the demo trigger width is fixed independently from status/debug text.
- `ToastManager` now builds in-window toast content from arbitrary strings or caller-provided widgets, and toast actions are composed from toolkit `Button` widgets via `ToastAction` / widget / spec lists.
- `BaseFlyout.show_aligned(...)` now supports point-to-point alignment via `anchor_point` and `flyout_point` strings such as `"bottom-center"` / `"top-center"`, while still accepting legacy `position=` values.
- `CustomLineEdit`, `SpinBox`, `TimeLineEdit`, and `ComboBox` now support focused underline styling through `focused_underline_color`, `focused_underline_thickness`, `setFocusedUnderlineColor(...)`, and `setFocusedUnderlineThickness(...)`; base underline options apply to the unfocused state.
- Wheel-scrollable widgets now take focus when handling wheel input, so focused visuals such as input underlines activate consistently during scroll interactions.

### Fixed
- `IconActionFlyout` / `IndexedToggleFlyout` now show their icon glyphs because icons resolve against the bundled toolkit resources.
- Bundled light/dark SVG icons use explicit theme-appropriate strokes instead of `currentColor`, which Qt SVG does not resolve consistently.
- Bundled `add`, `remove`, and `add_circle` icons now match the Improve-ImgSLI v9 resources.
- `BaseFlyout` now paints its own `flyout.background` / `flyout.border` surface, so simple flyouts do not depend on host QSS for their bubble background.
- `BaseFlyout` and `SimpleOptionsFlyout` now work with overlay layers that expose the documented `anchor_rect` / `clamp_rect` API, while preserving the Improve-ImgSLI `place_rect_relative_to_anchor` path.
- `FlyoutManager` now actively closes other registered flyouts on show, closes all flyouts on outside click / app deactivation, and keeps anchor clicks available for button-level toggle behavior.
- `EditableListItem` ships with a default delete glyph and the checkbox + delete button align at 28×28 instead of mismatching.
- `CustomLineEdit` is pinned to 32px height so it lines up flush with sibling `Button(variant="surface")` rows.
- Button dropdown menu width now matches the trigger button width instead of forcing a 180px floor; the menu also dismisses on outside click thanks to a global event filter installed while visible.
- Button dropdown menus now use the trigger width as a minimum and expand for longer item text instead of clipping long menu rows.
- The demo sunburst dataset now uses the documented radians + normalized radii contract, avoiding oversized scene geometry and blurred/downscaled chart rendering.

## 0.2.3

- Add a unified `Label` component with direct typography/behavior options and variant/config support.
- Remove the old public convenience label classes in favor of `Label`.
- Export `Label`, `LabelConfig`, `LabelVariantSpec`, `register_label_variant`, and `get_label_variant` through the public widget surface.
- Align built-in label typography with the documented design language.
- Remove `accent` and `delete` button variants; arbitrary colored buttons use explicit `background_color`.
- Make custom button background colors use subdued tint alpha levels so custom colors match the button visual system.
- Replace the static demo button showcase with a live editable button preview.
- Make `primary` button palette tokens visually distinct from neutral `surface` buttons.
- Give scrollable button value indicators an opaque neutral surface instead of drawing bare text over the button.
- Fix button dropdown menus so they remain visible when the host app does not provide an overlay layer.
- Paint button dropdown menu surfaces directly from flyout tokens and reserve list-item background fills for hover/current rows.
- Fix `CustomLineEdit` rendering so Qt does not draw an extra square styled background behind the rounded input.
- Clear editable text focus when clicking outside the active field, not only when pressing Enter.
- Make button badges outline-only by default and add `setBadgeStyle(...)` for filled/custom badge styling.
- Add text padding and theme-updated text color styling to `CustomLineEdit`.

## 0.2.2

- Clean up architecture documentation: remove legacy viewport migration notes that are irrelevant to the UI toolkit library.

## 0.2.1

- Document SLI as **Shared Lightweight Interface**.
- Add agent guidance for release/version discipline and host-app boundaries.
- Clarify that the toolkit was extracted from Improve-ImgSLI and Tkonverter but is maintained as reusable PyQt infrastructure.
- Replace theme-bias design wording with first-class light and dark theme support.
- Add a roadmap for making the library more mature as a standalone UI toolkit.

## 0.2.0

- Move shared UI toolkit code out of application repositories.
- Add ordered Markdown help section discovery helpers.
- Keep `sli_ui_toolkit.widgets` focused on public widget exports.
- Remove the redundant `comboboxes/combobox.py` compatibility layer.
- Keep legacy atomic combobox imports as compatibility re-exports.
