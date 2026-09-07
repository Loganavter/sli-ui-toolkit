# Changelog

## Unreleased

### Breaking

- **`NavigationSection.focus_first/last` now require `reason: Qt.FocusReason`** — `focus_first(self, ref_x=None, *, reason: Qt.FocusReason)` / `focus_last(..., *, reason)`. All sections (`ToolbarRowsSection`, `IconListNavSection`, `SessionPickerSection`, `TabStripSection`) and every `NavigationManager` call site (`register` bootstrap, `focus_section_for_owner`, `_neighbor` handoff, `eventFilter` bootstrap) now pass `NavigationManager.current_focus_reason()` / `nav_graph.focus_reason()`. Old `spec.focus_first()` without `reason` raises `TypeError`.
- **`NavigationManager.declare_graph(specs)` added** — explicit top→bottom graph declaration replaces implicit ordering by `register()` call order. `register()` remains for dynamic tab/flyout sections but is deprecated for static shell.

- The unified flyout (dual-list picker) and the rating row moved out of the
  toolkit into the host application (Improve-ImgSLI `src/ui/widgets/`).
  Removed from the toolkit: `UnifiedFlyout` / `UnifiedFlyoutItem` /
  `SimpleUnifiedFlyoutStore` / `SimpleUnifiedFlyoutController` /
  `RatingListItem` and the whole `unified_flyout` package. The generic,
  reusable part stays as a new public widget: **`ListPanel`** +
  **`ListRowSpec`** (scrollable multi-select list panel with marquee
  selection, drag&drop drop indicators and a host-supplied row factory;
  exported from `sli_ui_toolkit.widgets`). Pure multi-move list helpers
  moved to `sli_ui_toolkit.ui.widgets.helpers.multi_move`. The demo app's
  `flyouts_page.py` now shows a `ListPanel`-based assembly example.
- Title-bar menus moved out of the toolkit. `TitleBarMenu` / `TitleBarMenuStrip`
  and `CustomTitleBar.set_menu_strip` are **removed**; `TitleBarPresets.app_shell`
  now takes `leading: QWidget | None` instead of `menus=`. `CustomTitleBar` is a
  generic shell — hosts inject their own leading-zone widget (e.g. File/Help
  trigger buttons) via `set_leading`/`app_shell(leading=…)` and open their own
  dropdowns (toolkit `ContextMenu` with an explicit `surface=`) as the app
  decides (popup vs in-window). The toolkit no longer knows about
  `context_menu_surface` for the title bar.

### Added

- **`declare_toolbar_navigation(owner, rows, tag="toolbar")`** — declarative one-liner for toolbar/panel navigation (`ToolbarRowsSection` via `NavigationManager.register`). Alias to `declare_navigation_rows` with toolbar-specific naming (Phase 3 `plan_navigation_simplification.md`). Migrated `tabs/image_compare` and `tabs/multi_compare` from 15-line `_toolbar_rows` + `_register_nav_section` to one call.
- **`HelpDialog` focus restore simplified** — `_restore_focus_after_window_change` (116 → ~30 lines) now delegates to `NavigationManager.focus_section_for_owner` / `AutoNavigationSection.focus_first` instead of manual `findChildren(StrongFocus)` + `global Y` sort duplicate. Behavior: keep focus if still inside dialog, else restore to same column via declarative sections. Matches `Settings` dialog pattern.

- **`OverlayScrollbarConfig` scrollbar policy API** — declarative preset (`reserve_space`, `reserve_width`, `gap`, `auto_hide_seconds`) mirroring `ButtonConfig`: `OverlayScrollArea(config=...)` plus per-field ctor kwargs (`reserve_scrollbar_space`, `scrollbar_width`, `scrollbar_gap`, `scrollbar_auto_hide`, `corner_radius` — kwargs win, `scrollbar_auto_hide` uses a sentinel so explicit `None` still means "persistent bar"). New live setters/getters: `set_scrollbar_width` / `scrollbar_width`, `set_scrollbar_gap` / `scrollbar_gap`, `reserve_scrollbar_space()`, `scrollbar_auto_hide_seconds()`, `set_scrollbar_config` / `scrollbar_config`. Exported from `sli_ui_toolkit.widgets`; documented in `docs/user/INPUTS_API.md`.
- **`ListPanel` scrollbar policy passthrough** — `ListPanel(..., scrollbar_config=...)` forwards an `OverlayScrollbarConfig` without baking in any host's policy (defaults = toolkit defaults), plus `panel.set_scrollbar_config` / `panel.scrollbar_config()` delegators and `config=` spec fields so the policy shows in the UI inspector. Hosts wanting a persistent bar (e.g. Improve-ImgSLI unified picker) pass `OverlayScrollbarConfig(auto_hide_seconds=None)`.
- **`OverlayScrollArea` smooth wheel scrolling** — wheel deltas now
  accumulate into a target scroll position and the viewport eases toward it
  Chrome/Firefox-style (timer-driven ease-out at ~60fps, zero idle cost).
  Direction follows the Qt convention (wheel up moves the viewport toward
  the top); touchpad `pixelDelta` and `ScrollBegin` phases are handled;
  external `setValue` (thumb drag, keyboard, programmatic scroll) cancels
  the glide instantly. The mirrored `MinimalistScrollBar` thumb glides with
  the content.
- **`VirtualListController` / `RowPool` incremental rebinding** —
  `RowPool.rebind(reuse=True)` keeps slots whose item index stays inside
  the window: they are repositioned without re-running `bind()`, so a
  scroll step binds only the rows entering the window (the previous code
  re-bound every visible row on every scroll step — visible jank at the
  start of scrolling on heavy rows). `VirtualListController.rebind(force=True)`
  (used by `ListPanel` rebuild/sync paths and `set_count`) restores a full
  rebind when item data may have changed. The ComboBox dropdown keeps full
  rebinding (`reuse=False` default) because its bind index is positional.
  `RowPool` also gained `height_fn`/`offset_fn` for variable-height lists
  and `indexed_widgets()` for the live index→widget map.
- **`MinimalistScrollBar` animated visuals** — thumb thickness now eases
  between idle/hover/drag (4→6→10px) and opacity fades instead of snapping
  (timer-driven, stops when settled). `set_animated_visible(bool)` shows/
  hides with a fade; `set_auto_hide(seconds)` (default `1.2` on
  `OverlayScrollArea`, off elsewhere) fades the bar out after inactivity —
  scroll activity, hovering, and dragging re-show it. Fade-ins are never
  interrupted by the idle timer. `OverlayScrollArea.set_scrollbar_auto_hide(
  seconds | None)` toggles it per area.

- **`CustomTitleBar` keyboard navigation** — `StrongFocus` policy, Left/Right
  arrow-key navigation between focusable title bar buttons via QApplication
  event filter. `_focusable_buttons()` collects visible, enabled, StrongFocus
  descendants. `focus_first_button()` / `focus_last_button()` for programmatic
  focus. `_set_child_focus()` helper temporarily weakens parent StrongFocus
  to work around Qt's parent-chain focus redirection.
- **`NavigationManager` flyout section registration** — `BaseFlyout.show()`
  now registers the flyout as a `NavigationSection` via
  `_FlyoutNavigationSection`, and `hide()` unregisters it. This ensures
  arrow keys are routed to the flyout when it has focus, instead of being
  claimed by the underlying section via parent-chain `isAncestorOf`.
- **`BaseFlyout._grab_focus()`** — weakens StrongFocus ancestors, focuses
  the first leaf StrongFocus child (skipping containers like QScrollArea),
  uses `MouseFocusReason` so no focus ring appears on mouse-initiated
  show. Saves `_previous_focus_widget` before `_register_nav_section()`
  so the original trigger widget is correctly restored on hide.
- **`BaseFlyout` generic keyboard navigation** — `keyPressEvent` handles
  Up/Down/Left/Right (move focus between StrongFocus children with
  wrap-around) and Enter/Return (click on `QAbstractButton` children).
  All flyout subclasses (SimpleOptionsFlyout, IconActionFlyout,
  IndexedToggleFlyout, FontSettingsFlyout) get keyboard navigation for
  free without custom `keyPressEvent` overrides.
- **`ContextMenu` keyboard navigation** — `StrongFocus` policy, `keyPressEvent`
  handles Enter (activate focused row), Escape (close menu or submenu),
  Up/Down (navigate rows via `_navigate_rows()`).
- **`ContextMenu._spec` on rows** — rows store their `ContextMenuAction`
  spec for Enter key activation in `keyPressEvent`.
- **`NavigationSection.extra_keys`** — protocol property (default
  `frozenset()`). Flyout sections declare additional keys (Enter, Escape)
  they want intercepted. `NavigationManager.eventFilter()` checks
  `extra_keys` for non-arrow keys and routes them through `navigate()`.
- **`NavigationManager.should_intercept(key, focused)`** — public API for
  app-level event handlers to check if a registered section wants to
  intercept a key. Used by `app_event_handler.py` to yield Escape to
  flyout sections instead of consuming it locally.
- **`BaseFlyout.focus restoration`** — `_restore_focus_policies()` restores
  focus to `_previous_focus_widget` with `MouseFocusReason` (no ring).
  Focus is restored in `hide()` before fade animation starts to avoid
  intermediate CsdMenuTrigger flash.
- **`BaseFlyout.on_hide_fade_finished()`** — hides flyout BEFORE clearing
  snapshot / restoring children to prevent 1-frame flash at full opacity.
- **`Button` auto-appends `FocusLayer`** — even with custom `layers=`
  parameter, `FocusLayer()` is appended if not already present. Subclasses
  with custom layer pipelines (ContextMenuRow, _SimpleRow) get focus ring
  without explicit `FocusLayer()` in their layer list.
- **`AdaptiveTabStrip` keyboard navigation** — `Left`/`Right` between tabs,
  `Home`/`End` for first/last tab, `Delete`/`Backspace` to close the current
  tab (emits `tabCloseRequested`). `Down`/`Up` via `focusNextChild()`/`
  `focusPreviousChild()` for cross-widget traversal. `StrongFocus` policy
  on the strip for Tab/Backtab traversal. Focus ring (accent-colored
  `QPainterPath` outline) visible only for keyboard-granted focus (matches
  `Button`'s `FocusLayer` style). `navigateOutRequested(+1)` signal emitted
  when `Down` is pressed on the add button — the host app connects to this
  to focus the content area.
- **`RecentHeaderBar` keyboard navigation** — `Left`/`Right` between header
  control buttons. `Down` on the last button hands off to the panel's
  `focus_recent_item()`. `Up` on the first button propagates to the parent
  (session picker create-cards). `Enter`/`Return` activates the focused
  button via `clicked.emit()`.
- **`ContextMenu._visible_menus` registry** — class-level `set` tracking
  currently visible in-window context menus. `close_visible()` classmethod
  closes the most-recently-shown menu and returns `True`. The host app
  queries this in its global `EventHandler` to dismiss context menus on
  `Escape` before the keyboard handler consumes the event. Follows the same
  pattern as `FlyoutManager` for outside-click dismissal.
- **`ContextMenu` ESC dismissal for in-window menus** — since in-window
  menus have `NoFocus` policy (required for Wayland/QRhi activation
  stability), `keyPressEvent` never fires. The `_visible_menus` registry
  provides a clean app-integration point instead of per-widget event filters.

- Minimal scrollbar public API trimmed to two names exported from
  `sli_ui_toolkit.widgets`: `MINIMAL_SCROLLBAR_WIDTH` (the bar's fixed
  width, for positioning) and `overlay_scrollbar_max_inset()` (the single
  always-on footprint value = width + gap + margin). Gap, overlay margin,
  thumb thicknesses and track padding are internal to the bar. The combobox
  dropdown overlay, flyout list views and the timeline widget now read the
  public API instead of hardcoding widths; the app-side recent-shelf grid
  reserve (`ITEMS_MARGIN_RIGHT`) is derived from it too. The timeline's own
  drawn footer scrollbar keeps its metrics as local named constants.
- `OverlayScrollArea.overlay_scrollbar_inset()` now returns a single fixed
  value — the bar's maximum width plus a small margin (was the bare bar
  width) — so overlay-mode content never sits flush against the thumb in
  any state (idle/hover/drag) and hosts don't chase the live thickness.
- `measure_text_width(fm, text)` — the toolkit's text-width normalizer, now
  public from `sli_ui_toolkit.ui.managers.ui_font` /
  `sli_ui_toolkit.widgets` (was `_measure_text_width` in
  `context_menu.models`, kept as a back-compat alias there):
  `max(horizontalAdvance, boundingRect) + 8px` so panels sized from it never
  clip painted glyphs.
- `ButtonRow(size=None)` — render the row with the current default UI font
  (`ui_font()`) instead of an explicit pixel size, matching the host's normal
  text (SimpleOptionsFlyout default rows / HUD labels). Explicit pixel sizes
  unchanged.
- `SimpleOptionsFlyout.set_rows(rows)` — generic list fill: the composite owns
  flyout display, long-list scrolling and sizing; hosts supply arbitrary row
  widgets (any `QWidget`; `clicked`-bearing rows are wired to `item_selected`
  with the row index). `populate(labels, current_index)` remains the
  convenience path for plain single-line rows. New `rows()` accessor;
  `row_widget(index)` now indexes installed rows. Panel sizing follows each
  row's `sizeHint()` (variable heights supported).
- `SimpleOptionsFlyout.set_list_padding(padding)` — host-controlled inset
  between the panel border and the row list (`int` or `(l, t, r, b)`).

- `BaseFlyout.show_aligned(..., animation_axis="diagonal")` — new slide
  mode alongside `"auto"`/`"vertical"`/`"horizontal"`: both X and Y travel
  the full `distance`/`animation_distance` independently (each clamped
  against the anchor edge the same way `"vertical"`/`"horizontal"` already
  do on their own axis), instead of `"auto"`'s single fixed distance split
  across the real anchor→flyout unit vector. For a corner-aligned flyout
  (e.g. `anchor_point="top-left"` / `flyout_point="bottom-right"`) where
  the anchor and flyout sizes differ a lot on one axis — a narrow icon
  button anchoring a much wider panel — `"auto"`'s vector ends up dominated
  by whichever axis has the bigger center-to-center offset, shrinking the
  other axis's slide to a few barely-visible pixels; `"diagonal"` keeps
  both axes clearly visible regardless. Found via ImgSLI's
  `FontSettingsFlyout.show_top_left_of`, which wanted a visible slide in
  both directions and got a slide that looked purely vertical under
  `"auto"`.
- `BaseFlyout.set_background_brush(brush)` / `.set_border_color(color)` /
  `.set_shadow_color(color)` (+ matching getters) — per-instance overrides
  for the flyout panel's fill, stroke, and drop-shadow tint, `None` falls
  back to the theme token. Same shape as `Button`'s style API
  (`set_background_color`/`setBorderColor` in `style_api.py`). Accepts a
  flat `QColor`, any `QGradient`, or an existing `QBrush` (e.g. built from
  a `QPixmap` for a repeating texture) for `set_background_brush`. Texture/
  gradient brushes are anchored to the panel's own corner via
  `painter.setBrushOrigin`, not `(0, 0)` of the (shadow-inset) flyout
  widget. `draw_rounded_shadow`/`paint_shadowed_surface` gained an optional
  `color`/`shadow_color` keyword (default `None` = the historical opaque
  black) to support the shadow tint; both are backward compatible for
  every other existing caller (tooltips, combobox overlay, unified
  flyout), which don't pass it. See "Custom surface style" in
  `docs/user/FLYOUT_SYSTEM.md` — deliberately does not attempt live
  backdrop blur/frosted-glass (expensive, awkward over a QRhi canvas);
  approximate that with a semi-transparent gradient instead.
- `FlyoutManager.request_hide` now logs a `DEBUG`-level message with a
  stack trace whenever a `pinned=True` flyout is hidden. The manager can't
  distinguish an intentional app-level hide from a bug bypassing the
  pinned exemptions (both are just a `.hide()` call), so this is a
  diagnostic aid, not an enforced invariant — see "Diagnosing unexpected
  pinned-flyout closes" in `docs/user/FLYOUT_SYSTEM.md`.
- `sli_ui_toolkit.managers.LayerStack` — named z-order layers for
  `FlyoutManager.ensure_overlay_stacking`. Replaces the previous hardcoded
  "`context_menu` group always raised above everything else" special case
  with a host-configurable ordered layer list (`FlyoutManager.set_layer_stack`
  / `.layer_stack()`). The default stack is unchanged from prior behavior
  (`base` < `context_menu`) — hosts that never call `set_layer_stack` see no
  difference. First phase of the flyout layer/rule system plan, see
  `docs/dev/FLYOUT_LAYER_SYSTEM_PLAN.md`.
- `GroupShowPolicy.define_group(group, parent=...)` / `configure_group(...,
  parent=...)` — groups can now inherit another group's `dismisses` /
  `claim_active` rules recursively instead of repeating them, overriding
  only the fields they need. `GroupShowPolicy.coexists_with(a, b)` is
  symmetric sugar for "opening either group never dismisses the other",
  independent of each group's own dismiss set. Second phase of the flyout
  layer/rule system plan, see `docs/dev/FLYOUT_LAYER_SYSTEM_PLAN.md`.
- `FlyoutManager.link(parent, child)` / `.unlink(...)` / `.linked_children(...)`
  — declare a flyout as part of another one's family (submenu, color-picker
  opened from inside a settings flyout, etc). Hiding the parent (through
  any dismiss path) cascades to hide every linked child recursively;
  re-showing the parent (e.g. a pinned HUD's `reposition()`) calls
  `child.reposition()` for visible children automatically. Third phase of
  the flyout layer/rule system plan, see
  `docs/dev/FLYOUT_LAYER_SYSTEM_PLAN.md`.
- `ChainShowPolicy` — `FlyoutManager.set_show_policy` now also accepts a
  `list`/`tuple` of policies, combined as: `should_dismiss` AND-combined
  (any policy can protect a pair from dismissal), `should_claim_active`
  priority-order (first policy wins). Fourth phase of the flyout
  layer/rule system plan, see `docs/dev/FLYOUT_LAYER_SYSTEM_PLAN.md`.
- `ButtonGroup(..., border_radius=8, corner_radii=None)` — per-corner border
  radii, same `(top-left, top-right, bottom-right, bottom-left)` convention
  and `CornerRadii`/`normalize_corner_radii` helper as `Button`'s
  `ShapeSpec`. `border_radius` stays the uniform shorthand;
  `corner_radii` overrides individual corners. Also runtime-adjustable via
  the new `set_corner_radii(corner_radii=None, *, border_radius=None)` /
  `corner_radii()` methods — e.g. squaring off a group's bottom corners
  while a flyout is docked flush underneath it, then restoring them when
  the flyout closes.
- `ButtonGroup.label() -> str` — public getter for the group's caption
  (`set_label`/`set_label_text` already existed; reading it back required
  poking the private `_label` attribute). Lets a companion widget (e.g. a
  flyout docked under the group) mirror the same caption instead of
  duplicating the string.
- `BaseFlyout.trigger_widgets()` / `.trigger_contains_global(global_pos)` —
  split out from `anchor_widgets()`/`anchor_contains_global()`. Defaults to
  `anchor_widgets()`, so every existing flyout (dropdown, context menu,
  ...) keeps its current behavior unchanged. `FlyoutManager.eventFilter`'s
  `MouseButtonPress` handling now uses `trigger_contains_global` (not
  `anchor_contains_global`) to decide "clicked the trigger while open,
  dismiss" — override `trigger_widgets()` to return `()` (or a narrower
  subset) for a flyout whose anchor is used purely for positioning against
  a widget that isn't itself a click-to-toggle trigger, e.g. a hover-driven
  flyout anchored to a whole button group for width/placement rather than
  a single button. Without the split, clicking *any other* button in that
  group while the flyout was open read as "clicked the trigger, dismiss"
  and closed it — found via ImgSLI's magnifier-settings hover flyout, whose
  anchor is the whole magnifier button group; toggling the magnifier
  button itself (a sibling in that group) was closing the flyout.
  `anchor_contains_global`/`anchor_widgets()` are unchanged and still drive
  positioning, anchor-move auto-dismiss, and the generic outside-click
  "am I inside any open flyout" check.

- `IconListWidget(button_factory=...)`: lets a caller replace the default
  nav-row `Button` per item, for custom row layouts (badges, a different
  `variant`, `regions=`, multi-line text) without subclassing
  `IconListWidget` or reaching into its internals. Rows built through a
  custom factory still get layout stretch, `FocusPolicy.NoFocus`, click→
  selection wiring, and CHECKED-state syncing
  (`setRegionChecked("_main", ...)`) from `IconListWidget`, but the widget
  leaves their icon/foreground styling alone — that's the custom factory's
  responsibility, same as any other `Button` variant.
- `ComboBox` "gear-shifter" drag-select: press-and-hold the field for
  `GEAR_HOLD_MS` (450ms), or drag it sideways/vertically past
  `GEAR_DRAG_THRESHOLD_PX` (8px) right after pressing, to open the dropdown
  and scrub through rows by dragging — like sliding a gearbox knob into its
  slot. A stationary outline frame (`_GearFrame`, drawn at the field's own
  screen rect) marks the fixed reference point; whichever row is behind it
  gets the hover highlight and is what gets committed on release. A plain
  click/release still just toggles the list as before, and dropdowns with
  more rows than fit on screen fall back to plain scroll-to-select (the
  window can't be dragged to track an unbound row count). Implementation:
  - New `GearDragCapability` (`ui/widgets/comboboxes/capabilities/`),
    attached via `ComboBox.attach_capability()` the same way `Button` attaches
    `LongPressCapability` — `ComboBox` now opts into `long_press=True` on its
    own `Button.__init__` call to get the hold gesture.
  - Below the overflow threshold, the whole popup window (card + shadow +
    rows, one widget) physically translates with the drag instead of the
    list scrolling internally, so it reads as sliding the actual rows past a
    fixed field rather than a normal scrolling list.
  - On release, the popup snaps the rest of the way to the exact
    item-boundary offset (`QPropertyAnimation` over `GEAR_SNAP_DURATION_MS`,
    40ms) so the focused row lands perfectly centered under the field, then
    holds there for `GEAR_SNAP_HOLD_MS` (250ms) before the dropdown closes,
    instead of collapsing the instant the row lines up.
  - The real cursor is hidden (`Qt.BlankCursor`) for the gesture's duration
    since the popup moves under a stationary pointer; app-wide hover
    (`HoverCoordinator`) is explicitly suppressed on dropdown rows during the
    drag so it can't light up whatever row the moving popup happens to pass
    under, layering a second highlight on top of the gear frame's own.
  - Only arms on genuine OS-delivered input (`event.spontaneous()`) — mouse
    events synthesized in-process can't trigger the gesture.
- `Button(underline_fade=...)` / `setUnderlineFade(bool | None)`: turns the
  tip fade on/off per button. `None` (default) follows the process-wide
  default (`get_default_underline_fade()`, itself `True` unless changed).
- `set_default_underline_fade(bool)` / `get_default_underline_fade()` and
  `configure_toolkit(default_underline_fade=...)`: process-wide default for
  the tip fade, same pattern as `set_default_defer_click`. A host that finds
  the fade doesn't suit its visual style can turn it off globally in one call
  instead of passing `underline_fade=False` at every `show_underline=True`
  call site.
- `Button(underline_tongue_reach=...)` / `setUnderlineTongueReach(float | None)`:
  controls how high (px) the underline's end caps ("tongues") are allowed to
  climb the sides, independent of `underline_thickness`. `0` gives hard square
  ends (no corner rounding followed at all); `None` (default) matches the
  button's own corner radius, i.e. the old look; larger values climb further
  up the sides. If `thickness` needs more room than the corner radius alone
  provides, the excess fills *upward* toward `tongue_reach` rather than
  overflowing sideways past the rounding.
- `Button(underline_ring=...)` / `setUnderlineRing(bool)`: draws the underline
  as a closed frame around the whole button instead of just a bottom band —
  still split into `underline_color`'s zones the same way.
- `DrawContext.underline_tongue_reach` / `DrawContext.underline_ring`,
  `UnderlineConfig.tongue_reach` / `UnderlineConfig.ring` (low-level painter
  API, `sli_ui_toolkit.ui.widgets.helpers.underline_painter`).
- `OverlayScrollArea.overlay_scrollbar_inset() -> int`: how many px of content
  clearance the overlay bar currently needs — `0` when
  `reserve_scrollbar_space` is on (the bar already gets its own viewport
  margin) or when the bar isn't visible (nothing overflows), else the bar's
  width + gap. Lets callers that manually lay out content inside the scroll
  area (rather than via `setWidget` + a Qt layout) reserve exactly the live
  clearance instead of hardcoding a guess at the bar's width that wastes
  space whenever there's nothing to scroll.

- `TextView.set_line_number_start(n)` — VS Code-style line-number gutter:
  right-aligned muted numbers (starting at `n`, e.g. the class's line in
  its source file so the gutter matches the actual file) plus a thin
  separator; text, selection, caret and hit-testing shift by the gutter
  width. `None` (default) disables it. Code mode only — document mode never
  shows the gutter. Exposed on both `TextView` and its painted `TextCanvas`.
- UI inspector Code section — ONE unified editable `TextView` (styled like
  the app's recent-projects shelf: a rounded panel well behind the text,
  `variant="default"` toggle button) containing the generated
  **Configuration (live values)** snippet (a synthetic constructor call
  built from `WidgetInspection.config` — enums render as `Type.MEMBER`,
  colors as hex, `REF` child widgets as `Type(...)` placeholders, nested
  field blocks as dicts) followed by the widget class source. Any other
  code in the source file is collapsed into a plain gap row (`·····`);
  clicking the row expands that region inline, clicking again collapses
  it. VS Code-style folding display: the gap row's gutter shows the last
  line number before the hidden block and the next row its real number
  right after (e.g. `12` then immediately `17`), a disclosure arrow (`▸`)
  sits in the gutter left of the gap row's number, and the synthetic
  config snippet is marked with a dot (`·`) instead of a line number so
  the file counter never restarts below it. The gutter width (numbers + a
  constant arrow slot) is identical across compact/expanded/full so the
  content's left offset never moves. The **Full/Compact** button
  (top-left) expands/collapses everything at once and flips its own
  label. **Preview** compiles the edited class and constructs a live
  instance (the current config values become the constructor kwargs;
  non-reconstructable values like `REF` placeholders are skipped, and
  REQUIRED args the widget does not store as attributes — e.g.
  AdaptiveTabStrip's `add_icon`/`close_icon` — are filled with `None` so
  the preview still builds; the required-arg resolution walks the MRO, so
  forwarding subclasses (`__init__(self, *args, **kwargs)`) cannot hide
  the real parameters) in a panel below the editor; while open, it
  re-builds on every edit (debounced 300ms), so the effect of a change is
  visible before saving — compile/construct errors are shown in the panel
  (with the exact attempted constructor call) instead of crashing.
  **Apply** hot-patches the LIVE widget class in place (the edited class
  region's methods/attributes are copied onto the real class — the actual
  widget changes where it sits, same instance, host wiring intact, all
  instances of that class affected — and repaints); **Revert** restores
  the snapshot of the original class taken when the inspection opened.
  Every Apply/Preview result is reported in the preview panel (auto-opened
  on failure so nothing is silent) with a debug line: the compiled class,
  the resolved constructor signature, the kwargs used and the skipped
  values. Config-snippet kwarg extraction now resolves module-level names
  through the widget's module namespace (e.g.
  `CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT`), so enum-valued config
  no longer silently drops out of the preview construction.
- Fixed: `FlyoutFadeController.start_hide_fade` now clears the flyout's
  `_show_animation` reference after stopping the show animation — a
  lingering reference pointed at the `deleteLater`-ed C++ animation and
  crashed the next hide (RuntimeError: Internal C++ object already
  deleted) in rapid show/hide/reposition cycles (slider-hint style). The
  gutter numbers the actual file lines (starting at the class statement;
  the snippet is 1-based). `Save` reconstructs the whole file with the
  edited class region — the snippet and gap rows are never written to
  disk.
- `TextView.set_line_number_map(mapping)` — explicit per-display-line
  gutter text (for collapsed-gap views; lines missing from the map fall
  back to `start + index`), `TextCanvas.set_fold_lines(lines)` (gutter
  disclosure arrows for collapsed rows, left of the line number; an empty
  set keeps a constant arrow slot reserved, `None` disables it — the
  content never shifts between states), `TextCanvas.line_at(y)` (display
  line for a widget-space y — click targeting) and `TextView.canvas()`
  (the painted surface, for event filters). `TextView.set_panel_fill(color)` paints a
  rounded panel well behind the text (viewport fill clipped to the frame
  radius — the recent-projects shelf look); `None` restores the page
  background.

- `Button(text_fit=True)` — grow-to-content sizing for text/rows buttons:
  `sizeHint` tracks the parent row's available width (margins + preceding
  siblings) capped at the full text width, `minimumSizeHint` stays tiny so
  a scroll content can always shrink the button. Pair with a trailing
  `addStretch(1)` in the row (a stretch/Expanding item right-anchors its
  widget in Qt) and a row `marquee=True` for overflowing text.
- `Button` size hints are now rows-aware: a `rows=[ButtonRow(...)]` button
  reports the widest row's text width (measured with each row's own paint
  font) instead of the fixed (36, 36) — `text=` and `rows=` size alike.
- Markdown document mode (help/`TextView`): headings now render on a
  strictly decreasing font scale (`#` 26px → `######` 13px, design px) —
  previously `#`/`##` shared one size and `###`…`######` another. Fenced
  code blocks now render as a shaded rounded box (the long-unused
  `help.code.background` token) with the text inset and the fence language
  label in the box header, instead of bare monospace paragraphs.
- Markdown document mode: fenced code blocks lost their line breaks —
  `QTextLayout` treats `\n` as a soft break, so without forced wrapping the
  whole block collapsed into one line. Segment layout now splits on `\n`
  (one fragment per line; blank lines reserve the font's line height), and
  inline `` `code` `` spans get the monospace font **and** the
  `help.code.background` tint instead of a bare font-family change.
- Markdown document mode: code text could disappear or render with
  mismatched backgrounds — two stacked PySide6 `QTextLayout` traps:
  `FormatRange.format` holds a *reference* to the `QTextCharFormat`'s C++
  object (the layout draws dangling formats once the Python wrapper is
  collected — formats are now kept alive for the layout's lifetime), and a
  second `setFormats` on an already-laid-out layout silently breaks its
  drawing. Fence blocks no longer set a per-character tint at all (the box
  is their background) instead of stripping it after layout.

- **`SurfaceScrollArea`** (`sli_ui_toolkit.widgets`) — scroll area that
  paints its surface from a theme token (default `dialog.background`),
  extending `OverlayScrollArea` (overlay scrollbar kept). The token is
  resolved to a widget-level `background-color` stylesheet on the scroll
  area — it cascades to the viewport and the content widget, survives
  `QStyle::polish` at `show()` (a per-widget palette does not), and is
  re-tinted on `theme_changed`. `set_surface_token(token)` switches at
  runtime; `set_surface_token(None)` pins the viewport and the content
  widget transparent instead, so a host ancestor that paints the surface
  shows through (the `SimpleOptionsFlyout` pattern). Closes the stock
  scroll-container black-substrate mechanism for toolkit widgets: stock
  `QScrollArea` viewports and `setWidget`-flipped content widgets auto-fill
  the `Window` role, darker than the dialog surface token (dark `Window`
  `#1e1e1e` vs `dialog.background` `#2b2b2b`).


- `Button(overlay_painter=...)` — high-level parameter accepting a custom overlay painter callback `(painter, rect)` or `(painter, ctx, tm)` without requiring `Layer` subclassing or pipeline manipulation.
- `Button(extra_layers=...)` — parameter to append custom `Layer` instances to the default painter pipeline.
- Exported `Layer`, `DrawContext`, `default_layers`, `OverlayPainterLayer`, `OverlayPainterCallback`, `BackgroundLayer`, `RippleLayer`, `ContentLayer`, and other layer primitives in `sli_ui_toolkit.widgets` and `sli_ui_toolkit.ui.widgets.buttons`.
- `emerald_button_demo.py` — demo of a multi-region `Button` where each octagonal
  gem facet is an independent `ButtonRegion` with its own `path_fn`, `override_bg_color`,
  and per-facet hover/ripple via the toolkit pipeline.

### Changed

- **`ColorSettingsButton` uses `bind_auto_preview`** — `bind_flyout(..., side="above")` → `bind_auto_preview(..., side="above")` (with fallback). Hover/focus preview + Enter interactive + Esc/focusOut wiring now via `_AutoPreviewController` event filter, not per-anchor `enterEvent/leaveEvent/focusIn/keyPress/focusOut` duplication. Business signals (`elementHovered`, underline colors) kept.

- **Debug streams unified on env-gated helpers** (host `LOGGING.md` unique-prefix convention) — every subsystem stream is now a call-time `_xxx_debug_enabled()` / `_xxx_debug()` pair over `core.debug_flags` (permissive: any non-empty except `0/false/no/off`), off by default even under host `--debug`, existing `[prefix]` tags unchanged. New canonical `SLI_*` vars with legacy aliases: `SLI_NAV_DEBUG` (`UI_NAV_DEBUG`, shared with host router), `SLI_FLYOUT_DEBUG` (`IMGSLI_FLYOUT_DEBUG`, `FLYOUT_DEBUG`), `SLI_TIMELINE_DEBUG` (`IMGSLI_TIMELINE_DEBUG`, `IMGSLI_VIDEO_EDITOR_DEBUG`), `SLI_SCROLLBAR_DEBUG` (`IMGSLI_SCROLLBAR_DEBUG`), `SLI_DND_DEBUG` (`IMGSLI_DND_DEBUG`, `IMGSLI_IMAGE_COMPARE_DEBUG`, `IMGSLI_IC_DEBUG`); unchanged singles `SLI_UI_NAVLIST_DEBUG`, `SLI_UI_COLORS_DEBUG`, `SLI_RESIZE_DEBUG`. New shared helpers: `core/debug_flags.py`, `base_flyout/debug.py`, `timeline_widget/debug.py`.
- **No more host-app leaks in the toolkit** — `logging.getLogger("ImproveImgSLI...")` and import/call-time `logger.setLevel` mutations removed from all unified streams (timeline, flyout, DnD overlay, scrollbar, resize); `SLI_TOOLKIT_DEBUG` / `debug_env_var` handling in `core/logging.py` is now permissive like the rest (was strict `=="1"`).
- **Progress-only toast updates are cheap** — `update_toast(..., content=None)` with `actions=None` skips the text/layout/repolish pass and only moves the progress bar (`+update()`); `_set_progress` skips the surface repolish when progress visibility is unchanged; the update path no longer forces `show()`/`raise_()` when already visible and keeps only the scheduled reposition (no synchronous `_position_toasts` per tick).

- **`RadioButton` / `CheckBox` rebased onto `Button`** — were standalone
  `QRadioButton` / `QCheckBox` subclasses with hand-rolled hover animation
  and no keyboard-focus ring; now `Button` subclasses painting the same
  indicator/checkmark geometry through a custom `Layer`, so they pick up
  `FocusLayer`'s ring like every other toolkit control. Two-state only
  (`CheckBox` drops the unused `Qt.CheckState.PartiallyChecked`
  indeterminate state — nothing used it). `isChecked()` / `setChecked()` /
  `toggled` stay API-compatible.
- **`RadioButtonGroup` added** (`sli_ui_toolkit.widgets`) — `Button` has no
  native exclusive-group concept (unlike `QAbstractButton` + `QButtonGroup`,
  which `QRadioButton` got for free, including *implicit* exclusivity for
  radios sharing one parent widget with no `QButtonGroup` at all). Host apps
  using `QButtonGroup` with `RadioButton` must switch to
  `RadioButtonGroup()` — plain Python object, `addButton()` only, no `QObject`
   parent needed.

- **`NavigationManager._WidgetNavigationSection.owns()`** — removed parent-chain
  fallback that incorrectly claimed overlay widgets (flyouts, popups) parented
  inside a section's widget tree. Flyouts now register their own sections.
- **`_FlyoutNavigationSection.navigate()`** — creates synthetic `QKeyEvent`
  and delivers it directly to the flyout's `keyPressEvent()`, bypassing
  `WA_ShowWithoutActivating` which prevents normal Qt keyboard routing.
  All handled keys (arrows, Enter, Escape) are consumed.
- **`NavigationManager.eventFilter()`** — expanded to intercept non-arrow
  keys (Enter, Escape) via `extra_keys` on registered sections. Only
  consumed if a section's `navigate()` returns `True`.
- **`BaseFlyout._grab_focus()`** — no more `QTimer.singleShot`. Weakens
  ancestors, stores them on `self._weakened_focus_ancestors`, restores
  in `_restore_focus_policies()` called from `_finish_hide()`. Focuses
  first leaf StrongFocus child using `MouseFocusReason`.
- **`BaseFlyout.show()`** — saves `_previous_focus_widget` BEFORE
  `_register_nav_section()` to correctly capture the trigger widget.
- **`BaseFlyout.hide()`** — restores focus BEFORE fade animation starts
  to avoid intermediate focus jump to CsdMenuTrigger.
- **`ContextMenu` focus policy** — changed from `NoFocus` to `StrongFocus`
  so the focus ring renders and keyboard events reach `keyPressEvent`.
- **`_AdaptiveTabBar` focus policy** — changed from `NoFocus` (QWidget
  default) to `StrongFocus` so the tab bar participates in Tab/Backtab
  traversal and can receive keyboard focus for arrow-key navigation.
- **Pipe tables in document/markdown mode** — `parse_help_blocks` now
  parses GFM-style pipe tables (``| a | b |`` rows, optional bold header
  when the next line is a `---` separator, `\|` escapes, short rows padded)
  into `TableBlock`; the table layout was generalized from two columns to
  N columns with an optional header row (header cells bold, divider under
  the header). Tables render as bordered grids with per-column dividers —
  the same surface the app's Image Properties dialog uses. `TableBlock` is
  now exported from `sli_ui_toolkit.ui.widgets.composite.help_document`.
- **`IconListWidget` in-place search filtering** — `set_search_text(query)` /
  `set_no_results_text(label)` / `IconListItem.search_texts`: rows stay built,
  filtering toggles visibility via a ComboBox-style visible-index pool (no
  per-keystroke widget rebuilds); matching reuses the ComboBox
  `match_score` fuzzy scorer over pre-normalized texts. `count()`/`item()`/
  `row_button()`/`setCurrentRow()` operate on visible rows while filtered.
- **`SidebarDialogShell(resizable_sidebar=True)`** — draggable sidebar |
  content splitter (`.splitter`); the configured `sidebar_width` becomes the
  sidebar minimum.
- **`SidebarDialogShell(sidebar_header=…)`** — optional widget (e.g. a search
  field) pinned above the nav list; the sidebar column tracks the configured
  width and stays visible when the nav list is collapsed. Used by the app's
  Settings and Help in-dialog search.
- **`TextView`** (`ui/widgets/composite/text_view/`) — unified painted text
  rendering + editing composite (no stock Qt text widgets). Two modes on the
  same painted surface:
  - **Code mode** — monospace lines with Python syntax spans
    (`python_line_spans` / `python_span_colors`: keywords use the `accent`
    token, comments/strings/numbers/decorators/`def`-names themed) and a
    full painted editor: caret, anchor/focus selection (double-click word /
    triple-click line, drag extension with 4px threshold), undo stack,
    clipboard, Tab → 4 spaces. API: `set_text`/`text`,
    `enter_edit_mode`/`exit_edit_mode`/`editor`/`is_editing`,
    `changed` signal.
  - **Document mode** — controlled markdown subset (headings, bold/italic,
    inline code, links, lists, images, figure fences) laid out with the
    help-document engine (`QTextLayout` wrapping, tables): `set_markdown`,
    `plain_text`, `is_document`; offset-based selection (drag, Ctrl+A/C);
    `linkActivated(href)` / `imageActivated(path)` signals, the help image
    lightbox opens on image click.
  Exported from `sli_ui_toolkit.widgets` (plus `TextCanvas`,
  `TextSelection`, `python_line_spans`, `python_span_colors` and the
  markdown block API). See `docs/user/TEXT_VIEW_API.md` and
  `docs/dev/TEXT_VIEW_PLAN.md`.
- **UI inspector** (`ui/inspector/`) — DevTools-style widget inspection:
  widgets self-describe via co-located `inspect_spec` class attributes
  (config auto-derived from `__init__`, curated state with labels, token
  families, Button regions/layers); `inspect_widget()` (spec → duck-typed
  registry → generic fallback); live theme-token capture through the
  `get_color`/`try_get_color` funnel; QSS candidate matching + dead-selector
  analysis; `InspectorWindow` — tabbed panes (TopTabHost, closable via
  `CloseButtonPolicy.ALL`), sidebar sections that auto-hide when empty
  (Object/Config/State/Regions/Layers/Theme/QSS/Layout/Constructor/Code),
  collapsible Layout/Constructor trees with hover highlighting, QSS
  candidates with source + `[matched]`/`[dead]` markers, the `Code` section
  on `TextView` (edit/revert/save of the widget's source file), per-region
  overlay, selection controller. See `docs/dev/FAMILIES.md`.

- `DoubleSpinBox` — float-valued `SpinBox` variant (`single_step`, `decimals`,
  step-grid snapping, `scaled_px`-aware geometry), exported from
  `sli_ui_toolkit.widgets`.
- `UiScale` — process-wide interface scale factor (independent of the OS/Qt
  display factor). `factor()` / `set_factor(value)` (clamped to 0.5–2.5),
  `scaled_px(design)`, `scale_changed(float)`; exported from
  `sli_ui_toolkit.managers` plus the module-level `scaled_px(...)` helper.
  `configure_toolkit(ui_scale_factor=...)` sets it process-wide.
- Fonts now scale: `UiFont.base_font()` / `resolve()` multiply the inherited
  application-font size and design `pixel_size`/`point_size` by the factor;
  `UiFont.apply()` keeps subscribed widgets in sync with `scale_changed` too.
- Icon/corner tokens scale: `read_widget_style()` and `icon_size_qsize()`
  return rendered px (design px × factor); `normalized_icon_pixmap()` cache
  key includes the factor.
- Widget geometry scales live: `CheckBox`, `Switch`, `Slider`, `SpinBox`,
  `CustomLineEdit`, `ComboBox`, `Button` (fixed sizes + `sizeHint`), and
  `CustomTitleBar` read constants through `scaled_px()` and re-flow on
  `scale_changed` (`updateGeometry()` + `update()`, `ThemedWidget` idiom).
- UI scaling is now wired into roughly 80% of the toolkit (widget geometry,
  fonts, icons, margins/spacing through `scaled_px()`, flyout/panel sizes).
  The remaining widgets and painter paths are still being migrated — some
  surfaces may not fully re-flow on a live `UiScale` change yet.
- `TimelineWidget` lane labels scale: the left-gutter track titles and
  channel labels now resolve their painter font through `ui_font()` (like
  the group headers and the ruler already did), so the lane names grow with
  the UI scale instead of staying at the design size. The ruler pass also
  restores the painter font afterwards, so the already scale-resolved ruler
  font no longer leaks into the sticky-gutter label pass (which would have
  multiplied the factor a second time).
- `ProcessConsoleWidget` text scales: the console's monospace font (system
  `FixedFont`) is re-derived with the UiScale factor applied — family kept,
  size multiplied — and re-applied on `scale_changed`, so the log output
  and the command input grow with the interface like every other label.
- Context menus scale: row/separator/section-title heights, icon size,
  paddings, the check gutter and the trailing shortcut/arrow widths are
  now derived through `scaled_px()` (previously only the row text went
  through `ui_font()`, so at UI scale > 1.0 the menu width lagged the
  text and the fixed 32px row height clipped the scaled labels; the
  section-title `sizeHint` also re-pinned its font to unscaled 11px,
  under-sizing the whole menu). The row content layer also paints with
  `rebase_family()` instead of `paint_font()` — the row font is already
  scale-resolved (set by the menu's `_relayout_widths`), and `paint_font()`
  would multiply the UiScale factor a second time, painting labels
  ~factor² large and pushing them out of the row (the same
  size-preserving pattern `SimpleOptionsFlyout` rows use).
- Help-document fallback alt text (missing/malformed image) is now painted
  with `setFont(ui_font(...))` — plain `drawText` used the raw painter
  (design-sized) font, so placeholder labels stayed small at UI scale > 1.0.
- New static scan test (`tests/test_text_paint_scan.py`): every function in
  the toolkit that calls `drawText` must either call `setFont()` itself,
  reference a scale-resolving helper (`ui_font`/`paint_font`/`rebase_family`/
  `rebase_font`/`apply_ui_font`), or carry a documented allowance for
  painting an already scale-resolved inherited font. It also rejects
  `paint_font()`/`rebase_font()` inside text paint functions without an
  explicit allowance (those multiply the factor, so they are only safe on
  design-sized widget fonts). Allowlists are cross-checked against the live
  source so they cannot rot. Catches both the unscaled-text and the
  double-scaled-text failure classes in any widget, present or future.

- Fade show/hide on `BaseFlyout` now hides the live container for the
  duration of the fade. `paintEvent` composites the pre-rendered `grab()`
  snapshot at the animated opacity, but Qt kept painting the container (all
  content widgets) on top at *full* opacity — the panel and shadow faded
  while the content popped in binarily. The container's own hidden-mark
  (not `isVisible()`, which is parent-dependent and would skip the sync on
  the very first show) is driven by `_fade_opacity`, and `_capture_fade_cache`
  un-hides it before `grab()` so a re-show after a fade-out snapshots the
  content too.

- `toggle_submenu` re-runs `_relayout_widths()` on the freshly created
  submenu just before showing it (same as `popup_at`/`show_aligned` do for
  the top menu). In some hosts the constructor's `set_entries` ->
  `_relayout_widths` pass left the new rows on the inherited design-sized
  window font — live in Improve-ImgSLI: the tab-strip context menu's "New
  Tab" submenu rendered at the unscaled 12pt while the parent menu rows
  were at 24pt. The second pass reliably pins the scale-resolved UI font
  on every row before the first paint.

- Context-menu submenu indicator is now a painted chevron polygon instead
  of the "›" text glyph: the single-arrow character is extremely narrow
  (≈4px wide at 12pt — half the width of ">"), so it read as a tiny dot at
  any UI scale and looked like it never scaled. The polygon is derived from
  `scaled_px()` and stays visually comparable to the row text.

- The help-document layout engine moved into `text_view/` as the single
  home: `blocks.py` → `text_view/markdown.py`, plus `text_index.py`,
  `structure.py` and `layout/` (builder, text_layout, paint, hit_test,
  coords, segment_map, types, constants) relocated; `help_document/` keeps
  its chrome (`canvas.py`, `view.py`, `image_lightbox.py`) and re-exports
  the same public API unchanged.
- The UI inspector's Code section now uses the public `TextView` (the
  private `_CodeView`/`_CodeCanvas` and `inspector/python_highlight.py`
  are gone).
- `TopTabBar`/`TopTabHost` gained close buttons (`close_policy` /
  `CloseButtonPolicy`, default `NONE`): an embedded close button per tab
  (painted X, tab-state slot background, hover forwarded to the bar,
  `tabCloseRequested` signal). The bar's minimum no longer forces the host
  wider than the content (`minimumSizeHint` no longer equals `sizeHint`).
- `HelpImageLightbox.eventFilter` is defensive against teardown events (a
  partially-constructed lightbox no longer raises inside the event loop).

- Grouped button fills: a `group=` whose members are all plain rects now paints
  ONE united fill (first member paints the group rect, siblings paint nothing)
  instead of per-region abutting fills with a hairline overlap. The old
  approach left an antialiased seam at the split boundary (and overlap nudges
  double-tinted it). Ripple is unaffected (it already clipped to the united
  group rect). Groups with any `corner_radii`/`path_fn` member keep the
  per-region fill behavior.
- `BaseFlyout.show_aligned(..., animation="fade")` and
  `"slide-fade"` — fade-in (opacity 0 → 1, with the existing slide for
  `"slide-fade"`). Fade is implemented without a `QGraphicsEffect`: a one-shot
  `grab()` snapshot taken outside `paintEvent` is composited with the
  animation's opacity in `paintEvent` (a graphics effect on the shell would
  conflict with the container's `RoundedClipEffect` and the shell's
  `QPainter(self)` paintEvent on composited windows; `windowOpacity()` does not
  apply to in-window child widgets).
  `hide()` mirrors the show: a flyout shown with `"fade"`/`"slide-fade"`
  fades out on close (new `FlyoutTimingConfig.flyout_fade_out_duration_ms`,
  default 150 ms) instead of vanishing instantly; `"none"`/`"slide"` shows
  still hide instantly, and `reposition()` does not reset the close
  animation. Docs updated in `FLYOUT_SYSTEM.md` / `CONFIGURATION.md`; tests
  in `tests/test_flyout_fade.py`.
- `FlyoutTimingConfig.default_flyout_animation` — process-wide default for
  `show_aligned(..., animation=...)` when the caller omits it (`"none"` unless
  configured). A host sets `configure_toolkit(timings=FlyoutTimingConfig(
  default_flyout_animation="slide-fade"))` to fade every default flyout app-wide
  from one config value; explicit per-call `animation=` always wins.
- `SimpleOptionsFlyout(parent_widget, animation=...)`, `IconActionFlyout(...,
  animation=...)`, `IndexedToggleFlyout(..., animation=...)` — per-instance
  show-animation override for the composite flyouts (takes precedence over the
  process-wide `default_flyout_animation`, which they now also respect).
  `SimpleOptionsFlyout.show_below`/`show_above` resolve the same mode as
  `show_aligned` (fade / slide / slide-fade / none) instead of always sliding,
  so a global `"fade"` default makes those dropdowns fade in place.
- `popup_context_menu_for_anchor(..., animation=None)` and
  `TitleBarMenuStrip`'s File/Help menus now resolve their show animation the
  same way (explicit value → global `default_flyout_animation` → historical
  `"slide"`), so an app-wide `"fade"` also fades title-bar / anchor context
  menus instead of always sliding.
- `ContextMenu.popup_at(global_pos, *, animation=None)` — cursor-positioned
  context menus (canvas right-click, popup surface) now also resolve the
  global animation default: with a fade-bearing mode they fade in at the
  cursor and fade out on hide, and `aboutToHide`/`deleteLater` fire only
  after the fade-out actually hides the menu.
- Consolidated `CustomLineEdit`'s click-outside-clears-focus behavior onto
  one shared `QApplication` event filter instead of one filter per
  `CustomLineEdit` instance (`ui/widgets/helpers/editable_text.py`) —
  same one-filter-many-widgets shape `HoverCoordinator` already uses for
  hover. Pilot fix for item #9 in `docs/dev/API_CONSISTENCY_AUDIT.md`
  (app-level `installEventFilter` calls scattered one-per-concern across
  9 subsystems); the transient ones (`MarqueeBandGesture`, `ComboBox`
  outside-click) were deliberately left alone this pass — higher risk to
  merge, lower payoff, see the doc for why.
- `tests/test_editable_text_outside_click.py` — regression guard for the
  fix above: asserts every `CustomLineEdit` registers into the same
  `_OUTSIDE_CLICK` coordinator singleton, that creating 5 instances calls
  `QApplication.installEventFilter` for the coordinator exactly once (not
  once per widget — the literal bug being fixed), and an end-to-end
  `qtbot` check that click-outside-clears-focus / click-inside-keeps-it
  still behaves correctly through the shared filter.
- `TimelineWidget(..., accent_color=, canvas_bg=, track_bg=, grid_color=,
  text_color=)` + matching `set_*` runtime setters, and
  `CustomTitleBar(..., bg_color=, text_color=)` + `set_background_color`/
  `set_title_color` — both composites previously had zero per-instance
  color-override path (100% `ThemeManager`-token-driven), unlike
  `CalendarWidget`/`BaseFlyout`/`Label`/`Button`, which all follow the same
  constructor-kwarg-plus-setter shape. See item #8 in
  `docs/dev/API_CONSISTENCY_AUDIT.md` for the full before/after and why
  `LogConsoleWidget`/`MinimalistScrollBar`/`ToastManager.spacing`/
  `DragDropOverlay`'s hardcoded `close_on_*` were left alone this pass.
- `docs/dev/API_CONSISTENCY_AUDIT.md` — review of 7 public-API consistency
  issues found while writing the per-widget docs, with a done/proposed/
  no-action status per item. Linked from `docs/dev/README.md` and
  `docs/dev/ROADMAP.md`. Includes a follow-up finding: a stock `mypy` run
  against the newly-`py.typed`-marked package (see below) found 562 errors
  across 66/202 files — mostly internal `ui/` Optional-attribute noise, but
  23 in the public `i18n.py` (`TranslationManager` attribute typing). Those
  562 errors are now fixed (0 remaining across all 201 source files), and
  `mypy` runs in CI on every push/PR (`.github/workflows/ci.yml`) so the
  count can't silently regress. `mypy`, `PySide6-stubs`, and `types-Markdown`
  are new `dev` extras; run `mypy src/sli_ui_toolkit` locally to reproduce
  the CI check. Remaining PySide6-stubs gaps (`shiboken6.isValid`, `QRhi*`
  fields/overloads — the stub package lags current PySide6 releases) are
  suppressed with narrowly-scoped `# type: ignore[<code>]` comments rather
  than broad ignores.
- `sli_ui_toolkit.config.reset_toolkit_config()` — resets every
  `configure_toolkit`-settable value (timings, overlay resolver, rating
  gesture factory, drag-drop service getter, context menu surface, ripple
  duration, click deferral, underline fade) back to library defaults in one
  call. Exported from the top-level `sli_ui_toolkit` package. Intended for
  test isolation, since `configure_toolkit` state is process-wide;
  `tests/conftest.py` now calls it in an autouse fixture around every test
  instead of the previous ad hoc, partial per-file save/restore.
- `tests/test_config_callback_errors.py` — asserts the new `config.py`
  logging (below) actually fires with `exc_info` on each of the three
  failure paths, and stays silent when the host callback succeeds.
- `sli_ui_toolkit.widgets.RatingListItem` / `.EditableListItem` — both
  existed and were used internally but were never added to the public
  `sli_ui_toolkit.widgets` surface or documented (the catalog even had
  `RatingListItem` under the wrong name, `RatingItem`). Old import paths
  (`sli_ui_toolkit.ui.widgets.list_items.*`) still work.
- `docs/user/CONFIGURATION.md` — single reference for every process-wide
  setup hook (icons, theme, i18n, logging, tooltips, `configure_toolkit`
  timings/feedback), with a full startup sequence mirroring `demo/main.py`,
  per-hook defaults, and what happens if a hook is skipped. Linked from
  `README.md`, `docs/README.md`, `docs/user/README.md`, and
  `API_CATALOG.md`'s Configuration Hooks table. Previously this was spread
  thin across a few bullet points with no parameter-level detail.
- `src/sli_ui_toolkit/py.typed` (PEP 561 marker) so type checkers in host
  apps trust the toolkit's inline annotations instead of treating it as
  untyped.
- README badges (PyPI version, CI status, license).
- Nine new per-widget-family doc pages under `docs/user/`, each with real
  constructor signatures (verified against source via
  `inspect.signature`), defaults, and runtime setters — previously most of
  this content was either a bare one-line table row in `API_CATALOG.md` or
  missing entirely: `LABELS_API.md`, `CONTEXT_MENU_API.md` (incl. the
  `ContextMenuAction.defer_trigger` entry below), `INPUTS_API.md`
  (`CheckBox`, `RadioButton`, `Slider`, `SpinBox`, `Switch`,
  `MinimalistScrollBar`, `OverlayScrollArea`, `LoadingSpinner`,
  `CustomGroupWidget`/`Builder`, plus the existing text-input docs moved
  here), `TABS_API.md`, `DIALOGS_API.md` (`SidebarDialogShell`,
  `ScrollableDialogPage`, `IconListWidget`, `MarkdownHelpDialog`,
  `HelpDocumentView`), `FEEDBACK_API.md` (`LogConsoleWidget`,
  `ProcessConsoleWidget`, `ToastManager`), `CHARTS_API.md`
  (`SunburstChartWidget`, `CalendarWidget`, `TimelineWidget`),
  `OVERLAYS_API.md`, and `LIST_ITEMS_API.md` (`RatingListItem`). Also
  documented previously-undocumented `Button` underline params
  (`underline_tongue_reach`, `underline_ring`) in `API_CATALOG.md`.
  `API_CATALOG.md` itself (1016 → ~540 lines) is now an index: one table +
  a link per group, matching the existing `BUTTON_API.md`/
  `FLYOUT_SYSTEM.md` pattern instead of duplicating everything inline.
  Linked from `README.md`, `docs/README.md`, and `docs/user/README.md`.
- `ContextMenuAction.defer_trigger: bool = False` — the context-menu
  equivalent of `Button(defer_click=DEFER_CLICK_AWAIT_RIPPLE)`. A row click
  normally hides the whole menu and invokes `on_triggered` synchronously,
  which for a row whose action opens a modal (`.exec()`) dialog means the
  row (and its own click ripple) is destroyed by the menu closing before
  the ripple gets to play at all -- worse than the plain-Button case, since
  there the button itself at least stays on screen. `defer_trigger=True`
  waits one ripple duration (`get_ripple_duration_ms()`) with the menu
  still open before hiding + firing. Found via ImgSLI's Help menu "Find
  Action…" row, which opens a modal command-palette dialog.

- `show_aligned(..., offset=N)`: any `N < SHADOW_RADIUS` (default 8) was
  already silently floored to `SHADOW_RADIUS` (needed so the drop-shadow
  halo never visually overlaps the anchor) -- but with zero signal that it
  happened, so e.g. `offset=2` and `offset=4` render pixel-identical (both
  floored to 8) and tuning within that range looks like the parameter does
  nothing. `_compute_aligned_top_left` now logs at DEBUG
  (`sli_ui_toolkit.ui.widgets.composite.base_flyout`) whenever the floor
  actually changes the requested value, naming the flooring
  `shadow_radius` and the `anchor_point`/`flyout_point` involved. No
  behavior change -- pass `offset >= SHADOW_RADIUS` for the exact pixel gap
  requested, same as before, just diagnosable now instead of a silent
  no-op. Found via ImgSLI's `ModePicker`/color-options flyouts, where
  offset went 2 -> 4 -> 10 with no visible difference between the first two.

- `FlyoutManager._close_flyouts_with_moved_anchors` now calls
  `flyout.reposition()` itself for `pinned=True` flyouts whose anchor moved
  or resized, instead of only skipping the auto-close (leaving repositioning
  entirely up to the host's own resize/move handler, per `reposition()`'s
  docstring). Hosts that already call `reposition()` themselves
  (`InfoHUD`/`ZoomIndicator`) just get a harmless extra no-op call. Found
  via ImgSLI's `MagnifierSettingsFlyout` (app-side code, not this library)
  — freshly switched to `pinned=True` to opt out of `_dismiss_passive()`
  closing it on any outside click, but with no resize-handler wiring of its
  own, so without this it would sit at a stale position instead of tracking
  its anchor during a window resize while open. Gated on the same
  snapshot-rect comparison the existing non-pinned auto-close branch already
  uses (and refreshes the snapshot after repositioning) -- the triggering
  event filter is installed app-wide, so an ungated call would re-run a
  pinned flyout's full positioning logic on *every* Move/Resize/etc.
  anywhere in the app, not just when its own anchor actually moved. Hosts
  with positioning beyond a plain `show_aligned()` call (e.g. an extra
  `move()` afterwards) should override `reposition()` to redo that too --
  see `MagnifierSettingsFlyout.reposition()` for the pattern.

- `IconListWidget` rows are now built entirely on the public `Button` API
  (`variant="sidebar_nav"`) instead of the bespoke `_NavRowButton`/
  `_NavRowContent` painter pair. Icon/text layout, ripple, and checked-state
  painting come from `Button`'s own content/variant pipeline instead of
  being hand-drawn; no behavior change for existing `set_items`/`add_item`
  callers. This also unlocked `button_factory` (see "Added") since rows are
  now ordinary `Button` instances the widget composes rather than a private
  subclass it paints itself.
- `IconListWidget` checked-row background now reads
  `list_item.background.selected` from the theme palette first, falling
  back to `accent` and then `list_item.background.hover` (the previous
  behavior, unchanged for palettes that don't define the new key). Lets a
  host palette give the checked row a background other than a solid accent
  fill — e.g. so an accent-tinted icon (see below) stays legible against it —
  without any widget-level change.
- `IconListWidget` checked-row icon color now reads `list_item.icon.selected`
  from the theme palette first, falling back to `HighlightedText` (white) as
  before. The checked icon's pixmap is now actually tinted to that resolved
  color via `QPainter` (`CompositionMode_SourceIn`) rather than being
  RGB-inverted — the previous default `selected_icon_mode="invert"` flipped
  each icon's own channel values, which is only coincidentally close to
  "white" for near-black monochrome glyphs and produces arbitrary,
  unthemed hues for anything else. The per-pixel Python loop this replaced
  is also gone; tinting is now one composited fill.
- `Button` underline (`show_underline`/`setUnderlineColor`/`setUnderlineThickness`):
  rewrote the paint geometry to build the band from rounded-rect `QPainterPath`
  boolean ops (`intersected`/`subtracted`) instead of stroking a fixed-size arc
  with a `QPainterPathStroker`. The old approach centered a `thickness`-wide pen
  on a tiny, fixed-radius arc at each corner, so once `thickness` exceeded that
  radius the stroke visibly overflowed past the button's own rounded corners as
  square blobs. The new geometry is bounded by the widget's own rounded rect by
  construction, so it cannot overflow at any thickness.
- `setUnderlineThickness`/`Button(underline_thickness=...)`: removed the
  previous hard cap of 3.0px (and the `RuntimeWarning` it raised past that).
  Uncapped now that the geometry rewrite makes arbitrarily large values safe.
- Underline tip alpha-fade: back to only the strip's true left/right ends
  (a small fixed-px patch, skipped once `thickness >= tongue_reach`). An
  intermediate experiment fading every zone across its own full length
  (interior color seams included) read worse in practice — messy rather than
  like a taper — and was reverted.

- Large widget families were decomposed into folders, one concern per
  module (the `buttons/` folder is the model; all old module paths stay as
  thin re-export shims, the public API is unchanged):
  - `base_flyout.py` → `ui/widgets/composite/base_flyout/`: `widget.py`
    (thin facade), pure placement math in `geometry.py`, fade machinery in
    `animation.py`, style/builder/placement/lifecycle/manager-contract
    modules.
  - `ui/windows/custom_title_bar.py` → `ui/windows/custom_title_bar/`:
    zones/balance in `zones.py`, `window_controls.py`, `drag.py`,
    `appearance.py`, thin `widget.py`.
  - `ui/inspector/view.py` → section rendering in `rendering.py`, the Code
    section in `code.py`, Layout/Constructor trees in `tree.py`, value
    formatting in `fields.py`, plus a thin `view.py` (`InspectorWindow` +
    `_InspectionPane`).
  - `ui/widgets/composite/adaptive_tab_strip/widget.py` → `widget.py`
    (thin host), `tab_bar.py` (the painted bar), `close_button.py` (close
    slot + policy + tab-background layer).
  - `ui/widgets/composite/list_panel.py` → `ui/widgets/composite/list_panel/`:
    `widget.py` (facade), `rows.py`, `drag_drop.py`, `selection.py`.
  - `ui/widgets/composite/sidebar_nav_list.py` →
    `ui/widgets/composite/sidebar_nav_list/`: `widget.py` (facade),
    `rows.py`, `icons.py`, `debug.py`.
  - `ui/widgets/composite/toast.py` → `ui/widgets/composite/toast/`:
    `progress_bar.py`, `notification.py`, `manager.py`.
  - `ui/widgets/composite/text_view/canvas.py` → the document-mode
    interaction moved to `document_mode.py`.
- The mixin splits were further decoupled into state-owning objects and
  pure functions with explicit inputs (no shared instance namespace):
  - `list_panel`: `MarqueeSelectionModel` owns the selection set and
    band-preview semantics; `drop_target_index()` / `should_hide_indicator()`
    are pure geometry/decision functions; item/position transforms are pure
    in `rows.py`. All testable without a widget.
  - `sidebar_nav_list`: icon resolution (pixmap pairs, invert/replace
    tinting, selected color) is pure in `icons.py`; the layout debug dump is
    module functions taking the widget explicitly.
  - `text_view`: `DocumentSelection` owns the document-mode selection/press/
    drag state (widget-free); the canvas only delegates and repaints.
  - `base_flyout`: `FlyoutFadeController` owns ALL fade state (snapshot
    cache, opacity, hide-fade animation, flags); the widget only references
    it and passes itself explicitly where the controller must touch it
    (grab/update/hide children). Subclasses' show paths
    (ContextMenu/SimpleOptionsFlyout) use the same controller API.
  - `custom_title_bar`: the min/max/close buttons are now a real
    self-contained child widget `WindowControlsCluster` — it owns its
    buttons, deterministic-slot geometry, scaling and window-state icon
    refresh; the bar wires signals and keeps the corner mask + flyout sweep.
  - `inspector`: the Code section is a self-contained `CodeSectionEditor`
    widget (source view, config view, Edit/Revert/Save, dirty tracking);
    the pane keeps thin compatibility properties for the old private
    attribute names.

### Fixed

- **`setup_logging()` re-entry no longer silences the host app's debug stream** — the app and toolkit loggers share handler instances, and the re-entry branch unconditionally set the shared handlers to the toolkit-only level (`INFO` without `SLI_TOOLKIT_DEBUG`). Hosts that configure logging twice at startup (Improve-ImgSLI re-applies it after loading persistent settings) lost every `DEBUG` line after the second call even though the app logger itself stayed on `DEBUG`. Shared handlers now keep `min(app, toolkit)` level; per-logger gating is unchanged, so the toolkit stream stays quiet by default.
- **`SimpleOptionsFlyout.hide` no longer kicks an already-active window** — focus restore now skips `activateWindow()` when `win.isActiveWindow()` (keeps `setFocus()`), so closing a flyout over the active host no longer costs a Wayland busy-cursor frame. Satisfies the host `test_no_unconditional_activation` contract.
- **`NavigationManager` focus-ring on new tab** — `ToolbarRowsSection`/`IconListNavSection` `focus_first` and bootstrap now respect mouse vs keyboard modality via `current_focus_reason()` (`MouseFocusReason` vs `OtherFocusReason`). Opening a tab with a mouse click (session picker) no longer lights up the ring; keyboard opens still do. Previously `OtherFocusReason` was unconditional.
- **`AdaptiveTabStrip`/`_AdaptiveTabBar` tab switching requires Enter** — `Left`/`Right`/`Home`/`End` now move a separate keyboard-focused index (`_focused_index`) with modality preserved, `Enter`/`Space` activates (`setCurrentIndex`). `Delete`/`Backspace` closes the focused tab. Focus ring follows `_focusedTab()` when `hasFocus() && _keyboard_focus`. Mouse clicks still switch immediately.


- **`HelpDialog` focus consistency** — `IconListWidget` `OverlayScrollArea` was `StrongFocus` and was picked as navigable candidate by `AutoNavigationSection`, causing `Right` from left list to land on the scroll area instead of content hub cards; now `NoFocus` (incl. viewport). `HelpDialog._restore_focus_after_window_change` now preserves exact left sub-target (`search` vs `current_row_button`) via `NavigationManager.focus_section_for_owner` + direct `current_row_button` fallback, instead of always jumping to `QLineEdit`. `HelpDialog` Left from content now lands on selected row, not search.
- **`HelpDocumentView` TOC keyboard navigation** — `_LinkLabel` (TOC entries) were `NoFocus` (`Label` default) so `help-content` `AutoNavigationSection` had zero `StrongFocus` candidates on document pages, `Right` from sidebar was consumed but moved nowhere (later seen as `OverlayScrollArea` focus). Now `StrongFocus` + `focusIn/Out` ring + `Enter/Space` activation + `paintEvent` focus rectangle, so document TOC is navigable via `Up/Down`/`Left`/`Right`.
- **`HelpDialog` focus loss on close** — `hideEvent`/`closeEvent` left `QApplication.focusWidget() → None` after `HelpDialogWindow` lost focus (`23:42:16:980`), because external focus (`CsdMenuRow`/`MainWindow`) was cleared by `SimpleOptionsFlyout` hide before Help opened and never saved. Now `showEvent` saves `_external_prev_focus`/`_external_prev_window` (incl. `NavigationManager.last_keyboard_focus` fallback) and `hideEvent` restores it with `OtherFocusReason` + `activateWindow`, so closing Help never leaves `None`.
- **`AutoNavigationSection` crash on stale Help sidebar** — `HelpDialog._sync_sidebar` `clear()` deletes old `Button`s but `Auto._cached_rows_widgets` kept deleted `C++` pointers; `Key_Down` from `HelpSearchField` on next row did `min(target_row, key=lambda w: w.mapToGlobal(...))` on deleted `Button` → `RuntimeError: Internal C++ object (Button) already deleted` (`navigation_sections.py:589`, лог `23:49:46:925`). Now `_auto_rows` filters `shiboken6.isValid`/`isVisible`/`isEnabled`, `navigate`/`focus_first`/`focus_last` re-scan and filter target rows, `mapToGlobal` wrapped in `try/except`, so stale cache self-heals without crash.


- **`IconActionFlyout` crash on deleted layout** — `update_state()` called
  `h_layout.invalidate()` on a freed `QHBoxLayout` when a host
  `store.state_changed` observer (e.g.
  `magnifier_color_controls.py:251` `_on_store_state_changed`) was still
  connected at app shutdown (Python wrapper kept alive by the bound-method
  signal connection). Now `update_state` guards `self`, `h_layout` and
  `container` with `sip.isValid` + `try/except RuntimeError` before any
  layout touch; `set_actions` and `_on_scale_changed` also guard layout
  validity (same class as the 4.1.0 `AutoNavigationSection` / 4.2.1
  stale-button fixes, but for the layout object).
- **`IconActionFlyout` crash on stale action buttons** — a host signal
  connection (e.g. a store `state_changed` observer) can keep the flyout's
  Python wrapper alive past its buttons' C++ deletion (parent teardown or
  `set_actions` `deleteLater` processed by the event loop). `set_action_state`
  then hit `button.setVisible(...)` on a freed `Button` →
  `RuntimeError: Internal C++ object (Button) already deleted`
  (`magnifier_color_controls.py` `_on_store_state_changed` → `update_state`).
  Now `set_action_state`, `_on_scale_changed` and the `set_actions` cleanup
  loop guard every cached button with `sip.isValid` and self-heal the
  action dicts via `_purge_action` (same pattern as the 4.1.0
  `AutoNavigationSection` stale-row fix).


- **`DragDropOverlay` dark text in all themes** — `HighlightedText` alias resolves to `surface.background` (white in light, dark gray in dark) so text/border were dark on semi-transparent blue in both themes and did not react to theme toggle. Now text/border are forced to white (`#ffffff`) with luminance check fallback, `ThemeManager.theme_changed` triggers `update()`, so overlay is readable and theme-reactive in light and dark.
- **`DragDropOverlay` not disappearing after drop until image loads** — `WindowEventHandler.handle_drop` hid the overlay via deferred `singleShot(0)` which raced with the also-deferred `load_images_from_paths`; overlay stayed visible until decode finished. Now hides synchronously via direct `_safe_update_drag_overlays(False)`.

- **`OverlayScrollArea` no longer holds a dead gutter when content fits** — `reserve_scrollbar_space=True` now adds the viewport right margin only while the native scrollbar range is non-empty (`maximum > minimum`). Lists with fewer rows than the visible limit (e.g. `ListPanel` capsules below `MAX_VISIBLE_ITEMS`) get the full viewport width; the gutter appears only once content actually overflows. Safe against oscillation: the vertical range depends on height only, so a width change cannot flip it back.
- **`VirtualListController` symmetric content height** — `_content_height` / `_max_scroll` now mirror the top `y_margin` below the last widget (which contributes its widget height, not a full pitch), so the last row no longer hugs the content's bottom edge. Identical numbers for the default (`y_margin=0`, no separate widget height). `ListPanel` sizing matches: panel heights are content + own chrome, the scroll area gets the chrome subtracted, so the viewport lands exactly on the content with no stretch band.
- **`ListPanel` rowsyncs widget height on rebuild** — new `VirtualListController.set_widget_height` (plus `ListPanel._sync_row_metrics` calling it alongside pitch/margins on rebuild, sync, and scale change). Previously only the pitch was updated, so rows repopulated at a new anchor height kept the construction height: the content overflowed by the delta and a scrollbar appeared over a one-row list.
- **`VirtualListController` no longer double-applies the scroll offset** — rows are positioned at absolute content coordinates; Qt already moves the content widget by the native scrollbar value, so subtracting the offset again scrolled every list at 2x and parked ~2 pitches of dead space under the last row at max scroll (9-row dump: last visible bottom 167 of 237). `index_at` hit-testing adjusted to the same absolute coordinates; `ensure_visible` now measures the true widget bottom (+ bottom inset on the last row). `RowPool.scroll_offset` stays for non-Qt-scrolled hosts (ComboBox overlay).
- **`Button.setHoverActive(True)` actually activates hover** — the method only implemented the `False` branch, so `HoverCoordinator`-driven activation (widget slid under a stationary cursor, flyout opened under it, drags) silently never lit: e.g. `+`/`-` buttons in virtualized lists showed no hover overlay. The `True` branch derives the position from the live cursor and lights the exact region (idempotent, no repaint storm); direct `Enter` behavior unchanged.
- **`ToastNotification.hide_and_close` now destroys** — previously `hide()` + `close()` on a parented widget only hid it, so the manager's `destroyed→pop` registry exit never fired and closed toasts (plus their `theme_changed` connections) leaked. The toast now sets `WA_DeleteOnClose` and `hide_and_close` does `hide()` + `deleteLater()` (idempotent via `_closing`); `close_toast` no longer pops directly so `destroyed→pop` is the single registry exit, and `update_toast` after close is a no-op instead of resurrecting the toast via `show()`.
- **Toast anchor guards narrowed** — `set_anchor`, `_toast_max_width`, `_position_toasts`, `eventFilter` and the `ToastManager` constructor now use null/`shiboken6.isValid` guards instead of broad `except pass`, so a dead anchor can no longer silently misposition the stack.
- **Focus-ring modality unified on input device, not `FocusReason`** — `NavigationManager.resolve()` / `is_keyboard_focus()` / `resolve_keyboard_focus()` is now the single resolver: the source of truth is the input device (`MouseButtonPress` → `False`, `KeyPress` → `True`), `Qt.FocusReason` is only a documented hint. All `focusInEvent` (`Button`, `Slider`, `_AdaptiveTabBar`, `BaseFlyout`, `HelpDocumentView`), `AutoPreview` `FocusIn` and anchor readers migrated; the `ActiveWindow` special case and `ring-preserve` safeguard in `Button` are subsumed by the flag semantics. Qt-generated `Tab`/`ActiveWindow`/`Other` (focus-proxy steals, fade re-shows, window activation) on a mouse history no longer lights the ring; programmatic `Mouse`-steal during keyboard navigation still preserves it. Covered by `tests/test_focus_ring_resolver.py` (reason×input matrix + AST guard against reason-tuple drift).

- `API_CATALOG.md`: removed the `OutputPathSection` row — the class was
  deliberately removed (see the "Removed" entry below in this same file)
  but the catalog row and Reuse Guidance mention were never cleaned up,
  so the doc pointed at a non-importable name.
- `API_CATALOG.md`: `RatingItem` renamed to `RatingListItem` (the actual
  class name in source) and `SunburstSegmentData`'s documented fields
  corrected from `span_angle`/`segment_id` to the real `end_angle`/
  `node_id` — both were stale from earlier renames.
- `AGENTS.md`: dropped the rule about keeping `src/sli_ui_toolkit.egg-info/`
  in sync — it's a `.gitignore`d local build artifact, never committed, so
  the instruction referred to files that don't exist in the repo.
- `config.py`'s `resolve_overlay_layer` / `create_rating_gesture` /
  `get_dragdrop_service` now log a `WARNING` with the original traceback
  before falling back on a host-callback exception, instead of swallowing
  it with a bare `except Exception: return None`. A broken
  `overlay_resolver`/`rating_gesture_factory`/`dragdrop_service_getter`
  used to degrade silently to "no overlay"/etc. with nothing in the logs
  explaining why.
- `attach_in_window_widget` no longer re-parents a flyout into an overlay
  host that lives in a *different top-level window* than its anchor.
  Host overlay resolvers typically walk up the QObject chain, so a flyout
  anchored inside a dialog whose QObject parent is the main window used to
  be re-parented to the main window's overlay layer — and Qt paints that
  child *under* the dialog, making the flyout invisible (only the part
  sticking out past the dialog edge showed up, looking like a stray popup
  in the host window's corner). In-window flyouts now keep the same
  invariant the combo dropdown always had: a plain child of the anchor's
  own window. Found via ImgSLI's slider value hint in the Settings dialog.
- Fenced code blocks in document mode (`TextView.set_markdown` / help
  pages / UI-inspector text views) now paint their rounded background box
  exactly once per block instead of once per line fragment. Every line of a
  block shares the same `code_box`, and the `help.code.background` token is
  semi-transparent — the repeated strokes accumulated alpha, so a block's
  shade depended on how many lines it had (1-line blocks nearly
  indistinguishable from the page background, long blocks dark).
- Text selection is now ONE shared system (`text_view/selection.py`:
  `SelectionState` core + `TextSelection`/`DocumentSelection` bindings)
  used by code mode, document mode AND the help-document canvas — the
  multi-click chain, drag threshold and extend logic were triplicated
  with divergent behavior. Document mode gained the same multi-click
  selection as code mode (double-click word, triple-click paragraph/
  segment, drag extends word-/segment-wise), so the UI inspector's Docs
  and Code sections select text identically; the help canvas's 4th-rapid-
  click now starts a fresh chain like everywhere else. Triple-click inside
  a fenced code block now selects the current line (like the code editor)
  instead of the whole fence — a code block is one text-index segment, and
  `segment_bounds_at_offset` resolves multi-line segments to the line at
  the offset.
- Code-mode multi-click chain: the same-spot test now runs in widget
  PIXELS (Qt's double-click distance), not in `(line, col)` space — a
  click on line 2 followed by a click on line 1 used to count as a
  double-click and select a word instead of moving the caret.
- The text caret is hidden while a selection is active (it used to ride
  inside the selected range during a drag and blink on top of the
  highlight); it reappears when the selection is cleared.
- Line-mode selection dragged UP no longer drops the top line: the
  normalized interval put the focus line at its END, so the top boundary
  painted empty and the selection was one line short of the drag
  position. Both boundary lines are now kept whole (keyboard Shift+
  arrow column edges are untouched).
- `TextView` no longer expands to a fixed content-derived size: the canvas
  pins its content height as a MINIMUM and `widgetResizable(True)` makes
  the scroll area stretch it to the viewport (the view flexes with the
  window; long content scrolls internally). The document layout now always
  recomputes at the real canvas width — a pane rendered while the window
  is hidden (e.g. the inspector's first Docs section) could previously
  stay laid out at a stale 1px width, producing an absurdly tall column
  instead of wrapped text. The inspector's Code section keeps filling the
  page (the editor now stretches in its page layout instead of relying on
  the canvas's old fixed-height sizeHint; the height clamp is unchanged),
  so both the Code and Docs areas follow the window and scroll internally.
- `ui/inspector/code/__init__.py` is now a thin package init: the
  `CodeSectionEditor` implementation moved to `code/editor.py` (the
  package previously carried ~830 lines of implementation in its
  `__init__.py`; the public imports `CodeSectionEditor` /
  `build_code_section` are unchanged).

- `_compute_aligned_top_left` (`BaseFlyout.show_aligned`'s placement math)
  used an `if`/`elif` chain across the vertical and horizontal clearance
  push, so a true corner-to-corner anchor (`anchor_point` and
  `flyout_point` differing on *both* axes, e.g. `"top-left"` /
  `"bottom-right"`) only ever got the offset gap on whichever axis the
  chain reached first (vertical, always, since that check came first) —
  the other axis stayed flush against the anchor with zero gap. Now two
  independent `if` blocks, so both axes get `offset` clearance on a
  diagonal anchor. Non-corner callers (anchor/flyout sharing an axis, e.g.
  `"bottom-center"` / `"top-center"`) are unaffected — the block for the
  shared axis never had a differing condition to fire. Found via ImgSLI's
  `FontSettingsFlyout.show_top_left_of` (`"top-left"`/`"bottom-right"`)
  sitting flush against its anchor button horizontally; also fixes the
  same flush edge on multi-compare's `"bottom-right"`/`"top-left"` variant
  of the same flyout.
- `BaseFlyout.hide()` unconditionally called `window.activateWindow()` /
  `.setFocus()` whenever the host window wasn't the active window at close
  time (see `restore_focus_on_hide()`). For a purely hover-driven flyout
  (opens/closes just from the cursor passing over its trigger, no click),
  this fired even while the host app was in the background with OS focus
  elsewhere, and `activateWindow()` on an inactive window reads to the WM
  as an activation request — surfacing as an unsolicited taskbar flash /
  "app wants attention" hint, not an actual focus steal. `show()` now
  records whether the window was already active at open time
  (`_window_active_on_show`); `hide()` only restores focus if it was —
  i.e. only when the window genuinely lost activation during the flyout's
  own lifetime (e.g. to a nested dialog), never when it was inactive to
  begin with. Found via ImgSLI's slider-hint and magnifier-settings hover
  flyouts triggering attention requests while the app sat in the
  background.
- `AnchoredFlyoutAutoHide._on_timeout` only ever treated two spots as "still
  interacting, don't hide" — the flyout's own body and its anchor widget's
  rect. A flyout hosting a combo box whose own dropdown opens well outside
  both (e.g. a wide list popping up below a combo that lives inside the
  flyout's content) would auto-hide the parent right out from under an
  in-progress pick the moment the cursor reached that dropdown, or shortly
  after closing it (cursor left in empty space, nowhere near either safe
  zone). Now also checks `FlyoutManager.linked_children(flyout)` — any
  flyout `.link()`-ed as this one's child counts as inside too while it's
  visible. Found via ImgSLI's magnifier-settings hover flyout hosting an
  interpolation-method dropdown.
- `UiFont.apply(widget, **overrides)` (what `apply_ui_font()` calls) now
  keeps `widget` in sync with any *future* real application font change
  (`font_changed`) using the same `overrides`, instead of only resolving
  the font once at the call site. `resolve()` reads
  `QApplication.font()` at the exact moment it runs, and
  `QWidget.setFont()` marks `WA_SetFont`, so Qt never retroactively
  re-cascades a later `ApplicationFontChange` onto that widget on its
  own — a plain widget (e.g. a bare `QLabel`) constructed before a host
  finishes its own startup font correction could bake in whatever
  transient fallback font was active at that moment and never recover.
  `Label` already covered itself the same way internally (its own
  `font_changed`-connected `_apply_style`); this generalizes the same
  protection to every other `apply()` caller, so callers don't each need
  their own `font_changed` plumbing. Disconnects itself via
  `widget.destroyed` rather than leaving a dangling connection to a
  freed C++ object. Found via a real host bug: a `QLabel` baked in a
  10pt fallback face at construction while the app's real UI font (12pt)
  was already/about to be set moments later in the same startup
  sequence, and nothing ever re-synced it afterward except an unrelated
  full-widget-tree unpolish+polish pass happening to run for a different
  reason.
- Flyout layer/rule system self-review turned up four gaps between what
  the four phases above claimed and what they actually guaranteed; all
  four are now closed (see "Gaps found and fixed" in
  `docs/dev/FLYOUT_LAYER_SYSTEM_PLAN.md` for detail):
  - `ensure_overlay_stacking` stacked same-layer flyouts in whatever order
    the internal `set` happened to iterate, not open order as documented —
    now uses a `_registration_order` counter as a deterministic tie-break.
  - `GroupShowPolicy.coexists_with` ignored `parent` inheritance — a group
    declared via `define_group(child, parent=X)` didn't inherit `X`'s
    coexistence exceptions even though it inherited `X`'s other rules; now
    resolved through the same parent chain.
  - The "click inside a linked child doesn't dismiss the parent" guarantee
    from phase 3 had no regression test; added one.
  - `ChainShowPolicy`'s AND-combine/priority-order contract had only been
    exercised with two synthetic policies; added a 3-policy composition
    test shaped like a realistic host stack.
- `CustomTitleBar._hide_active_flyouts` (the Resize/Move sweep that keeps
  CSD File/Help menus from looking like a no-op when opening them resizes
  the host) special-cased `flyout_group == "context_menu"` but hid every
  *other* visible flyout unconditionally, ignoring `pinned=True` entirely —
  unlike every other auto-dismiss path in `FlyoutManager`
  (`_close_flyouts_with_moved_anchors`, `_dismiss_passive`), which already
  exempt pinned flyouts. A host whose window resizes when an unrelated
  panel opens (or when a context menu attaches/detaches from the overlay
  layer) would see its pinned HUDs vanish. Now skips `pinned` flyouts too.
- `IconListWidget.refresh_icons()` rebuilt row icon pixmaps on theme change
  but never reapplied the checked row's foreground tint (`_update_row_fg`) —
  so after a theme switch, a checked row's icon/text color only picked up
  the new theme once you re-selected some row, not immediately. Now called
  alongside the pixmap refresh.
- `CustomLineEdit` underline sat ~0.75px above the widget's bottom edge,
  leaving a visible gap that `Button`'s underline doesn't have. Both share
  the same `draw_bottom_underline` painter, but the underline geometry
  rewrite (see "Changed" below) switched from a stroke *centered* on
  `rect.bottom() - vertical_offset` to a band drawn entirely *above* that
  line — so the old default `vertical_offset=0.75` went from "half the
  stroke still reaches the edge" to "the whole band stops short of it".
  `Button`'s underline layer already always passed `vertical_offset=0.0`;
  `CustomLineEdit` never set it and inherited the now-visible default.
  Fixed by passing `vertical_offset=0.0` in `CustomLineEdit`'s two
  `UnderlineConfig` calls (focused/unfocused), matching `Button`.
- `BaseFlyout.show_aligned(offset=...)`: the visible gap between anchor and
  flyout was always `offset + SHADOW_RADIUS` px, not `offset` px as
  documented — `_compute_aligned_top_left` added the shadow-halo clearance
  *on top of* the caller's offset instead of only enforcing it as a floor.
  With `SHADOW_RADIUS=8` and typical call sites passing `offset=5..10`, the
  real gap ended up roughly double what was requested. Now
  `clearance = max(offset, shadow_radius)`, so `offset` is honored exactly
  once it's already enough to clear the halo on its own, and only falls back
  to `shadow_radius` when `offset` is smaller than that.
- `Button` underline tip fade: no longer uses
  `CompositionMode_DestinationIn` to fade the tip to transparent. That mode
  reduces the *destination surface's own alpha*, not just the blended color —
  on an opaque top-level window this can genuinely punch translucent holes
  into the window's backing store rather than just visually blending the
  underline color into its (already-opaque) background. Normally masked by
  whatever repaints over it next, but visible as the desktop/window-behind
  bleeding through at the underline's tip once a repaint happens outside the
  usual path (most reliably reproduced by defocusing the window). Replaced
  with two plain `SourceOver` fills (solid region + a same-color
  transparent-to-opaque gradient over just the tip), which never touches the
  destination's existing alpha.

- `IconListWidget` content shifted sideways when the vertical scrollbar
  appeared/disappeared (the `ScrollBarAsNeeded` platform bar shrank the
  viewport, reflowing the rows). The nav list now uses `OverlayScrollArea`
  with `reserve_scrollbar_space=False`: a floating minimal scrollbar that
  takes no layout space, so the content width never changes. The bar paints
  nothing when there is nothing to scroll.
  `enable_minimal_scrollbar()` is now a no-op (kept for API compatibility —
  the floating bar is always in use).
- CSD windows could show a rectangular corner inside the rounded
  silhouette: the window's transparent corner zone stayed transparent only
  while no opaque child painted its square corners over it, and that
  contract was implicit (the UI inspector's `TopTabPane` left square
  bottom corners in the rounded window). `sync_csd_chrome` now enforces it
  systematically — `_mask_edge_hosts` masks every direct child that reaches
  a rounded corner zone (bottom → `apply_bottom_rounded_mask`, top →
  `apply_top_rounded_mask`, both → `apply_rounded_window_mask`; the title
  bar and the background layer are skipped because they paint the AA
  silhouette themselves). Hosts no longer need per-window masking code.
- UI inspector: section pages (and their scroll areas/content) could stay
  at their creation size (640×480) while the window grew or shrank —
  `_InspectionPane` now forces the current page to the stack's size on
  every stack resize, so the content always follows the window.
- UI inspector: REF rows could wedge the section content wider than the
  scroll viewport — the button text was the raw `str(widget)`
  (`"<PySide6.QtWidgets.X object at 0x...>"`, ~560 px). REF buttons now
  show `ClassName#objectName`, are bounded with elide (full repr in the
  tooltip), and value/title labels elide.
- UI inspector: the source/docs path buttons did not resize with the
  window; they now use the `text_fit` Button mode (below) and show the
  full path with a marquee when it overflows.

- **Inspector Code section showed the whole ancestor class for bare
  `QWidget` containers** — selecting an anonymous `QWidget` (e.g.
  `ScrollableDialogPage.content_widget`) loaded the entire app ancestor
  class (the whole `SettingsDialog`) into the Code editor. The fallback now
  locates the widget's own creation site — the enclosing function whose
  line references the widget by objectName or by an instance attribute on
  its parent chain (searched in the ancestor's file and the files its
  module imports) — and shows only that region, with the rest of the file
  collapsed into the usual gap rows. Apply stays disabled for such
  function-only regions (there is no class to hot-patch); Save still
  rewrites the file.
- **`ScrollableDialogPage` scroll surface painted the raw QPalette Window
  role instead of the dialog surface token** — the viewport and content
  widget are stock `QWidget`s; with a host QSS active they auto-fill the
  `Window` role, which hosts keep darker than `dialog.background` (the
  app's dark palette: `Window` `#1e1e1e` vs `dialog.background` `#2b2b2b`),
  so the empty page area rendered near-black against the gray panels. The
  page now sets the surface as a widget-level `background-color` stylesheet
  on the scroll area, resolved from the `dialog.background` token and
  re-tinted on `theme_changed`. (A per-widget palette is not enough:
  `QStyle::polish` at `show()` — and on any host stylesheet re-apply —
  resets widget palettes to the app palette; a widget stylesheet survives.)
- **Inspector Colors section added** — the pane's new **Colors** page shows
  the selected widget's background / text / border colors and WHERE each
  comes from: matched QSS rules (selector + value, with a button opening
  the QSS file at the rule's line), the effective palette role +
  `autoFillBackground` (with the first painting ancestor for transparent
  containers), the ThemeManager tokens behind the values (reverse lookup,
  app-defined tokens first, each with a button opening `themes.json` at the
  token's line), custom `paintEvent` detection, and paint-relevant widget
  flags.

- **`HelpDocumentView` painted on the near-black QPalette Window role** —
  the view is a transparent custom widget inside host scroll areas; stock
  `QScrollArea`/viewport auto-fill the `Window` role, which hosts keep
  darker than the dialog surface token (dark `Window` `#1e1e1e` vs
  `dialog.background` `#2b2b2b`), so the document rendered on a black
  substrate. The view now paints its own surface from the
  `dialog.background` token in `paintEvent` (same explicit-paint pattern as
  `_SurfaceWidget`), re-read on `theme_changed`.

- **`MarkdownHelpDialog` help body rendered on the `Window` role** — the
  content scroll area is now a `SurfaceScrollArea`, so the body surface
  reads `dialog.background` like the shell panels instead of the darker
  `Window` fill (same black-substrate mechanism as `ScrollableDialogPage` /
  `HelpDocumentView`, which already painted their surfaces).
- **`TextView` viewport rendered on the `Window` role** — the viewport and
  the text canvas are now pinned transparent by default, so the host
  surface shows behind the frame overlay (`_paint_frame` draws border only,
  no fill); `set_panel_fill(color)` still paints the raised rounded-panel
  well (it clears the transparency pin), and `set_panel_fill(None)`
  restores the transparent default.
- **`CalendarWidget` surface fell back to the `Window` role** — the widget
  now paints its own surface from the resolved `dialog.background`
  (`self._bg`) in `paintEvent` (the view stack, the views and the day
  buttons are transparent, so the fill shows through them), re-painted on
  `theme_changed` and on `set_colors`.
- **`BaseDialog` surface fell back to the `Window` role** — `paintEvent`
  now fills the dialog surface from the `dialog.background` token (mirrors
  `MarkdownHelpDialog.paintEvent`), re-read on `theme_changed`.
- **`ProcessConsoleWidget` surface fell back to the `Window` role** — the
  widget paints its own surface from the `dialog.background` token in
  `paintEvent` (same pattern as `_SurfaceWidget`), re-read in
  `_apply_styles`; the gaps around the output/input rows no longer read
  darker than the dialog surface. The `QTextEdit` QSS styling is unchanged.

- **Theme alias table removed** — `ThemeManager` no longer remaps token
  names (`ALIAS`, `theme_aliases.json`, `register_aliases` are gone):
  every `get_color`/`try_get_color` resolves the requested key directly
  from the registered palette. Previously text/foreground tokens
  (`list_item.text.normal`, `HighlightedText`, `help.nav.selected.text`)
  and chrome tokens (`slider.thumb.outer`, `switch.knob.on`, `Window`,
  `label.image.background`, …) were silently redirected to `surface.*`
  backgrounds, so explicit palette values were ignored
  (dark-on-dark list names, dark knobs/thumbs, dark selected text).
  Hosts must use canonical token names; `tests/test_no_theme_aliases.py`
  fails the suite on any reintroduced remapping.





  `h_layout.invalidate()` on a freed `QHBoxLayout` when a host
  `store.state_changed` observer (e.g.
  `magnifier_color_controls.py:251` `_on_store_state_changed`) was still
  connected at app shutdown (Python wrapper kept alive by the bound-method
  signal connection). Now `update_state` guards `self`, `h_layout` and
  `container` with `sip.isValid` + `try/except RuntimeError` before any
  layout touch; `set_actions` and `_on_scale_changed` also guard layout
  validity (same class as the 4.1.0 `AutoNavigationSection` / 4.2.1
  stale-button fixes, but for the layout object).
  connection (e.g. a store `state_changed` observer) can keep the flyout's
  Python wrapper alive past its buttons' C++ deletion (parent teardown or
  `set_actions` `deleteLater` processed by the event loop). `set_action_state`
  then hit `button.setVisible(...)` on a freed `Button` →
  `RuntimeError: Internal C++ object (Button) already deleted`
  (`magnifier_color_controls.py` `_on_store_state_changed` → `update_state`).
  Now `set_action_state`, `_on_scale_changed` and the `set_actions` cleanup
  loop guard every cached button with `sip.isValid` and self-heal the
  action dicts via `_purge_action` (same pattern as the 4.1.0
  `AutoNavigationSection` stale-row fix).




- `BackgroundLayer`: fixed a regression where `is_subregion` evaluated to `True` for standard single-region buttons due to default hit-testing paths, causing outer button borders to be skipped. `is_subregion` now correctly evaluates `False` for standard single-region buttons so that specified outer borders (e.g. `variant="surface"` or `override_border_color`) are stroked without adding unintended borders to standard/ghost buttons.
- `region_at`: documented that `z_index` is sorted `reverse=True`, so assigning a
  high `z_index` to any region makes it win the hit-test over all other regions whose
  `rect_fn` returns the same (or overlapping) rect — even when their `path_fn` areas
  are non-overlapping. Use `z_index=0` for mutually-exclusive `path_fn` regions;
  priority is only needed when paths genuinely overlap.

### Docs

- **QSS hard rule documented** — `AGENTS.md` and
  `docs/dev/DESIGN_LANGUAGE.md` now state explicitly that toolkit widgets
  are never styled via QSS (`setStyleSheet`); the painter pipeline owns all
  visual output. QSS templates (`register_qss_path`, `@token` sheets)
  remain a host-facing path for native/stock Qt widgets only.

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