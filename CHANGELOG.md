# Changelog

## 3.1.6-1.1.11

### Fixed
- Resolved cascading issues with tests, painters, and widget creation/deletion in environments other than the development environment (Linux Mutter/Wayland).
- The toolkit is now guaranteed not to crash on GitHub Windows CI servers and Flatpak build servers.

## 3.1.5

### Added
- Process-wide button feedback API (parallel setters):
  `set_ripple_duration_ms` / `get_ripple_duration_ms` and
  `set_default_defer_click` / `get_default_defer_click`, plus
  `DEFER_CLICK_AWAIT_RIPPLE` (`"ripple"`). Also accepted by
  `configure_toolkit(ripple_duration_ms=..., default_defer_click=...)`.
- `Button(defer_click=None)` inherits the process default (library default
  remains synchronous `False`).
- `defer_click` now delays `regionClicked` as well as `clicked` (needed for
  multi-region create-cards that wire `regionClicked`).
- `translatable_text` / `tooltip` / `placeholder` / `callback` accept
  `defer_when_hidden=True`: language updates for off-screen widgets (e.g.
  stacked workspace pages) wait until the next `Show` event.

### Changed
- `ThemeManager.set_theme(..., await_ripples=True)` (default) defers the
  blocking QSS/polish apply until any active button ripple finishes, so the
  wave is not frozen mid-frame. Top-levels hosting an active ripple are also
  skipped by `suspend_widget_updates`.
- `Button.defer_click` accepts `bool | int`: `True` = next tick, `int` = delay
  in ms (use `RippleEffect.DURATION_MS`). `Button.set_defer_click()` setter.
- `RippleEffect.remaining_ms()` and public `RippleEffect` export on
  `sli_ui_toolkit.widgets`.
- `Label`: `theme_changed` only recolors (palette); full font/geometry rebuild
  stays on font changes and property setters — major theme-switch speedup.
- `ThemeManager` theme switches batch top-level `setUpdatesEnabled(False)`
  across QSS apply **and** `theme_changed` emit, then one `update()` pass —
  avoids the “theme fills in gradually” cascade and shortens the freeze.
- `apply_theme_to_app` no longer calls `QApplication.processEvents()` between
  clearing and setting the stylesheet (that mid-flush painted a half-themed
  tree). Nested `suspend_widget_updates()` is public for app wrappers.

## 3.1.4

### Added
- `SimpleOptionsFlyout.row_widget(index)` for Find Action / pulse targeting.

### Fixed
- `bind_popup_transient_parent`: on Windows, skip `winId()` /
  `QWindow.setTransientParent` when the host uses `WA_TranslucentBackground`
  (frameless CSD). Forcing that native link permanently broke DWM alpha for
  in-window siblings (soft shadows painted as solid black until restart).
  Wayland still gets an explicit transient parent for xdg_popup placement;
  Windows relies on `place_popup_at_global` alone.

## 3.1.3

### Added
- Timeline selection edge handles (resize) and middle drag (move) for Shift+drag ranges.
- `HelpDocumentView` image lightbox for figure clicks.
- Button pixmap / marquee text content helpers for dense toolbar rows.
- Flyout slide-start and `SimpleOptionsFlyout` width sizing improvements.

### Fixed
- App-level tooltip interceptors: ignore non-`QObject` watched targets (e.g. `QRhi`) instead of calling `QObject.eventFilter` — prevents `TypeError` / `QWidget returned NULL` when opening dialogs over an RHI canvas.
- `CustomTitleBar._clear_zone`: hide + detach widgets before `deleteLater` so a replaced `TitleBarMenuStrip` cannot paint on the first show frame (ghost menu labels).
- `TitleBarMenuStrip.remasure()`: no deferred balance `singleShot` (that second layout after the first paint left a translucent ghost of «Справка» between File and Help); full title-bar `repaint()` after width changes.
- `CustomTitleBar._schedule_balance_resync`: while hidden, sync immediately instead of deferring past first show.
- `TitleBarMenuStrip.remasure()` + host call sites: recompute File/Help widths after the UI font is applied so Cyrillic labels are not sized with a fallback face.
- `IconTextContent`: set the paint font before measuring text width (Cyrillic advances no longer collapse on the first paint).

## 3.1.2

### Changed
- `IconListWidget`: navigation rows no longer set label text as a tooltip (labels still elide; hover no longer repeats the visible caption).

### Fixed
- `CustomTitleBar`: window-control cluster uses a fixed width so min/max/close no longer overlap when the bar is squeezed.
- `TitleBarMenuStrip` / `CustomTitleBar`: remasure on `FontChange` as well as `ApplicationFontChange` (Qt delivers the former after `QApplication.setFont`); menu trigger width gets a small slack so labels like «Файл» do not clip.
- `SimpleOptionsFlyout`: size from live row `sizeHint` (label + tight pad), not font-advance + 180px floor / extra clearance — ModePicker panels stay close to the longest label.
- `CustomTitleBar`: host Resize/Move no longer calls `FlyoutManager.close_all()` — keep `flyout_group=context_menu` open so tall File/Help menus are not dismissed on first open.
- `FlyoutManager`: anchor-dismiss sets only one suppress flag (`_suppress_next_context_menu` for context menus, `_suppress_next_click` otherwise). Setting both poisoned the next open (second click required).
- `Button._emit_click_signals`: clearing `_suppress_next_click` also clears a paired `_suppress_next_context_menu` left from older dual-flag dismiss paths.
- `tr(..., language=...)`: always resolve an explicit language from that pack instead of assuming the live translation buffer matches `_current_lang`.

## 3.1.1

### Fixed
- `TopLevelInWindowOverlay`: defer dismiss on window/app deactivate and drop event filters first so PySide6 + offscreen no longer segfaults in `hideChildren` during focus delivery / test teardown.
- Tests: `Button.triggered` removal assertions for 3.1.0; `IconListWidget` render uses `QPainter` + `QPoint()` for current PySide6 signatures.

## 3.1.0

### Removed (breaking)
- `Button(menu=...)`, `ButtonConfig.menu`, `ButtonRegion.menu`, and all built-in dropdown menu APIs: `MenuCapability`, `DropdownMenu`, `set_menu_items` / `set_actions`, `show_menu`, `set_menu_animation`, `set_current_by_data`, `menuTriggered`, `regionMenuTriggered`, and deprecated `Button.triggered`.
- `MenuBehavior` from the declarative button spec surface.
- `AdaptiveTabStrip(add_button_menu=...)` — use `add_button.clicked` + `ContextMenu` in app code when a plus-button menu is needed.
- `TitleBarMenuMode.dropdown` — tuple menu entries now open via `ContextMenu` like other command menus.

### Added
- `ToastProgressBar`: painted progress track for toasts (accent fill, rounded ends, `toast.progress.background` / `toast.progress.fill`). `ToastNotification` no longer shrinks width when the label shortens; omitting `progress=` in `update_toast(...)` keeps the current bar.
- Composable `CustomTitleBar` zones (`leading` / `center` / `trailing`), drag exclusions, and `titlebar.*` theme tokens.
- `TitleBarMenu`, `TitleBarMenuStrip`, and `popup_context_menu_for_anchor` — IDE-style menu strip with Button dropdown, `ContextMenu`, and flyout anchor support.
- `TitleBarPresets.dialog` / `TitleBarPresets.app_shell` presets.
- `WindowChrome.install`, `WindowChromeConfig`, `WindowControlsConfig`, shared `RoundedWindowBody` painting, and `set_window_bg_color(...)`.
- `docs/user/WINDOW_CHROME_API.md` and API catalog section for window chrome.
- `HelpDocumentView` — native widget-tree help renderer (controlled markdown subset, figures with `side=left|center|right|block`, kbd, links).
- `TopTabBar` / `TopTabItem` / `TopTabHost` — horizontal content-section tabs.
- `ThemedWidget` mixin for theme-repaint subscription.
- `UiFont` / `ui_font(...)` / `apply_ui_font` / `paint_font` / `rebase_font` / `apply_text_color` — pinned UI typeface (no `QFont()` / color-only QSS for toolkit text).
- `SettleGate` — restartable quiet-period gate for resize/pulse work.
- Pluggable flyout show policies on the managers surface: `ExclusiveShowPolicy`, `GroupShowPolicy`, `CallableShowPolicy`, `flyout_group_of`, `DISMISS_ALL`.
- `entries_from_labeled_data(...)` and `entries_from_callbacks(...)` helpers for building `ContextMenu` entries from `[(label, data), ...]` tuples.
- `popup_context_menu_for_anchor(..., animation_distance=..., animation_duration_ms=...)` animation tuning.
- Button background controls: `set_bg_locked(...)`, `set_hover_color(...)`, `set_hover_compose("replace"|"stack")`.

### Changed
- `decorate_dialog` delegates to `WindowChrome.install` and accepts an optional pre-built `title_bar`.
- `CustomTitleBar` title label uses toolkit `Label` with theme-driven background paint.
- `ContextMenu` lives under `ui/widgets/composite/context_menu/` (folder package).
- Docs describe current APIs without migration-diary framing (`ARCHITECTURE`, `ROADMAP`, `BUTTON_REGION_ARCHITECTURE`, catalog/BUTTON/FLYOUT/WINDOW docs).

### Fixed
- Grouped multi-region ripple (`group=`) again covers the full capsule: sibling `BackgroundLayer` fills no longer overpaint the shared wave (session-picker cards and similar). Painter clusters `group=` siblings and paints layer-major within the cluster.
- `Button.click()` restored (QAbstractButton parity) so programmatic / shortcut activation emits the normal press→click sequence.
- Frameless resize hit-testing and rounded window body mask edge cases.
- Combo overlay focus/reveal when the popup must stay above in-window chrome.
- Rating-item `+` control no longer selects the list row as a side effect.

### Migration
- `popup_context_menu_for_anchor(...)` lives in `widgets` (`context_menu/`), not in `buttons/` or `windows/`.
- Replace `Button(..., menu=items)` with `button.clicked` → `popup_context_menu_for_anchor(...)` or `ContextMenu.show_aligned(...)`.
- Replace `button.menuTriggered` / `button.triggered` handlers with `ContextMenu.on_triggered` or `actionTriggered`.
- Replace `set_actions` / `set_current_by_data` with app-owned picker state + `entries_from_labeled_data(..., current=...)`.
- Host apps that customize flyout exclusivity should install a `GroupShowPolicy` (or `CallableShowPolicy`) instead of patching widget classes.

## 0.3.0

### Added
- `AdaptiveTabStrip` composite (workspace-style tabs with trailing add button and adaptive close-button policy).
- `ContextMenu`, `ContextMenuAction`, `ContextMenuSection`, `ContextMenuSeparator`, `ContextMenuBuilder`, and `show_context_menu(...)` — a theme-aware native `QMenu` API for app/domain context actions with shortcuts, icons, checked items, disabled/danger entries, sections, separators, and submenus.
- Top-level window decoration helpers: `CustomTitleBar`, `apply_frameless(...)`, `remove_frameless(...)`, `set_frameless_runtime(...)`, and `decorate_dialog(...)` for frameless windows/dialogs with client-side title bars and resize handling.
- Tests covering the new tab strip, context menu, window decoration helpers, per-corner button radii, PySide6 import surface, underline gating, layered/custom backgrounds, and worker/i18n/tooltip regressions.
- `ButtonRegion.group` (and matching `RegionSpec.group`) — regions that share the same group propagate hover/press state to each other and treat a press-then-release within any sibling region of the group as a click of the press region. Lets a multi-region button render as one visual capsule (e.g. icon + multi-row text).
- Content drawing inside a grouped region skips the region-path clip so glyph antialiasing/overflow near the inner boundary spills onto the sibling region (matching bg) instead of being trimmed.
- Per-corner button radii via `Button(corner_radii=(tl, tr, br, bl))`, `ButtonConfig.corner_radii`, `ShapeSpec.corner_radii`, and region-level `ButtonRegion.corner_radii` for seamless split/grouped capsules and custom title-bar controls.
- `ButtonCapability.handle_wheel_event(event)` — an optional hook (default no-op) that any attached capability can override to receive wheel events routed to its region. `Button.wheelEvent` dispatches to it duck-typed, with no hardcoded capability type.
- `Button.update_region(region_id, **changes)` and `Button.setRegionChecked(region_id, checked, emit=True)` — programmatic per-region updates that reconcile through `set_regions()` by id, leaving other regions' and the target region's own runtime state (hover/ripple/capabilities) untouched. Previously the only way to change one region's static fields or checked state was to rebuild and pass the whole region list, and `setChecked()` only ever addressed the implicit `"_main"` region.
- `Button.region(region_id)` returns a `RegionHandle` — a live view exposing both static `ButtonRegion` fields and runtime state (`checked`, read-only `hovered`/`pressed`) as plain attributes, e.g. `button.region("copy").checked = True`, so callers don't need to know which of the two internal stores a given field lives in.
- `Button.set_menu_animation(drop_offset_px=..., move_duration_ms=...)` for tuning dropdown menu opening distance and duration without reaching into private `MenuCapability` / `DropdownMenu` internals.
- `ButtonRegion.action` / `.action_data` / `.action_callback` — `Button.actionTriggered` dispatch is now reachable from the imperative `Button(regions=[...])`/`update_region()` API, not only from `Button.from_spec(ButtonSpec(...))`. Previously a region built through `regions=` could never trigger `actionTriggered`, because the underlying `ClickBehavior(action=..., callback=...)` was only ever populated from the (now-removed) `RegionSpec`.

### Changed
- Migrated runtime from PyQt6 to PySide6.
- Updated package metadata, README/docs examples, demo imports, tests, and AUR template dependency declarations from PyQt6 to PySide6.
- Moved `ColorSwatch` out of the public toolkit API; the demo now owns its local color swatch example.
- Removed `BaseFlyout.make_color_swatch(...)` with the public `ColorSwatch` removal; demos now compose color swatches locally instead of exporting that helper from the toolkit.
- Reworked i18n lookup flow: `tr(key, language=...)` loads alternate language packs without changing global language or emitting `language_changed`; explicit global switching goes through `emit_language_changed(...)` / `set_current_language(...)`.
- Replaced `TranslationsBinder` with widget-lifetime-bound helpers: `translatable_text(...)`, `translatable_tooltip(...)`, `translatable_placeholder(...)`, and `translatable_callback(...)`.
- Button backgrounds now resolve as paint layers, preserving a base layer below hover/pressed/checked overlays. The `"ghost"` variant uses translucent theme-aware overlays instead of borrowing toggle background tokens.
- Runtime `Button.setIcon(...)`, `setText(...)`, `setRows(...)`, and `set_actions(...)` now keep the main controller region in sync with facade state.
- Right-click presses on buttons now start the same region-aware ripple feedback path as left-click presses before emitting `rightClicked` on release.
- `UnifiedFlyout` sizing now keeps the panel width aligned to the anchor button and allows the decorative shadow halo to extend outside the clamped content area.
- Timeline scrubbing now keeps the visual scrub index from the precise pointer position and rounds frame selection from pointer position, reducing off-by-one feel while dragging.
- Deprecated imports and runtime compatibility aliases now use a centralized `sli_ui_toolkit.deprecations` registry with consistent replacement, removal-version, and changelog context instead of hand-written warnings scattered across modules.
- i18n state changes now have fail-fast guards: direct `translation_events().language_changed.emit(...)` and legacy `TranslationManager.load_language(...)` raise `I18nStateError` with documentation guidance. Use `emit_language_changed(lang)` for global UI language changes and `tr(key, language=...)` / `ensure_loaded(lang)` for passive lookups.
- `Button.set_regions()`/`set_spec()` now detach capabilities left over from regions that disappear across a reshape (previously a region's capability, and any `QTimer` it owned, leaked forever once that region id stopped appearing in a subsequent call).
- **Breaking:** collapsed the Button region schema from three hand-synced representations down to one. `ButtonRegion` (`regions.py`) is now the sole schema; `ButtonSpec.regions` is `tuple[ButtonRegion, ...]` instead of `tuple[RegionSpec, ...]`, and `ButtonSpec.from_regions()`/`.to_regions()` are lossless passthroughs instead of a field-by-field conversion. See `docs/dev/BUTTON_REGION_ARCHITECTURE.md` for the rationale — the old three-schema setup (`ButtonRegion` / `RegionStyle`+`RegionSpec` / `DrawContext.region_*`) had no mechanism to catch a field added to one and not the others; that's how per-region `corner_radii` shipped broken for months.

### Removed
- **Breaking:** `ContextMenu` no longer subclasses `QMenu` — it is now a regular in-window overlay widget (like the rest of this toolkit's flyouts/tooltips/dropdowns), rendered inside the host window instead of as a separate frameless OS popup window. Public API (`ContextMenuBuilder`, `ContextMenuAction`/`ContextMenuSection`/`ContextMenuSeparator`, `show_context_menu`, `popup_at`/`exec_at`, `actionTriggered`) is unchanged, but code that reached into `QMenu`/`QAction` internals (`.actions()`, `.menu()`, `.trigger()`) needs to use the new row-based structure instead.
- **Breaking:** the built-in scroll-wheel value counter is gone entirely — `Button(scrollable=...)`/`ButtonConfig.scrollable`, `ScrollCapability`, `ValuePopupContent`, `ScrollBehavior`, `Button.valueChanged`/`regionValueChanged`, `setValue`/`getValue`/`setRange`, `configure_value_popup`/`set_popup_controller`, and the value-under-icon rendering in `IconContent` are all removed. Button no longer owns this concern; it only provides the generic primitives (`attach_capability()`, `ButtonCapability.handle_wheel_event`, and custom `Layer`s via `Button(layers=...)`) needed to build an equivalent app-level counter — see the "Wheel counter (app-level recipe)" card in `demo/pages/buttons_page.py` (`WheelCounterCapability` + `ValueBelowIconLayer`).
- Toggle+scroll composition (`_do_toggle_scroll_click`/`_handle_toggle_scroll_wheel`) is removed along with the scroll system it composed with.
- `Button._is_scrolling` and `ButtonState.SCROLLING` — leftovers of the removed scroll capability. No layer in the paint pipeline branched on `SCROLLING` any more, but `_is_scrolling` remained a live property backed by `_region_states`, which made it look like a supported hook for app-level capabilities to flip. It wasn't; it did nothing visually. Custom capabilities that want visual feedback should drive a custom `Layer` (see `attach_capability()`/`Button(layers=...)`) instead.
- **Breaking:** `ContentSpec` and `RegionStyle` are gone; `RegionSpec` is gone (use `ButtonRegion` directly as `ButtonSpec.regions` elements — `RegionSpec(id="x", content=ContentSpec(icon="add"), style=RegionStyle(icon_size_px=20))` becomes `ButtonRegion(id="x", icon="add", icon_size_px=20)`). Custom per-region click behavior (previously `RegionSpec(behaviors=(ClickBehavior(action=..., callback=...),))`) is now `ButtonRegion(action=..., action_callback=...)`.

### Fixed
- Application tooltips now support `QTabBar` per-tab tooltips and ignore empty tooltip events instead of showing blank bubbles.
- `GenericWorker` keeps itself alive until `finished` is delivered under PySide6, preventing queued `result` / `error` / `finished` signals from being dropped after `QThreadPool` auto-deletes the runnable wrapper.
- Direct icon pixmap rendering is restored: `normalized_icon_pixmap(...)` no longer crops and rescales glyphs based on alpha bounds, avoiding distorted source-designed icon padding.
- `setShowUnderline`/`setUnderlineColor` now always draw a single line under the whole button, matching `badge`/`divider`/`show_strike_through`. Previously `UnderlineLayer` painted once per region on multi-region (`regions=`/`group=`) buttons, so the line rendered at each region's own bottom edge instead of the bottom of the whole capsule (visible as the underline sitting at the shared inner seam instead of the true bottom on a `VerticalSplit` button).
- `IconActionFlyout.show_aligned(...)` gained a `toggle: bool = True` parameter. The method doubled as both "open/reposition" and "click-to-close-if-already-open": calling it a second time with the same anchor while the flyout was already visible always hid it, even when the caller's intent was just to reposition or re-affirm an already-open flyout (e.g. re-running it from a hover handler, or from a store-change callback that repositions the flyout after its content changes). Callers doing that must now pass `toggle=False`. Surfaced by ImgSLI's magnifier color-settings flyout, which repositioned itself on every `viewport` store change (i.e. continuously while the mouse moved over the magnifier) and would vanish as soon as it opened; `IndexedToggleFlyout` (a `BaseFlyout` subclass, not `IconActionFlyout`) was never affected since it doesn't have this toggle branch at all.

## 0.2.14

### Fixed
- Fixed dialog/navigation geometry so `SidebarDialogShell`, `MarkdownHelpDialog`, generic dialog scaffolds, and `IconListWidget` no longer impose unnecessary fixed or maximum widths; long navigation row labels elide inside the available row width and keep full labels in tooltips.

## 0.2.13

### Fixed
- Synchronized `sli_ui_toolkit.__version__` with the package version (0.2.12 was published with a stale `_version.py` reporting `"0.2.11"` at runtime).

## 0.2.12

### Changed
- `Button` no longer auto-resolves a state-transition ripple gradient for toggle widgets. Gradient ripples are now strictly opt-in via `setRippleColors(color_from, color_to)`; without an explicit call, all buttons (including toggles) fall back to the default overlay ripple.

### Removed
- Redundant `CalendarDayButton._resolve_ripple_colors` override (now identical to the base default).

## 0.2.11

### Added
- Material Design 3 style press animation (`RippleEffect` and `RippleLayer`) for `Button` with configurable durations, quadratic ease-out curves, and theme-adaptive peak opacity levels (12% on light themes, 16% on dark themes).
- Support for state-transition color gradients in button ripples (used automatically for toggle buttons to smoothly morph old state backgrounds into new state backgrounds, or manually configured via `setRippleColors`).
- `defer_click` parameter in `Button` to queue click signal emissions (`clicked`/`shortClicked`) on the next event-loop tick, mitigating animation freezes when triggering heavy synchronous GUI-thread tasks (such as theme switching).
- Multi-region `Button` support via `ButtonRegion`, `HorizontalSplit`, `VerticalSplit`, `GridSplit`, `CustomSplit`, `Divider`, `regions=`/`split=`/`divider=`, `set_regions(...)`, and region-scoped signals/capabilities/ripples.
- New `"sidebar_nav"` button variant registered in `sidebar_nav_list.py` — resolves backgrounds from `list_item.background.normal/.hover` and `accent` tokens for the checked state.
- `IconListWidget.add_item(text, icon=None, data=None)` helper, returning a proxy with `QListWidgetItem`-style API (`text`/`setText`/`setIcon`/`setSizeHint`/`data`/`setData`).
- `IconListWidget` selected-icon modes: `"invert"` for selected color inversion and `"replace"` for alternate selected icons via `selected_icon=` or `(normal_icon, selected_icon)` pairs.
- Declarative `ButtonSpec` / `RegionSpec` control model with content, style, shape, and behavior specs plus `Button.from_spec(...)` / `set_spec(...)` for complex button controls.
- `Button.actionTriggered(action_id, data)` and behavior-level `action` / `data` / `callback` dispatch for declarative button controls.
- Arbitrary path-shaped button regions via `path_fn` and `z_index`; hit-testing, background, content, and ripple clipping now respect region `QPainterPath`s.
- `TopLevelInWindowOverlay`, `OverlaySlot`, and `OverlayItem` as reusable full-window in-window overlay infrastructure for arbitrary child widgets.
- Virtualization support for dropdown items in `ComboBox` using a pool of `_DropdownItemSlot` widgets (extends `Button`).

### Changed
- Legacy button widget names (`IconButton`, `ToggleIconButton`, `AutoRepeatButton`, `ToolButton`, `ToolButtonWithMenu`, `ButtonGroupContainer`, `ButtonType`, `ButtonMode`, etc.) now remain available only as lazy compatibility lookups that emit `DeprecationWarning`; they stay out of `__all__` and are scheduled for removal in `0.3.0`.
- Older `sli_ui_toolkit.ui.widgets.atomic.combobox*` compatibility modules now emit `DeprecationWarning`; canonical `sli_ui_toolkit.widgets` and `sli_ui_toolkit.ui.widgets.comboboxes` imports remain warning-free.
- `InstancesCounterButton` is now a thin `Button` regions subclass, so its add/remove halves share the standard button painter, hover states, dividers, theme resolution, and ripple feedback.
- `DragDropOverlay` now inherits from `TopLevelInWindowOverlay`, reusing the shared in-window overlay base while preserving its pointer-transparent drag/drop painting API.
- Refactored the core `Button` implementation (`button.py`) by isolating visual style properties/methods into a dedicated mixin `_ButtonStyleApi` (`style_api.py`) and input event handlers into `_ButtonEvents` (`events.py`), shrinking the facade code and unifying geometry calculations for text formats.
- `IconListWidget` is no longer a `QListWidget`. It is now a `QWidget` wrapping a vertical stack of toolkit `Button`s inside a `QScrollArea`, so sidebar navigation reuses the unified Button visuals (ripple, theming, hover/press). Public surface preserved: `set_items`, `clear`, `count`, `item`, `currentRow`, `setCurrentRow`, `setIconSize`/`iconSize`, `refresh_icons`, `enable_minimal_scrollbar`, signals `currentRowChanged(int)` and `currentItemChanged(item, prev)`. Rows are rendered by a custom `_NavRowContent` (left-aligned icon + text) on a `_NavRowButton` (`toggle=False`, `NoFocus`) — selection is driven entirely by `IconListWidget`, ripple stays in overlay mode (a shade darker than hover) instead of auto-gradient between unchecked/checked backgrounds.
- `MarkdownHelpDialog` populates its sidebar via `add_item(section.title)` instead of constructing `QListWidgetItem(text, parent)` directly.
- `TimeLineEdit` step buttons (`▲`/`▼`) now include `RippleLayer` in their custom layer pipeline, so they share the standard ripple feedback with the rest of the toolkit buttons.
- Accelerated `ComboBox` dropdown presentation by shifting show/hide actions from mouse release to mouse press, removing the activation delay.
- Refined `ComboBox` text layout: switched from asymmetric right-padded rects to symmetric horizontal padding, and decoupled list item hover styling from text positioning bounds to align baselines between the field and the dropdown overlay.
- Unified font rendering in `ComboBox` list overlays by resolving metrics directly from the parent ComboBox font.
- Split documentation into `docs/user/` for library consumers and `docs/dev/` for toolkit maintainers, with root-level compatibility redirects for old doc paths.
- Button region runtime state and geometry now flow through `ButtonController`, keeping compatibility aliases on `Button` while moving toward a spec/controller/renderer architecture.
- `InstancesCounterButton` now builds its add/remove layout as a `ButtonSpec` factory rather than assembling raw regions directly.
- `SingleRegionSplit` now gives each region the full widget rect, enabling overlay-style custom path regions without a separate split layout.
- Refactored `ScrollableComboBox`, `ComboBox`, `_SimpleRow`, `_MenuItem`, and `RatingListItem` to inherit from the `Button` base class, enabling standardized ripple effects, focus, and state pipelines.
- Improved `ComboBox` dropdown opening trigger to fire on click (release) rather than press, allowing the click wave to complete.
- Enabled temporary mouse transparency (`WA_TransparentForMouseEvents`) on flyouts during open animation to prevent accidental hover triggers.
- Optimized flyout initialization speed in `UnifiedFlyoutPanel` and `SimpleOptionsFlyout` by freezing layout/paint updates during bulk row insertions, preventing performance degradation on large lists.
- Scaled down icons on `RatingListItem` adjustment buttons from default sizing to a compact 14px.
- Adjusted `OverlayScrollArea` viewport margin behavior to properly reserve space for the minimalist scrollbar without clipping.

### Fixed
- Resolved a bug in `HoverCoordinator` where widgets in non-active child windows incorrectly evaluated hover events under Wayland due to global coordinate translation limits; events are now reconciled selectively against the source window.
- Synchronized programmatic `Button.setChecked(...)` with the main region `CHECKED` state, so widgets that update selection from models use the same painter state as click-driven toggles.
- Fixed `CalendarDayButton` interaction layering: day cells no longer keep a focus outline after clicks, hover uses the standard `Button` event path, selection wins over hover/data/weekend backgrounds, and ripple feedback is visible on press.
- Completed the remaining keyboard audit item for `InstancesCounterButton`: it is now Tab-reachable and supports keyboard add/remove activation.
- Restored `IconListWidget` row icons after the Button-backed rewrite by drawing resolved row pixmaps instead of raw icon identifiers.

### Removed
- Removed default bottom focus underline painting and associated configuration methods from `ComboBox` to simplify visual styling.
- Removed custom focus outline drawing from `Switch` to avoid clipping artifacts along track boundaries.
- `PasteDirectionOverlay` (superseded by the reusable `TopLevelInWindowOverlay` infrastructure).
- `ChoiceOverlay` and `ChoiceSlot` from the public widget exports; legacy explicit imports now emit `DeprecationWarning` and should migrate to `TopLevelInWindowOverlay` / `OverlaySlot`.

## 0.2.10

### Changed
- Tightened the default sizing for button scroll-value popups.

## 0.2.9

### Added
- Button scroll-value popups can be customized with formatter, pixmap/text, size, font, style, and padding options.
- Python 3.10 test compatibility via `tomli` fallback for TOML parsing.

### Changed
- AUR release publishing workflow and PKGBUILD handling were aligned with the existing package flow.

## 0.2.8

### Added
- PyPI publish workflow.

### Fixed
- Hover reconciliation respects window occlusion when evaluating registered hover widgets.

## 0.2.7

### Added
- `tests/` suite (pytest + pytest-qt, offscreen Qt): public API import surface, version sync with `pyproject.toml`, theme switching, i18n, icon resolver, widget smoke tests, and keyboard regression tests.
- GitHub Actions CI (`.github/workflows/ci.yml`) — Python 3.10/3.11/3.12 matrix, runs `pytest`, `python -m build`, and `python -m twine check`.
- `docs/KEYBOARD.md` — keyboard navigation and focus audit covering 22 widgets, with per-widget status table and a verification walkthrough.
- `docs/DESIGN_LANGUAGE.md` now has a **Token Tiers** section classifying palette tokens as Required / Optional / App-specific extensions, with light/dark defaults and consumer notes.
- `[project.optional-dependencies] dev = ["pytest", "pytest-qt"]` and `[tool.pytest.ini_options]` in `pyproject.toml`.

### Changed
- `Button` is now keyboard-activatable: `StrongFocus` policy, Space/Enter/Return triggers the full `pressed → released → clicked → shortClicked` sequence (including menu/toggle/scrollable behavior), and a focus ring is painted around the button when focused.
- `Button` variant `"primary"` is deprecated and normalized to `"surface"` with a warning.
- Button underline thickness is capped at 3 px with a warning when callers request a larger value; the demo playground now uses the same 3 px limit.
- The demo button playground now clamps corner-radius controls to half of the current button width/height instead of using a fixed radius ceiling.
- Custom-painted hover controls now share a hover coordinator that reconciles registered widgets from global pointer/container events and clears stale hover states on leave, hide, disable, and app deactivation. `RadioButton`, `CheckBox`, `Button`, `Switch`, `Slider`, `ComboBox`, `ScrollableComboBox`, `InstancesCounterButton`, `MinimalistScrollBar`, dropdown rows, simple option rows, and rating list items use the shared lifecycle.
- `Switch` is now keyboard-activatable: `StrongFocus` policy, Space/Enter/Return toggles, focus outline painted around the track.
- `BaseFlyout` (and its `SimpleOptionsFlyout` / `IconActionFlyout` / `IndexedToggleFlyout` subclasses) closes on `Escape` and accepts focus (`StrongFocus`).
- `UnifiedFlyout` accepts focus (`StrongFocus`) and closes on `Escape`.
- `ScrollableComboBox` is now Tab-reachable (`ClickFocus` → `StrongFocus`).
- `CalendarDayButton` becomes keyboard-activatable automatically via the `Button` fix.

### Removed
- `Button(circular=...)`, `ButtonConfig.circular`, `setCircular(...)`, `set_circular(...)`, and `isCircular()` were removed. Use `corner_radius=` or `setCornerRadiusPx(...)` for round button geometry.
- Visual references to "improve-imgsli v9" from source comments and public docs (`palettes.py`, `unified_flyout/{panel,layout,simple_adapter}.py`, `docs/API_CATALOG.md`, `demo/config.py`). Provenance retained only in `docs/ROADMAP.md` and `docs/ARCHITECTURE.md`.

## 0.2.6

### Fixed
- Avoid over-normalizing already well-sized filled SVG glyphs, which made icons such as pause/play appear too heavy.
- Cache resolved icons and normalized icon pixmaps to avoid repeated SVG rasterization and alpha scanning during frequent repaints such as drag ghost movement.

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
