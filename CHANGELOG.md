# Changelog

## 4.0.0

### Fixed
- **PySide6 6.12.0 is excluded (`PySide6-Essentials>=6.6,<6.12`)**: on 6.12.0 the test tier dies with a core dump (`SIGABRT`, exit 134) after ~130 widget tests on Python 3.10 and 3.11, and the aborting test moves between runs (`test_combo_focus_reveal.py`, then `test_button_regions.py`) — memory corruption, not a single bad assertion. The same tree on 6.11.1 is green on 3.10 (`1890 passed / 4 skipped`, 78 s). The public CI matrix caught this the first time it ever ran; raise the ceiling only after the suite is green on the new minor across 3.10–3.13.

### Added

- **The test tier's seed-dependent theme failures had one polluter: `tests/test_ui_font.py`.** Its two QSS-ordering tests register a `QWidget { background-color: @Window }` probe template and leave it applied, so the next module under a random order paints through someone else's application stylesheet — `test_icon_list_surface`'s explicitly painted `dialog.background` token then loses to it. `tests/conftest.py` grew an autouse `_restore_applied_theme_state` fixture that snapshots and restores the *applied* state, not the theme name: registered palettes, the QSS path/template, the application palette and stylesheet, the app font, the `UiFont` pin and the `UiScale` factor. Also `test_copy_clears_selection` planted a sentinel instead of asserting "the clipboard happens to differ" (process-wide state an earlier copy test can leave set). Three random seeds and the collection order are now all green (1859 passed / 4 skipped each).

- **A machine gate for every way we have broken a HiDPI raster — seven AST detectors, each calibrated on real pre-fix code.** PR #124 fixed four rasters at once (button snapshot, marquee strip, icon tint, pixmap fit) and each was found by eye, one widget at a time; the arithmetic behind them is one sentence (`QPainter` scales every command by the device's `devicePixelRatio`, so allocate `round(logical * dpr)`, tag the ratio, paint in logical px) and every departure from it has a shape a parser can see. `tests/test_dpr_contract.py` scans `src/sli_ui_toolkit/**` (plus the ratio-literal shape in `tests/**`) for: `raster-logical-tagged` (a logical-size allocation that is then tagged — the canvas becomes `size/dpr`), `ratio-dropped-on-copy` (a copy sized from another raster with the tag lost), `ratio-rounded` (`int(dpr)` — 125%/150% collapse to 1), `manual-dpr-scale` (`painter.scale(dpr, dpr)` on an already-tagged device), `ratio-hardcoded` (`setDevicePixelRatio(2)`, or a test substituting a literal ratio), `pixmap-size-as-logical` (device px read as logical geometry, the cover/contain fit), and `dpr-assumed-1` (a `dpr=1.0` default with no device read behind it). `tests/dpr_contract_allowlist.py` is a shrink-only ratchet keyed `(path, function, rule)` with a mandatory reason — it holds exactly one entry, the ratio-spoofing test that #124 deliberately kept — and `tests/test_dpr_contract_selftest.py` proves each detector red on a fragment cut from `3ccfe91^` with its provenance in the header (the three modes that never shipped here are marked `provenance: NONE` and cannot be faked with an invented snippet) and green on the file that fixed it. Public helper for future tests: `assert_device_sized(pixmap, logical_rect, *, ratio=None)` asserts both halves of the invariant and names the shape you probably just wrote. Red-before on the pre-#124 tree (`.probe/prefix`, 6 files): 13 findings in 4 of them, 0 on the two working siblings; current tree: 1 finding, allowlisted. Tests: 32 in the two new modules, plus `docs/dev/DPR_CONTRACT.md` (mode → shape → on screen → sanctioned answer, and how to add a mode).

- **`AdaptiveTabStrip` can reorder its tabs by dragging — opt-in, off by default.** The strip is a custom-painted `QWidget`, not a `QTabBar`, so `setMovable(True)` could not be inherited: the bar now carries its own gesture and exposes the `QTabBar` shape (`setMovable`/`isMovable`/`moveTab(from, to)`/`tabMoved(from, to)`, forwarded by the strip). Default is **off**, so every existing host is unchanged. A press only becomes a drag after `QApplication.startDragDistance()`, so a click still just activates; a press on a close slot never arms a drag (the slot's ignored press propagates into the bar and is filtered there); the insertion gap is marked by a painter-drawn line in the `accent` token (no QSS, no external Drag&Drop MIME — this is an internal reorder); the row auto-scrolls when the pointer reaches a viewport edge. Escape, leaving the strip, and a release that does not land on a tab are cancels — never a silent reorder. `moveTab` is the single reorder path the drag calls: the tab's entry (text, data, tooltip, close slot) travels as one unit, so the ACTIVE tab keeps its identity (`currentIndex` follows it; `currentChanged` fires only because the index number changed). Tests: `tests/test_adaptive_tab_strip_reorder.py` (16 — all red on the pre-change tree: `AttributeError: 'AdaptiveTabStrip' object has no attribute 'setMovable'`).

### Changed

- **`TimeLineEdit` now shares `Stepper`'s step gauge instead of carrying a copy of it.** The ▲/▼ gutter was written inside `TimeLineEdit` first, then extracted into `StepButtonsMixin` for `Stepper` — but the original duplicate stayed in place, so the two hosts could drift. `TimeLineEdit` is now `StepButtonsMixin, WheelScrollPolicyMixin, CustomLineEdit`: the private `_StepButtonOverlayLayer` / `_TimeLineStepButton` copies and the duplicated step privates (`_create_step_button`, the repeat timers and their slots, the button rects and `_sync_step_buttons`, plus `resizeEvent`/`eventFilter`/`setEnabled`) are deleted, and the widget implements only the mixin hooks (`_step` → `_step_minutes`, `_step_gutter_width`, `_sync_text_margins`) plus a 3-line `_start_step_hold` override that keeps the field's focus-on-arrow-press. No public API or behaviour change: constructor signature, `HH:mm` normalisation, the 22/0/1/22/350/70 geometry/repeat numbers, the paint colours and the snake_case aliases are unchanged. One mixin-owned improvement comes along: hiding the gutter mid-hold now stops the repeat timers (the duplicate leaked them). Tests: `tests/test_time_line_edit.py` (23) pins the gauge, keys, wheel policy, normalisation and geometry; they were committed green on the unmodified widget first and pass unchanged after the fold.

### Fixed

- **The timeline no longer swallows its window's `Resize` — the frozen CSD chrome on every window that hosts one.** `TimelineWidget` installs itself as an event filter on its **top-level window** (`interaction.show_event` → `install_filter_once`) only to notice fullscreen/OS resizes where its own width stays fixed; the `_layout_settle.ping()` there is a side effect of *listening*. `interaction.event_filter` returned `True` for `Resize`/`WindowStateChange`, which stops Qt's filter chain (newest-installed filter first), so any sibling filter on the same window ran never: `TitleBarGeometryFilter` (`ui/windows/csd_helpers.py`) is installed on the dialog, so `sync_csd_chrome` did not re-run and the chrome froze at the pre-resize size. Measured live on the video editor: window 1216×933 → 1620×1040 with the content relaid out (QSplitter 1604×988) while `CsdRoundedBackground` stayed [1200×917] and `CustomTitleBar` [1200×36]; Settings/Help (no timeline) resized correctly — the working-sibling diff that named this filter. The filter now pings and returns `False` for **both** targets (window and host viewport; no consumer relied on "handled" — the ping is what schedules the fit, and `SettleGate.ping` starts its timer regardless of the verdict). No public API, signal or scroll/fit behaviour change. Tests: new `tests/test_timeline_window_filter_passthrough.py` (3 — a filter installed on the window *before* the timeline's now sees its `Resize`; second order covered too; verdict `False` + gate armed for window and viewport) and `tests/test_timeline_settle_ping_passthrough.py` (2 — a real window resize still arms the gate through the filter, and the armed gate still runs the deferred `fit_view`); `tests/test_timeline_tokens.py::test_event_filter_passes_through_without_commit`. Red-before on the pre-fix tree: 4 failed / 82 passed across those three files; after: 86 passed.

- **The Settings divider no longer lands on the control groups' left border, and the content column takes part in the dialog's minimum (owner report 2026-10-28, 125 % screen).** Three separate defects in `dialog_shell.py` behind one symptom. *Scale:* the splitter handle width and the content margins were stamped once in `__init__`, so after `UiScale.set_factor(1.25)` the sidebar minimum followed (200 → 250) while the handle stayed 6 px (should be 8) and the margins (8, 8, 8, 8) (should be 10) — measured on the live Settings dialog; both now re-resolve through `scaled_px` on the `AXIS_SCALE` bus (a deliberate 0 margin/spacing stays 0 — `scaled_px` clamps to ≥1). *Line:* the divider was drawn by QStyle as a 1 **logical** px line, which at a fractional device ratio straddles two device columns and rasterizes as a blurred band against the neighbouring border. `_SidebarDialogSplitter.createHandle` now installs `_DialogSplitterHandle`, which paints the handle surface plus exactly **one device column** (`_hairline_rect`: `1/dpr` logical px, leading edge floored onto the device grid) in `dialog.border` with `surface.background` beneath, re-tinted on `theme_changed` — so the line is always crisp and keeps a visible gap on both sides of the handle (verified at DPR 1.0 / 1.25 / 1.5 / 2.0: one column, never at the handle edge, the border token's exact colour, no blend). Above 1.0 the line colour now comes from the theme token instead of the host's stock splitter styling. *Minimum:* `QScrollArea.minimumSizeHint()` is a fixed ~68×68 whatever its widget, so the right column could be squeezed under its own content (and up against the divider). `ScrollableDialogPage.minimumSizeHint()` now reports the content widget's minimum width (layout minimum or an explicitly pinned `minimumWidth`) plus the vertical scrollbar's extent, keeping the base height so vertical scrolling stays the page's job — a Settings-size column (419 px content) now reaches the shell's minimum (314 → 709 px on the probe). At factor 1.0 the metrics, the line width and the picture are unchanged for every host (Help, Export). Tests: `tests/test_dialog_shell_scale_divider.py` (10; red on the pre-change tree: `handleWidth()` stays 6 after the factor change, the handle is a stock `QSplitterHandle` with no divider painter, the page minimum is 68 against a 419-px column).
- **A title bar no longer dead-locks a window it claims to move: `startSystemMove()` returning True is a request, not proof.** Native Wayland (no press serial) and Windows accept the request and then move nothing, while `mouseMoveEvent` deliberately ignored its own motion events because "the compositor owns this drag" — so neither side moved the window: child dialogs (export, video editor, diagnostics) could not be dragged by their title bar, while X11/XWayland moved only because the manual path ran there. A claimed move is now probed on the first motion events: if the window is still at its press position after ≥2 motion events *and* ≥2 px of pointer travel, the claim is dropped, the anchor is re-pointed at the pointer (no teleport) and the existing manual `w.move(w.pos() + delta)` path takes over; a system move that really moves the window keeps ownership, so no app-level delta is added on top (no double movement). Tests: `tests/test_title_bar_drag_system_move_fallback.py` (3; red before = `inert system move is dropped` with the flag stuck set), plus the full tier 1871 passed / 4 skipped.

- **`install_scrollbar_policy()` no longer frees a widget that Qt is still iterating — this is the SIGSEGV that killed the tier under the app venv.** `QApplication.setStyle()` fans a `StyleChange` out over a **snapshot** of `QApplication.allWidgets()`, and the built-in scrollbar policy substitutes bars from inside `QStyle::polish` — `QAbstractScrollArea.setVerticalScrollBar`/`setHorizontalScrollBar` delete the previous native bar **immediately**, so a bar replaced during that fan-out stayed in Qt's snapshot as a freed `QWidget` and the loop's next `testAttribute`/`style()` was a use-after-free (`gdb`: fault in `QWidget::testAttribute_helper` with `widget->d_ptr` reading `0xa`; a probe over `allWidgets()` showed all nine widgets alive and valid *before* install, so the widget dies during the fan-out). Reproduced without pytest: one `QScrollArea` with stock bars + `app.setStyle(WidgetPolicyProxyStyle())` → exit 139, while the same tree with both bars pre-replaced → exit 0. The reported pair was a never-shown `TextScrollArea` (only its vertical bar is replaced at construction, so the stock horizontal bar was still there) left behind by `test_text_view_read_and_edit_modes`, then `install_scrollbar_policy()` in `test_install_end_to_end_and_restore` — `tests/test_scrollbar_policy.py` alone was green only because its earlier tests had already polished their areas, leaving nothing to delete. `WidgetPolicyProxyStyle.polish` now applies handlers only outside the fan-out (`_STYLE_FANOUT` brackets `install_scrollbar_policy`'s own `setStyle`); the existing post-install sweep substitutes every bar a moment later, so nothing is left native. Installing the proxy with a bare `app.setStyle(WidgetPolicyProxyStyle())` is documented as unsupported for exactly this reason. Tests: `tests/test_scrollbar_policy.py::test_install_does_not_free_bars_during_style_fanout` (red before the fix: 3/3 exit 139; green after: 3/3), the reported pair 3/3 exit 0, full tier `tests` 1859 passed / 4 skipped in 71.7 s on the app venv (PySide6 6.11.1) and the same on the system interpreter (6.11.2), and no crash under three `--randomly-seed`s.

- **The test tier prints its result line again (`N passed in Xs`) at the verbosity the gate uses.** `pyproject.toml` sets `addopts = "-q"`; a gate command that also passes `-q` (the documented form, `pytest tests -q -p no:cacheprovider -p no:randomly`) lands on verbosity −2, where pytest suppresses its final stats line — a fully green tier whose log ended at the `Docs:` line, so the run could not be cited. Not a crash and not a test defect: `-q` only from `addopts` printed `11 passed, 11 warnings in 0.12s`, adding the second `-q` printed nothing. `tests/conftest.py` now emits the same counted line (`pytest_terminal_summary`) wherever pytest stays silent, counting the reporter's own stats; runs that already print it are unchanged (no duplicate line). Verified on the full tier: `1859 passed, 4 skipped in 71.72s`.
- **Icons are rasterized at the paint device's ratio, not the application's — the ragged button icons on a 125 % screen.** `normalized_icon_pixmap` called `QIcon.pixmap(QSize)`, which uses `QGuiApplication.devicePixelRatio()`. Measured on KDE/Wayland at 125 % (2026-10-28): application **2.0**, window **1.25** — a 22 px icon came back as **44×44 @2.0** and the painter squeezed it into 27.5 device px, a **0.625 resample** that left every thin stroke ragged; the same icons were crisp at 100 % (and an A/B with the explicit ratio produced a visibly clean glyph). `normalized_icon_pixmap(..., dpr=...)` now rasterizes through `QIcon.pixmap(size, ratio)` at the caller's device ratio (the cache is keyed on it), and every paint path supplies one: `IconContent`/`IconTextContent` take the painter's ratio via the new `helpers/paint_device.py` (`painter_dpr`/`widget_dpr`), context-menu rows rasterize inside their paint pass (a row is built before it is shown on any screen, so a construction-time pixmap would carry the application ratio again), sidebar rows and the custom-title-bar app icon take the widget's ratio. New gate mode `icon-app-ratio` — detector, `docs/dev/DPR_CONTRACT.md` row, and a fixture cut from the pre-fix helper — fails `normalized_icon_pixmap(...)` without `dpr=` and a one-argument `QIcon.pixmap(size)`; the themed-icon recolour is allowlisted with its reason (it rasterizes at the icon's own native size to recolour it, and the consumer rasterizes again). Tests: `tests/test_icon_pixmap_dpr.py` (4) plus the gate and its selftest; full suite 1863 passed (the 2 timeline/flyout failures are order-dependent and also red on `main`), mypy unchanged at the 49 pre-existing stub errors.

- **Every HiDPI raster in the toolkit is now allocated in DEVICE pixels and tagged with its ratio (verified at DPR 1 / 1.25 / 2).** `QPainter` scales commands by the paint device's `devicePixelRatio` (`combinedTransform` = dpr, `worldTransform` = identity), so a raster allocated in LOGICAL px and then tagged gets a logical canvas of `size / dpr` — at DPR 2 it covers a quarter of its widget. Four sites had that shape: the `Button` marquee static snapshot (`buttons/button.py`, a 120x64 card snapshotted into a 60x32 quadrant — 1440 ink px per fast frame vs 7680 for the full frame), the marquee text strip (`helpers/marquee_text.py`, devIndep 170x10 for an intended 340x20), the icon recolour (`managers/icon_manager.py`, which *dropped* the ratio entirely so a 64x64@2x glyph painted twice as large with the art pinned to the top-left corner — now matches the `tinted_pixmap` sibling in `sidebar_nav_list/icons.py`), and `_scaled_pixmap_rect` (`buttons/content.py`, where geometry was right but the cover was a 1/dpr raster the painter upscaled — it now takes the painter's ratio and caches per ratio). Each fix is the same arithmetic: allocate `round(logical * dpr)`, `setDevicePixelRatio(dpr)`, keep painting in logical px. The rounded CSD mask (`windows/rounded_body.py`) was **measured correct** — it already allocates at `round(logical * dpr)`, tags the ratio and lets Qt scale the path, so its corners step per physical pixel (radius 12 at DPR 2 spans 24 device rows); its docstring now states that, plus the fact that the `QRegion` fallback can only step per logical pixel. Tests: `tests/test_dpr_rasters.py` (18 — a red-on-base guard per site: `deviceIndependentSize()` must equal the intended logical rect, the snapshot ink must match the full frame, the strip glyphs must match a direct `drawText` at the same phase, the mask arc must span `radius * dpr` device rows), and `tests/test_paint_cache.py` now renders into a device-resolution target instead of a logical one (the old harness compared a device-res snapshot against a 1x render, so parity could only fail at DPR > 1; 71 passed at 1 / 1.25 / 2, previously 7 failed at DPR 2).

- **A button no longer recomputes its region rects when its geometry did not change.** `Button.resizeEvent` retired the static paint snapshot and rebuilt every region rect/path unconditionally, so a host that re-applies its layout at the same size paid the full pass per re-apply — measured in the app as ~251 ms of GUI block per session-mode sync (`ui/main_window/workspace.py::sync_session_mode` toggles a button). The pass is now memoized on the inputs `ButtonController.recompute_rects` actually reads (`_region_rects_cache_key()`: widget size, density, variant, corner radius/radii, icon size, split/divider, plus a version bumped whenever the region list is rebuilt — per-region weights and `rect_fn`/`path_fn` closures cannot be compared by value); `_recompute_region_rects()` reports whether it ran, and `resizeEvent` retires the snapshot only then. A density/variant/corner-radius/icon-size change still reaches the next pass (each term is in the key) and `set_regions`/`set_spec` always invalidate. Measured: 2000 same-size resize events on a 3-region button 43.9 ms → 12.8 ms; the rects after a real resize stay identical to a from-scratch controller pass. Tests: `tests/test_button_region_recompute.py` (8 — a same-size resize and 100 no-op resizes recompute zero times, red on the previous tree at 100/100; a real resize recomputes exactly once and round-trips to identical rects; a rebuilt region list and a density/variant/corner-radius/icon-size change still recompute).

## 4.0.0

First public 4.x release: the line was developed under internal `4.0`–`4.2`
version stamps that were never published (PyPI/GitHub tags stop at `3.1.11`),
so this section carries the whole accumulated range as one release. It is
**breaking** — `TextView`, `HelpDocumentView` and the exported `Label`/
`LabelConfig` are gone; see `Removed` below for the per-class migration.

### Fixed

- **A compressed tab's label fade lands in the tab's own fill, not the window background (owner report 2026-10-23: a white block on the light-theme strip).** The fade that softens a clipped label always ended in `surface.background`, which is correct only for the selected tab; on an unselected tab (sitting on the `surface.list` strip) it painted an opaque white patch — read as a highlight instead of a fade, and compression made it appear on every tab. The fade target now comes from one mapping (`_tab_fill_color`: selected → background, hovered → hover, otherwise → strip), shared with the close-slot background so the two can never diverge, and the gradient starts from that same colour at alpha 0 instead of transparent black (which left a grey smear mid-fade). Tests: `tests/test_adaptive_tab_strip.py::test_label_fade_lands_in_the_tab_fill_not_the_window_background` renders the painter path with a controlled palette and samples the fade end (red on the previous tree: `#e5e5e5` on a `#303030` strip).

- **The tab strip compresses before it scrolls, gains side arrows, and the wheel never switches tabs (owner report 2026-10-23).** `AdaptiveTabStrip` jumped from full-width tabs straight to a clipped scrolling row: `_AdaptiveTabBar` laid every tab out at its natural width, so any overflow hid labels behind the edge while the tabs stayed full size; there was no non-pointer way to scroll; and an ignored wheel propagated to the host. `_relayout` now runs three regimes — natural widths, then proportional compression down to `_min_tab_width` (a couple of glyphs of text beside the close slot), and only then scrolling — with the row filling the bar exactly in the compressed regime. Scroll mode reserves side gutters for painter-drawn chevron arrows (theme tokens, hover/pressed states, disabled at the row ends, press-and-hold auto-repeat, one whole-tab step per click); tabs keep their natural width there so scrolling reveals readable labels; close slots of tabs under a gutter are hidden instead of floating over an arrow; `tabAt`, `_ensure_visible` and `_max_scroll_offset` measure the viewport rather than the bare bar. `wheelEvent` always consumes the gesture and only scrolls — it never calls `setCurrentIndex`, and it never reaches a host that maps the wheel to next/previous tab. The strip also re-asserts its own size after a metrics pass (`_schedule_size_resync`): a strip left one font-step narrow squeezed the bar into the compressed regime right after a scale change. Tests: `tests/test_adaptive_tab_strip.py` (4 new — compression before scrolling with an exact fill, arrows only once the minimum widths overflow with inert-at-start/step/disabled-at-end, wheel scrolls without activating with and without overflow, close slots never over a gutter).

- **The opened list now aligns the selected ROW exactly under the field, not the list's centre.** The scrollable branch centred the popup's outer box on the field, so with an even visible window (the default 12 rows) the field's centre landed on a row **boundary** — the selected row read as half a row off and needed a half-row nudge (owner report 2026-10-22). Both the fitted and the scrollable cases now use the row-alignment formula (`field inner top − visible_index * row_height`), exact for every parity and scale factor, and it matches the gear-drag frame's `centered_inner_offset`. Tests: `tests/test_combo_focus_reveal.py` — the alignment probes now assert exact equality (row top == field inner top) and a 12-row parity case was added; the even-window case is red on the previous tree, the odd-window case was already exact.

- **An opened dropdown centres the selected row under the field again (owner report 2026-10-22: the selected model sat at the bottom / just outside the list).** A scrollable popup is centred on the field, so the row under the field is the *middle* window row — but opening scrolled with `_ensure_index_visible`, which only keeps the row inside the window (putting it on the **bottom** edge). With a reveal focus targeting a row other than `currentIndex`, the selected row ended up one row *outside* the visible window. Opening now uses `_center_index_visible()` (offset = position − `maxVisibleItems // 2`, clamped); navigation (arrows, wheel, selection changes) keeps the edge-keeping primitive so it does not re-centre on every step. `_reposition()` also anchors the row the scroll targeted (`_focus_or_current_index()`), so a Find Action reveal parks the popup on the revealed row instead of on `currentIndex`. Tests: `tests/test_combo_focus_reveal.py` (3 new overflow cases: a plain open centres the current row, a reveal centres the revealed row while `currentIndex` stays put, a reveal above the current row centres too — all three fail on the pre-fix tree).

- **A typeahead query survives a transient close of the dropdown (owner report 2026-10-22: "one letter works, then it stops searching").** `showDropdown()` wiped the query buffer on every open, so any close between keystrokes restarted the search from a single character, and no amount of waiting helped — each key began a new one-character query. Measured live: settings navigation leaves a reveal dropdown open (`reveal_combo_option`); opening the field's own dropdown dismisses it, its focus restoration moves focus, and the field's dropdown closes — with the old code the buffer died there. The query is now time-boxed rather than visibility-bound, like a file manager: `hideDropdown()` clears only the highlight (`_clear_typing_highlight`), a re-open inside `TYPEAHEAD_TIMEOUT_MS` resumes the query and re-highlights its match, and the session ends only on `Escape`, an `Enter`/click commit, `clearSearch()`, a typing-mode change, or the timeout. Tests: `tests/test_combo_typing_keys.py` (4 new — transient close keeps the query and re-highlights on reopen, pause-then-another-query starts fresh, `Escape` and `Enter` end the session).

### Changed

- **`ComboBox` typing is file-manager typeahead by default (`typing_mode="jump"`), with the old filtering one call away.** Typing used to filter the rows and apply the first match immediately, so a 500-model list lost every non-match and the value changed mid-word. In the new default, the list keeps every row, the keys extend a buffer (reset after `TYPEAHEAD_TIMEOUT_MS`, 900 ms) and the highlight walks to the first row matching the buffer in list order (wrapping; a repeated key after the timeout advances to the next match). Typing is highlight-only: `currentIndex`/`currentIndexChanged` stay untouched until `Enter` or a click commits the walked row; `Up`/`Down` walk the highlight, `Backspace` shortens the buffer; the buffer is time-boxed (a transient close keeps it, `Escape`/commit/timeout end the session — see Fixed below). `ComboBox(typing_mode="filter")` / `setTypingMode("filter")` restores the previous filter-and-apply behaviour. The walked row is drawn with the same hover background as the gear-drag row plus the keyboard ring (`_focus_row_index`), even when the list was opened by mouse. `acceptsTextKeys()` is the new host-facing protocol: it reports whether unmodified letter/space keys currently belong to the field, so a host keyboard router can keep canvas shortcuts from swallowing typing (Improve-ImgSLI's overlay route ate W/A/S/D/Q/E and Space before the field saw them — measured live, `deepseek` arrived as `pk`). The field paints the typed query in both modes (`"<query> -> <value>"`) and `searchText()` returns it, so a jump query is visible without changing the value; the elided-value tooltip follows that same painted line (merged with `[combo-tooltip]`, #103). Tests: `tests/test_combo_typing_keys.py` (10: default mode and constructor validation, highlight-without-value plus row binding, Enter commit/close/signal, timeout cycling, backspace, no-match, filter compatibility, mode switch clearing the query, search-disabled/disabled behaviour).

- **Gear drag-select commits immediately on release — the settle animation and its hold are gone.** `GearDragCapability` used to animate the popup to the exact item boundary (`OutCubic`, 40 ms) and then hold the settled frame for 250 ms before applying the row and closing, so a released drag felt like it lagged behind the hand. The row under the field frame is now applied and the dropdown closed synchronously in `_finish_drag`; `GEAR_SNAP_DURATION_MS`/`GEAR_SNAP_HOLD_MS`, `snap_in_progress`, the snap animation and its guard comments are removed. Tests: `tests/test_combo_gear_drag.py::test_release_after_drag_commits_and_closes_immediately` (asserts commit/close in the same call, no snap state), plus the unchanged begin/update/overflow/frame cases.

### Fixed

- **A high-resolution wheel no longer crawls: `ScrollBegin` re-bases the glide only for a real new gesture.** `OverlayScrollArea.wheelEvent` reset the accumulated wheel target on every `ScrollBegin`; wheels/compositors that mark *every* event `ScrollBegin` re-based it to the still-unmoved value faster than the 16 ms ticker advanced it, so progress was discarded per event (owner report 2026-10-22: a notch "stretched into 3 s" in the gallery grid). Re-basing now happens only when no glide is in flight or more than `_SCROLL_GESTURE_GAP_S` (0.12 s) passed since the last accepted wheel event. Measured offscreen: 10 × `ScrollBegin` notches went 132 px → 600 px (60/notch); 40 events at 2 ms went 100 px (2.5 px/event) → 2400 px. Plain no-phase notches (`singleStep * wheelScrollLines`), `pixelDelta` 1:1, `lines == 0` → viewport·0.8 and the tick/ease feel are unchanged. Tests: `tests/test_overlay_scroll_wheel_stream.py` (7; red on the pre-change tree).
- **A copy action now ends the selection gesture on every selectable surface.** After "Copy" / "Copy as Markdown" the selection highlight stayed on the text, so the viewer looked as if the selection were still live (owner report 2026-10-21). The rule is a toolkit behaviour, not a host patch: `Text.copy_selection()` (plain / document / code — copies, then clears; returns whether anything was copied) and `Text.copy_selection_markdown(source_markdown)` (document mode; same rule) are the public entries for host menus; the built-in Ctrl+C paths route through them (`Text` plain mode, the engine's document and code copy); the label context menu's Copy clears too, and `Label`'s own Ctrl+C does the same, so the default label behaves like the documents. `TextCanvasCore.copy_selection()` is the engine half; `_copy_selection` (cut's private step) is unchanged, since cut replaces the selection right after. Tests: `tests/test_copy_clears_selection.py` (9: plain `Text` via API, Ctrl+C and its label menu, document via API and Ctrl+C, Copy-as-Markdown, code mode, `Label` menu row and Ctrl+C — all red on the pre-change tree, where the clipboard is set and `hasSelectedText()` stays True).

- **"Copy as Markdown" copies the SELECTED fragment, not the whole page.** Document-mode copy mapped the flattened selection text back into the source by substring search (`needle in markdown`, then a whitespace-tolerant regex) and returned the **entire page** whenever the search failed — which it always does beyond one plain block, because the text index strips the markup (`-`, `**`, `##`, table pipes) and joins blocks with blank lines. Reported live: selecting two help list labels and choosing "Copy as Markdown" put the whole page on the clipboard. `parse_help_blocks` now records each selectable part's source geometry (`SegmentSource`: the part's structural range, the range to emit when it is selected whole, a per-character plain→source offset map, and per-inline-span text/delimiter ranges); it rides on the blocks (harmless for host-built ones — `sources` defaults to empty) into `TextSegment.source`. `Text.selected_markdown(source)` maps the live selection through it (`text/engine/markdown_copy.py::markdown_for_range`): whole parts emit their source slice (a heading loses only its invisible `{#anchor}`), partially selected parts are sliced per character, a fully selected inline span keeps its delimiters (`**жирный**`, `` `код` ``, `[label](url)`) while a partial one copies plain text (never half a delimiter), parts are joined with the real source text between them (`\n` between list items, `\n\n` between blocks, ` | ` between table cells), and the document's trailing newline survives Select-all. Blocks without geometry (a host's hand-built `set_blocks`) fall back to the plain selection — never to the page. Tests: `tests/test_document_copy_markdown.py` (13: two-list-label selection, heading+paragraph, whole/partial inline spans, table cells, code fence, select-all, host-built blocks, empty source, CRLF, widget wiring); the pre-change tree returns the page for every multi-block case. Full suite 1673 passed, 0 failures/errors; `mypy` has no new errors.

### Added

### Added

- **A coalesced reflow can no longer paint the previous state: `PendingSettle` moves it to the paint boundary.** The "first presented frame is not the settled frame" class had owners for a value derived from unsettled metrics (`UiMetrics` / `connect_ui_metrics`) and for a self-derived size versus a POSTED layout re-run (`settle_layout`), but a DEFERRED reflow — a 0-timer that coalesces several change notifications into one pass — had none, and a reflow armed for "the next event-loop turn" runs after the frame being composed is already decided. That mechanism shipped a CSD menu-strip guard that was dead (a misspelled hook) and a session-picker grid that painted the previous column count for one frame after a resize. `sli_ui_toolkit.ui.pending_settle` now owns it: `PendingSettle.schedule(widget, fn)` coalesces repeats (last `fn` wins, one timer, `widget.update()` requested), `settle_now()` runs at most one reflow per call (the pending entry is cleared *before* `fn()`, so a reflow that re-schedules leaves the new entry pending instead of recursing; a nested or second call is a no-op), `is_pending()` reports the queue, and `settle_on_paint(widget, pending)` installs a widget-owned event filter whose `Paint` branch settles **before** the widget paints and returns `False` (painting continues). Qt delivers `Paint` after the layout pass, so the first frame presented is the settled one. A 0-timer remains as the fallback for a widget that never paints — whichever path runs first clears the pending entry, so the reflow still runs exactly once per schedule. The pending widget is held weakly and checked for a live C++ object, so a widget destroyed with a reflow still queued drops it. Companion, not replacement: `settle_layout` keeps the POSTED-layout mechanism. Tests: `tests/test_pending_settle.py` (5 — the first paint already sees the new value with the filter installed; the same harness without it paints the old value first, which is the falsification; N schedules in one turn run once with the last fn; `settle_now` is immediate and a second call is a no-op; a destroyed widget never runs the reflow).
- **An elided `ComboBox` item (or field) shows its full text as a tooltip.** Long items are painted with an ellipsis and there was no tooltip at all (owner report 2026-10-22: hovering a truncated model id must reveal the whole name). `_overlay.apply_elided_tooltip(widget, text, available_width)` sets the tooltip exactly when the painted label would elide and clears it when the text fits; it tracks the value it wrote itself, so a host-set tooltip is never overwritten. Dropdown rows use the item's full text (re-evaluated after binding, so a fresh or rebound pooled slot decides from its final width) and the closed field carries the full current value, re-synced on text/selection/scale change. Short items behave exactly as before. Tests: `tests/test_combobox_elided_tooltips.py` (10).
- **`Text.canvas()` + `TextScrollArea`: the two halves the retired `TextView` actually was (text-unification wave C, step 2b-2).** `TextView` fused a painted buffer (`TextCanvas`) with a scroll host (QScrollArea + toolkit scrollbar + rounded border overlay + optional shelf-well fill). The buffer is `Text`; the host is now `TextScrollArea` (`ui/widgets/composite/text_scroll.py`, exported from `sli_ui_toolkit.ui.widgets.composite`), which composes one `Text` and forwards `text`/`plain_text`/`set_text`/`set_markdown`/`anchor_y`/`scroll_to_anchor`/`is_editing`/`set_editing`/`enter_edit_mode`/`exit_edit_mode`/`editor`/`canvas`/`set_line_number_start`, re-emitting `changed`/`linkActivated`/`imageActivated`. `set_panel_fill(color|None)` keeps `TextView`'s raised-well behaviour (viewport palette fill + rounded mask) and `set_frame_visible(bool)` the 1 px rounded border. `Text.canvas()` returns the hosted engine surface (`None` in plain mode) — the same object `TextView.canvas()` returned, for chrome a HOST owns around a code buffer: the line-number map (`set_line_number_map`), collapsed fold rows (`set_fold_lines`), y→line hit-testing (`line_at`) and event filters (the inspector's gap markers). Typography, selection and edit state stay on `Text`. No behaviour was added beyond that accessor: the inspector Code editor, the inspector Docs page and `PreviewPanel` were migrated onto the pair in the same change. Tests: `tests/test_surface_widgets.py` (repurposed from `TextView` to `TextScrollArea` — transparent viewport, raised well, masked corner), `tests/test_preview_panel.py`, `tests/test_text_view.py` (31 tests re-pointed), `tests/test_inspector_code.py`/`test_inspector_view.py` (gutter map, folds, gap-marker clicks, docs page).

- **`Text(mode="document")` carries the whole `HelpDocumentView` surface now — the document page can move off the old host (text-unification P3 tail, document-surface slice).** Nine gaps from the audit's "Document gaps for P2" are closed on `Text`, with the old host's names: `scroll_to_anchor(anchor) -> int | None` (y-based — the value a host scroll area scrolls to — consistent with `anchor_y`, `None` when unknown), `source_markdown()` (markdown the content was last set from; cleared by `set_blocks`, which carries no source), `plain_text()` (flattened block text in every mode), `set_asset_resolver()` as an **alias** of `set_resolve_asset` (one resolver field, both spellings, ctor `resolve_asset=` unchanged), `imageActivated` / `textContextMenuRequested` kept host-owned (the lightbox and the menu live in the caller — `Text` opens neither), `set_panel_fill(enabled)` + read-only `panel_fill` (paints the `surface.background` theme token behind document/code content, palette-window fallback, default off, plain mode untouched), `size_hint_from_content() -> QSize` (painted content size at the current width, padding included), and `set_wheel_edge_forwarding(enabled=True)` (document mode: at the host scroll edge the wheel is left unswallowed so the next scroller chains; disabled, the document keeps it — interior scrolling always reaches the host). `set_line_number_start` stays code-mode only. Deliberately **not** on `Text`: `set_show_toc` / `set_toc_title` / `set_tab_stop_px` — TOC chrome and the host-measured tab column compose outside (§4 of `docs/dev/TEXT_UNIFICATION.md`), guarded by a test so the decision is not re-opened. Parity measured before editing (offscreen probe, width 640, default theme, three documents — headings/paragraphs/list/link/image): `sizeHint` 0x312 / 0x583 / 0x727 and `size_hint_from_content` 640x312 / 640x583 / 640x727, anchors 144/239 and 510, plain text identical to `HelpDocumentView.plain_text()` (231 / 67 / 1062 chars), `scroll_to_text("needle")` 689, and 0 rendered-pixel difference against the painted `TextCanvas` document path. Tests: new `tests/test_text_document_surface.py` (22; red on the pre-change tree — 13 fail on the missing accessors, and each behaviour was re-falsified by disabling its path: size hints 3, anchor alias 2, source markdown 1, resolver alias 2, wheel policy 1, panel fill 1). Full suite 1663 passed (baseline 1641 + 22); `mypy src/sli_ui_toolkit` unchanged (3 pre-existing `navigation_sections.py` errors, none in the touched file).

### Removed

- **`HelpDocumentView`, `TextView` and the two old text packages are DELETED — the engine under `ui/widgets/text/engine/` is the only implementation (text-unification wave C, step 2b-2).** Every module under `ui/widgets/composite/text_view/` was already a one-line delegate (`markdown`, `canvas`, `canvas_paint`, `constants`, `document`, `document_mode`, `editing`, `events`, `highlight`, `painter`, `selection`, `structure`, `text_index`, `layout/*`); `widget.py` (the real `TextView`) and the whole `ui/widgets/composite/help_document/` package (`view`, `canvas`, `image_lightbox`) are gone with them. Public surface: `HelpDocumentView` and `TextView` are removed from `sli_ui_toolkit.widgets` and `sli_ui_toolkit.ui.widgets.composite` (imports and `__all__`); `TextCanvas` stays exported but IS the engine class (`TextCanvasCore`, one class — the wrapper subclass is gone), and `TextSelection` / `python_line_spans` / `python_span_colors` are re-sourced from `text.engine.{selection,highlight}`. Callers migrated in the same change: the inspector **Docs** page (`Text(mode="document")` inside `TextScrollArea`, links/anchors unchanged), the inspector **Code** editor (`Text(mode="code")` + host scroller; gutter map, fold rows, gap-marker clicks, edit/revert/save all unchanged), `PreviewPanel`/`NonPropagatingTextEdit` (now a `TextScrollArea` subclass with the same consume-the-wheel-at-the-edges policy), and `MarkdownHelpDialog` (each page is `Text(mode="document")`; the dialog itself is KEPT — demo-only per `docs/dev/TODO.md`, its deletion is a separate decision). Migration for hosts: `TextView(code)` → `Text(code, mode="code", editable=True)` in a host scroller (`TextScrollArea(code, mode="code")` in the toolkit) — `Text` is a plain `QWidget` and never scrolls; `enter_edit_mode()`/`exit_edit_mode()` → `set_editing(True/False)` on `Text` (the host keeps its convenience spellings); `is_document()` → `mode() == "document"`; `scroll_to_anchor()` returns the host y (`bool` → `int | None`). `HelpDocumentView(md)` → `Text(md, mode="document")` + host-owned chrome: TOC list, image lightbox and search box compose OUTSIDE the widget (`Text` emits `linkActivated`/`imageActivated` and exposes `anchor_y`/`scroll_to_anchor`/`scroll_to_text`/`size_hint_from_content`). `HelpDocumentView`'s `set_show_toc`-style options are not re-created — TOC chrome was always the host's. Tests: 1667 → 1657 passed (0 failures/errors), every removed test named: `test_help_document_view.py` -3 (TOC link pitch, TOC restyle after nav — TOC chrome deleted with the host; lightbox CSD offset — the lightbox widget is gone, the host owns the viewer), `test_live_stale_widgets.py` -3 (`HelpDocumentView` root/TOC padding + its scale-only granularity case; document re-layout on a live scale is pinned by `test_help_document_scale.py`), `test_text_engine_motion.py` -3 (four shim-identity tests deleted, one engine-path guard added), `test_text_view.py` -1 (document image lightbox — covered by `test_help_document_view.py::test_help_document_figure_click_emits_image_activated`); the remaining 33 + 31 + 4 + 3 tests were re-pointed at `Text`/`TextScrollArea`/the engine and stay green. `docs/user/TEXT_VIEW_API.md` still describes the deleted widget — docs are out of this wave's scope.

- **`Label` / `LabelConfig` are gone from the public surface (text-unification wave C).** The surviving widget is `Text` (`mode="plain"` for static text, `document`/`code` for the painted engine), and every app-side caller now uses it. `sli_ui_toolkit.widgets` and `sli_ui_toolkit` no longer export `Label`/`LabelConfig`; the class itself remains at `sli_ui_toolkit.ui.widgets.atomic.text_labels.Label` as an **internal, documented exception** for the three capabilities `Text` does not cover yet — native text-interaction flags (`setTextInteractionFlags`), plain-mode rich text with clickable anchors, and inline pixmaps — each tracked as its own ticket. `LabelVariantSpec`, `register_label_variant`/`get_label_variant` and `DropZoneLabel` stay exported. Migration for hosts: `Label(text, variant=..., pixel_size=..., word_wrap=...)` → `Text(text, mode="plain", variant=..., pixel_size=..., word_wrap=...)`; parity is measured (pixel-identical on 5 of 6 shapes; the one named divergence is the wrapped `sizeHint` width, with `heightForWidth` identical). Tests: 1667 passed after the export drop + moving 16 in-repo import sites to the internal module (no behaviour change).

### Changed

- **The variant spec now lives in `text/variants.py` — the investment that unblocks deleting `Label` (text-unification wave C, step 1).** `TextVariantSpec` is defined once in `ui/widgets/text/variants.py` (same frozen dataclass, same field names/order/types/defaults: `name`, `pixel_size=None`, `bold=False`, `color_token="dialog.text"`, `minimum_width=0`, `expanding=False`, `elide=False`) together with the preset table (`TEXT_VARIANTS`, the one `_VARIANTS` dict) and the registry (`register_text_variant` / `get_text_variant`). `ui/widgets/atomic/text_labels.py` now imports it back and re-exports the old surface for compatibility — `LabelVariantSpec` is an **alias of the same class object** (`LabelVariantSpec is TextVariantSpec`), `LABEL_VARIANTS` is the **same table object**, and `register_label_variant` / `get_label_variant` are thin delegations to the new functions. The dependency arrow flipped: the surviving widget no longer owns the spec being retired. Nothing else changed — `Label`, `LabelConfig`, `Label`'s variant path, and every public export (`sli_ui_toolkit`, `widgets.py`, `atomic/__init__.py`, `zones.py`'s positional `LabelVariantSpec(...)`) are untouched, so this is import-level only and renders identically. `grep -rn "class TextVariantSpec\|class LabelVariantSpec" src/` has one hit (the unrelated `buttons/variants.py:VariantSpec` is a different spec and predates this change). Tests: new `tests/test_text_variants_home.py` (4 — class identity, one shared table both directions, positional construction, `Label(..., variant=)` still resolving); full suite 1663 passed, `tests/test_text.py` unchanged and green.

- **The toolkit's own display labels build the unified `Text` widget now — 24 direct `Label(...)` sites over 9 files moved to `Text(..., mode="plain")` (text-unification P3, toolkit slice).** Inspector (`rendering`, `view`, `tree`, `code/editor`, `code/factory`), `base_flyout/builder` (helper return annotations now `Text`), `help_document/view` (TOC caption only — `_LinkLabel` stays a `Label` subclass), the custom title bar title, and the `marquee_text` docstrings (they now point at `Text(..., mode="plain", marquee=True)`). Every positional and keyword value is unchanged. Parity measured offscreen over the 20 migrated parameter sets: identical `sizeHint`/`minimumSizeHint`/`heightForWidth` and zero rendered-pixel difference for the single-line shapes; `tests/test_text.py` + `tests/test_button_row_marquee.py` and the full suite stay green (1641). Two measured, benign divergences: a wrapped label's `sizeHint` is the unwrapped line width in `Text` (QLabel reports a wrapped hint; `minimumSizeHint` and `heightForWidth` match, so layout minimums are unchanged), and a `selectable` label paints 1 px lower at some (row height, font size) parities — the native QLabel selectable-text paint path, which differs from `Text` by exactly the same amount on stock `QLabel` and is not `Label` behaviour. `tests/inspector_helpers.py` and `tests/test_inspector_colors.py::_page_labels` now collect `Text` rows as well as `Label` (they pinned the row class via `findChildren(Label)`). `Label` itself, its public export, and `text/variants.py`'s dependency on `LabelVariantSpec` are untouched — retirement is a later wave.

### Added

- **CI gate for the value-edit contract: a new value control can no longer silently eat navigation arrows.** `tests/test_value_control_edit_contract.py` + `tests/value_controls_allowlist.py` mirror the app-side Enter-to-edit guard inside the toolkit. `VALUE_CONTROLS` registers every real value control (`ui.widgets.atomic.slider:Slider` — reason + factory + WASD flag) and `ALLOWLIST` records the `is_editing()` declarations that are *not* value controls (the text editors `Text`, `TextCanvasCore`, `TextView` — text-entry edit state, one-line reason each). An AST scan of `src/sli_ui_toolkit` fails, naming `module:Class`, for any class that subclasses `Slider` (transitively) or defines `is_editing` and is in neither table; dead entries (a class that no longer exists) fail too, so a rename cannot silently widen the gate. `SpinBox` needs no entry by design — it is a `CustomLineEdit` typed control with no `is_editing` edit mode, and the scan only gates `is_editing`/`Slider` subclasses. Each registered control is exercised with real keys through a real `ToolbarRowsSection` (`QTest.keyClick`, the section gate — not a direct `keyPressEvent` call): idle arrows leave the value untouched and move the ring, Enter enters edit mode, arrows (and WASD) adjust, Enter commits, Esc reverts to the entry value. Falsification is part of the module: synthetic sources declaring an unregistered `is_editing` class (`Mystery`) and an unregistered `Slider` subclass (`Fancy`/`Fancier`) must turn the scan red and name the offender; the same source passes once covered. No `src/` change.

### Fixed

- **A right-button press no longer collapses a document's text selection.** In document mode the canvas treated EVERY mouse press as the start of a selection gesture, so the right-press that opens the host's context menu re-anchored the selection to a caret at the click point and the selection was gone before the menu was built — every copy row came up disabled and the highlight vanished. The document path now ignores non-left buttons (press, double-click and release), the same rule the plain-mode `Text` and the retired document core already had. A right-release also stops activating the link under the cursor. Tests: `tests/test_text_document_surface.py` (2 new — the selection survives a right-press/release, and a right-click on a link does not activate it; both red on the pre-change tree). Full suite 1661 passed (baseline 1659 + 2).

- **The UI inspector re-derives its own chrome on a live UI-scale / font change (no metrics subscription existed at all).** `InspectorWindow` now carries **one** `connect_ui_metrics(..., axes=frozenset({AXIS_SCALE, AXIS_FONT}))` subscription and fans a coalesced change out to the whole subtree: page content margins/spacing, the toolbar margins/spacing, Layout/Constructor tree rows, the Code editor, an already-built preview and the color swatches. Every design-px constant is a named module constant resolved through `scaled_px()` at USE time (never at import): `tree.py` row height 26 / indent 14 / chevron 12 / text gap 4 / twist offset 2, `view.py` page `(8,8,8,8)` + spacing 4 and toolbar `(8,6,8,2)` + spacing 6, `rendering.py` indent + row spacing 6 + the 220 px REF button cap, `code/editor.py` spacings 4/6/3 and preview-well `(8,8,8,8)` / 160 / 48, `code/preview.py` preview 144/48 and the well radius 8, `code/factory.py` editor floor 160 + parent-row spacing 6, and `fields.py`'s swatch 14. The raw `self.setFixedHeight(self._ROW_HEIGHT)` in `_TreeNodeRow.__init__` is **deleted** — it landed after `Button` had already applied its scaled fixed size, so every row stayed 26 px across a live scale change. Behaviour at factor 1.0 is byte-identical (zero insets stay zero: `scaled_px` clamps to 1). Tests: new `tests/test_inspector_metrics.py` (2; red on the pre-change tree — row height stayed `26`, indent 14, page margins `(8,8,8,8)`, preview `144/48`, swatch 14 after `set_factor(1.25)`, and a font-axis emit reached no subscriber). `tests/test_px_scaling_contract.py` and `tests/test_ui_metrics_contract.py` stay green.

- **A value changes only after an explicit Enter — the value-edit contract (owner request 2026-10-19).** Navigating must never adjust a value: `Slider` used to accept Left/Right unconditionally for value-stepping, and the flyout's `_FlyoutNavigationSection` gave it (and `ScrollValueButton`) Left/Right first refusal unconditionally, so a focused slider ate the navigation keys. `Slider` now has an explicit **edit mode**: `Enter` enters (capturing the entry value) and paints a visible affordance (groove border + thumb ring turn accent — the existing focus-ring tokens, not a new look), arrows and WASD (`W/A/S/D` → Up/Left/Down/Right) then adjust the value, `Enter` again commits, `Esc` reverts to the captured value and leaves; focus leaving ends edit mode with the value as-is. While idle it `event.ignore()`s **all four** arrows (previously Up/Down only), so ring navigation keeps them. The gate lives in the sections; a control without the attribute keeps today's behaviour: `navigation_sections.arrow_gate_open(widget)` / `value_control_is_editing(widget)` duck-type `is_editing() -> bool` (`Slider.is_editing()`), `ToolbarRowsSection._widget_handles` (and therefore `AutoNavigationSection`) declines trial-dispatch while a value control reports not-editing, and the flyout sends Left/Right **and** (while editing) Up/Down to the focused control only when the gate is open. `SpinBox`/`DoubleSpinBox`/`ComboBox` are unaffected (they never stepped Left/Right). Contract table + checklist: `docs/dev/NAVIGATION.md` §1.1. Tests: new `tests/test_slider_edit_mode.py` (6: arrows navigate without touching the value; Enter/arrows/WASD/Enter commit; Esc reverts; the editing affordance repaints the track band; a control without `is_editing()` still receives arrows; the flyout gates value arrows on edit mode) plus a `Slider` Left/Right case in `tests/test_nav_arrow_key_contract.py` — all red against the pre-change source (7 failed / 4 passed). Full suite 1627 passed.

- **Navigation sections follow VISUAL ROWS too, and an auto section's owner chain boots the walk (owner report 2026-10-19: the colour-picker dialog's arrow walk did nothing at all).** `AutoNavigationSection` claimed only its own descendants, so a dialog that registered the section on an inner container dropped every arrow key while focus sat on the dialog window — `NavigationManager` found no owning section and yielded (12× Down, focus unmoved) — and its inherited `focus_nearest()` read row *containers* the section never had and always returned `False`, while the one row that could be reached walked by x only. The row banding is now the shared `ui/managers/nav_rows.py::group_visual_rows`, used by `BaseFlyout._navigable_rows` as well, so "a row is a centre-y band, x inside a row" holds on both paths (one implementation, no third traversal). `AutoNavigationSection` rescans the owner's `StrongFocus` leaves into those rows, claims the containers the owner lives in (the dialog, a page — not siblings), and bootstraps the first arrow into the rows when focus is on the owner or one of those containers; `focus_nearest()` lands on the row nearest the click's y and returns `True` when it moved. `ToolbarRowsSection._rows()` now orders rows by on-screen centre y (stable, so same-band rows keep the host's order) instead of trusting the provider's construction/index order. Empty/one-row sections, scroll behaviour, `side="above/below/left/right"` flyout entry and toggle handling are unchanged. Tests: `tests/test_nav_auto_section_rows.py` (5; red against the pre-change source — Down on the dialog left focus on it and `focus_nearest` returned `False`, 2 failed / 3 passed); `tests/test_flyout_row_order.py` stays green.

- **A flyout's arrow navigation follows VISUAL ROWS, not x order (owner report 2026-10-19).** `BaseFlyout._navigate_focusable` collected every `StrongFocus` descendant and sorted it **by centre x only** — not a reading order. Measured live in the label-text flyout: Down went `Opacity → Draw background`(a right-aligned `Switch`)` → Text color`(back up the panel) → Background → Edges → Split line, i.e. the switch sat out of place, and the two side-by-side radio buttons of `Position` were chained as consecutive vertical steps, so Up from the right one walked left ("they think they are stacked"). Rows are now built by centre-y bands (tolerance = half the median child height) with x inside a row: Up/Down step rows and keep the column (nearest-x in the target row), Left/Right step inside the current row and only fall back to the flat order at the row's edge. The existing exit/wrap semantics (`_nav_exit`, toggle `Up`-to-anchor, linked-owner return at the first/last row) are untouched — they run before the row step. Tests: `tests/test_flyout_row_order.py` (2, red against the x-sorted traversal: Down from the switch's row landed on the right radio of a *later* row and Down from the left radio stepped sideways).

- **`Switch` now shows a keyboard focus ring, with the room to draw it (owner report 2026-10-19: "на свиче непонятно, есть кольцо фокуса или нет — отличить невозможно").** The switch paints itself and never attached `Button`'s `FocusLayer`; its `focusInEvent` only called `update()`, so a focused switch looked exactly like an unfocused one. It now resolves modality centrally (`resolve_keyboard_focus`, as `Slider` does — a mouse click never paints a ring) and draws the ring from the new shared helper `ui/widgets/atomic/focus_ring.py::paint_focus_ring` (the one the `Slider` also uses now, instead of its private copy: one ring look, not two). The track also reserved no space for a ring (widget height == track height, track at x=0), so the ring overlapped the switch geometry — the owner's second report; a `RING_GUTTER` (2 design px, `scaled_px`-resolved) now insets the track and is added to `sizeHint` so the ring lands on the widget boundary outside the track. Tests: `tests/test_switch_focus_ring.py` (2: a keyboard-focused switch changes its render in the ring band and not in its centre; a mouse-focused one does not; plus a Tab reason follows the central resolver).

- **Four more toolkit surfaces re-derive their cached design-px geometry on a live appearance change — the residual live-stale widgets of `plan-live-appearance-fixes-2026-10-19`.** Each cached derived geometry from its construction-time `UiScale` factor (or never re-derived it), so a live Settings → OK change left it at design px until a rebuild. (1) `HelpDocumentView` — the root padding (`20/16/20/24` + `10` spacing) and the cached TOC frame's inner padding (`12/10/12/10` + `4` spacing) were build-time literals and the view subscribed to `theme_changed` only: it now rides the bus (`connect_ui_metrics(..., axes=frozenset({AXIS_SCALE}))` — scale-only, the padding is font-independent and the body canvas owns its own font axis) and re-derives both through `scaled_px` at use time. (2) `_SimpleRow` (`simple_options_flyout/row.py`) — the label font was already re-resolved live, but the row's own horizontal pad (`scaled_px(8)`) was stamped once at construction and `sizeHint()` reads it, so the label/accent inset stayed at the old factor; `_apply_scale` now re-derives it. (3) `ToastNotification` — `_MARGINS_WITH_ACTION`/`_MARGINS_NO_ACTION` and the progress/action-row spacings were applied in raw design px (never `scaled_px`) and `_on_scale_changed` never re-applied them, so the toast's width fit used old insets around a grown label; a new `_apply_layout_metrics` re-derives them at the live factor. (4) `CustomGroupWidget`'s top-caption branch (`caption="top"`) — its content margins (`12`, title-derived top, `12`, `12`) and `8` spacing were raw literals while the bottom branch already scaled; it now resolves through `scaled_px` (as do the top-caption `sizeHint`/paint title paddings), so it follows the factor like the bottom branch. `CalendarDayButton` was audited and needs no change — its floor/hints already re-derive (`day_button.py:48-60`, `:115-119`) and are pinned by `tests/test_px_ratchet_drain.py`. Tests: new `tests/test_live_stale_widgets.py` (6; all fail against the pre-change source — margins stay `(20,16,20,24)`/`(8,0,8,0)`/`(12,10,12,6)`/`(12,…,12)`, plus a granularity case proving a font-only emit does not wake the scale-only help view). Full suite 1611 passed.

- **The px-scaling ratchet's offender list is drained: every raw-literal chrome geometry named as an "offender" in `tests/px_scaling_allowlist.py` now resolves through `scaled_px()` at USE time (kit-px-sweep).** All 5 offender files (8 sites) fixed; `EXEMPTIONS` drops 10 → 5 and `EXEMPTED_SITES` follows (7 by-design sites in 5 files remain — the `QSize(1,1)` placeholders, the `QSize(24,24)` design-px carriers and the 1 px hairlines). Fixed: `ui/widgets/buttons/style_api.py` (icon-only `setFixedSize(36, 36)` → a design fixed size the Button re-derives in `on_scale_changed`), `atomic/drop_zone_label.py` (80 px floor), `composite/calendar_widget/day_button.py` (28×36 floor + 50×70 / 28×36 hints), `composite/markdown_help_dialog.py` (`resize(800, 600)`; the nav row's `QSize(0, 35)` is now handed to the row `Button` as a design row height — the old raw `setSizeHint` left the row bound to the nav's 44-design default, so a live change took it to 66 px instead of 52), `list_items/editable_list_item.py` (28×28 checkbox floor). `DropZoneLabel`, `CalendarDayButton`, `EditableListItem` and `MarkdownHelpDialog` now also ride the appearance bus (`connect_ui_metrics(..., axes=frozenset({AXIS_FONT, AXIS_SCALE}))`) so the floors/rows/nav width re-derive on a live scale/font change. Tests: new `tests/test_px_ratchet_drain.py` (5; red on the pre-change source: 36==54, 80==120, 50×70==75×105, 66==52 nav row, 54==42 checkbox); `tests/test_px_scaling_contract.py` stays at 0 un-exempted findings.
- **A toolkit flyout's rows are keyboard-reachable even in preview mode — the draw-background `Switch` class.** `BaseFlyout.show_aligned` derived its nav-section default from `grab_focus` alone: `grab_focus=False` (a panel that must not steal focus, e.g. the host's `FontSettingsFlyout` shown through `show_top_left_of` → `show_aligned`) meant the flyout was never registered as a `NavigationSection`, so arrow keys skipped over it entirely and its rows (a `Switch`) could not be reached or toggled from the keyboard. Registration is now content-aware: with no explicit `register_nav_section`, a preview flyout that actually holds an enabled `StrongFocus` descendant stays registered (`_has_navigable_content`, `base_flyout/placement.py`), while a content-free informational flyout (a value-preview pill) still stays out of arrow routing; an explicit `register_nav_section=True/False` forces the decision, and the hover-preview path (`auto_preview`, which passes `False`) is unaffected. No API added, `owns()` unchanged. Tests: `tests/test_flyout_switch_navigation.py` (1; red against the pre-change default — the `Switch` is owned by no section and Down from the anchor never reaches it — green after).

- **A live UI-scale change now re-derives the context-menu row pitch and the Button's content sections (owner report 2026-10-19: rows cramped / chips misaligned after Settings → OK).** Two "value derived once, then cached" bugs, one per surface. (1) `ContextMenuRow`'s own fixed height did follow the scale (`Button` re-applies it on `scale_changed`), but the section-title / separator heights (`setFixedHeight(scaled_px(24|9))` at construction), the check gutter (`check_gutter=scaled_px(12)` passed once by `content.set_entries`), the trailing shortcut/arrow width and the rasterized row icon were construction-time snapshots, and the cached menu (it survives a scale change — the app's flyouts are long-lived) never re-fit itself: at 150% the section title stayed 24 px and the separator 9 px inside 48 px rows, the gutter stayed 12 px so the width only grew by the text delta, and the icon stayed 16 px. `ContextMenu` now subscribes to the appearance bus (`connect_ui_metrics(..., axes=frozenset({AXIS_FONT, AXIS_SCALE}))`, `plan-ui-metrics-systemic`) and re-runs `_relayout_widths`, which re-derives every cached chrome metric at the live factor: `SeparatorRow` / `SectionTitleRow` expose `refresh_metrics()` (design-px `DESIGN_HEIGHT` re-scaled), `ContextMenuRow._check_gutter` is a property resolving the design gutter at use time, and `refresh_metrics` re-rasterizes the icon pixmap and re-measures the trailing width. (2) The Button API's per-section internal padding was applied in raw design px inside the paint / sizeHint paths: `content_padding` in `content._rect` (and `_wrapped_height_for_width`) and the icon↔label `gap` in `IconTextContent.draw` never went through `scaled_px`, so every chip built on the API (icon + text + badge — e.g. the gallery card's "Анализ" pill) kept 8/4 px insets and a 6 px gap while its font grew. Both now resolve through the new `resolve_content_insets` / `resolve_gap_px` at USE time (a zero inset stays zero — `scaled_px` clamps to 1), and `BadgeLayer` resolves its design-px badge box (14 px high, 12×10 plain, +2 offsets) at paint time instead of hardcoding it. Tests: new `tests/test_live_scale_section_pitch.py` (5 — build at 1.0, `set_factor(1.5)` + a real event-loop turn so the bus coalesces through its zero-timer, then assert exact numbers: section title 24→36, separator 9→14, row hint 32→48, gutter 12→18, trailing 20→30, re-derived icon request 16→24; chip insets (8,4)→(12,6) and rendered icon↔label gap 6→9; badge box 14→21. All 5 fail against the pre-change source: `24 == 36`, `16 == 24`, `(8,4) == (12,6)`, `7 == 9`, `14 == 21`).

### Added

- **`NavigationManager.bind_group_flyout(group, flyout, side=…)`** — register one flyout for a whole button group; any focusable member resolves it by walking its parent chain (`link_group` / `extension_for`), so a host no longer binds the same panel to every child and keeps that list in sync.

### Added

- **CI gate against the UI-scale class: import-baked `scaled_px` constants and raw-literal chrome geometry.** `tests/test_px_scaling_contract.py` + `tests/px_scaling_allowlist.py` (AST). Shape (a): `scaled_px(...)` evaluated into an import-time constant (module level, class body, function default) — 0 in the toolkit today, so a first new one fails immediately; a module-level `PAD = scaled_px(8)` is the synthetic red case. Shape (b): geometry calls whose arguments are ALL raw int literals (`setFixed*`/`setMinimum*`/`setMaximum*`/`resize(`/`QSize(`) inside `ui/widgets`/`ui/windows` — 15 sites in 10 files today, each seeded in `EXEMPTIONS` with a reason and a per-file count in `EXEMPTED_SITES` so a NEW offender fails even inside an already-exempt file and a fix is a one-line deletion. Real offenders recorded: `buttons/style_api.py` (36x36 icon-only branch while the sibling `sizeHint` branch resolves the same design size via `scaled_px(36)`), `calendar_widget/day_button.py`, `drop_zone_label.py:57` (80 px floor), `markdown_help_dialog.py` (`resize(800,600)`, `QSize(0,35)`), `list_items/editable_list_item.py:37` (28x28 floor). By-design entries documented: 1 px hairlines, degenerate 1x1 placeholders, `QSize(24,24)` design-px carriers resolved via `scaled_px()` one call later. `0` and `QWIDGETSIZE_MAX` are treated as structural sentinels, and a mixed call (`setFixedSize(size, size + offset*2)`) is deliberately not flagged. Origin: the owner's live-scale reports (chips/flyouts keeping design px); rationale + wave plan: see the project's internal engineering notes.

### Fixed

- **A widget's font can no longer silently take its *size* from the ancestor chain (the "first tab wrong for a couple of frames, then resizes" report).** `QFont` copies carry a size *value* without necessarily a resolved size bit, and `QWidget.setFont` fills every unresolved attribute from the widget's **inherited** font. Improve-ImgSLI applies its face as `QApplication.setFont(QFont(family))` — family only, size left to the platform default — *after* the window's widget chain is built, so a widget that pinned that face kept the chain's pre-apply size: measured live 2026-10-19, the workspace tab bar resolved `Source Sans 3` 12 pt, Qt applied 11 pt from the window chain (`parent='Adwaita Sans'/11.00`), the first tab was measured and painted 178x37 instead of 186x38, and the pill jumped a beat later when the shown window re-resolved the chain. `UiFont.base_font()` now pins the size into the resolve mask via the new `pin_font_size(font)` (also used by `rebase_family`), so every resolved face is fully specified. Two live instances of the same class are fixed with it: `ConsoleView` cached a raw `QFont(self.font())` copy for its whole lifetime (and never re-derived it — a console built before the face landed stayed at the wrong size *permanently*, not for one frame), now `apply_ui_font(self)` + the bus's `AXIS_FONT` axis (a host font set through `set_font` stays host-owned and is pinned too), and `time_line_edit`'s step-button copy already pinned its own pixel size. Tests: new `tests/test_ui_font_resolved_size.py` (2; red against the pre-fix `base_font()`: the tab widths disagree 390 vs 191 across the host's startup face change) and new `tests/test_font_resolution_contract.py` (AST contract — an unpinned `QFont(<x>.font())` copy, or `QFontMetrics(self.font())` in a file that never resolves the face, fails CI; the resolver itself is the one recorded exemption, and the detector is falsified against the pre-fix shapes).

- **A flyout's close no longer steals focus from another flyout navigation just entered.** `_finish_hide → _restore_focus_policies` re-asserted the keyboard on the hide's anchor/target unless the current focus was a *sibling in the same navigation section* — a flyout it did not know about wins, so a `ScrollValueButton`'s value pill entered with Up was immediately cancelled: the anchor's FocusOut hid a panel that had been shown on focus (magnifier settings), and that panel's restore `setFocus`-ed the toolbar back (focus landed on the `ButtonGroup`, `pill.focusIn` never fired). Verified live through the app's focus trace: `_handle_button_focus_event → _hide_immediately → BaseFlyout.hide → _finish_hide → _restore_focus_policies → target.setFocus`. The restore now skips whenever the current focus widget **is a flyout** (`_is_flyout_widget`, `lifecycle.py`): that hide is a consequence of the focus move, not a reason to undo it. The narrow guard is kept for every other case (focus that left to a non-flyout, e.g. the CSD title bar, still restores to the anchor). Tests: `tests/test_flyout_focus_restore.py` (2; the first fails against the pre-change guard — focus is yanked back off the entering flyout).

### Changed

- **`NavigationManager`: flyout links are per `(anchor, side)`, plus group-level ownership (`link` / `link_group` / `bind_group_flyout` / `extension_for`).** The old `_extensions_below` held **one** extension per anchor widget, so `bind_flyout(anchor, pill, side="above")` followed by `bind_flyout(anchor, panel, side="below")` silently overwrote the first link even though `bind_flyout` advertises four sides — a button could not carry a value pill *above* and a settings panel *below* (a host comment had explicitly assumed the above-link survived). The registry is now `{anchor: {side: flyout}}` (groups the same), and `extension_for(owner, side)` resolves the owner's own side first, then a group link found by walking the parent chain; the lookup stamps `extension_owner` with the member the user entered from, so the flyout's own Up/Down exit hands focus back to that exact button. `link_below` / `extension_below` / `unlink_below` remain as back-compat shims (side "below", then any side), and both registries drop their entries on owner/flyout destruction. `ToolbarRowsSection` / `AutoNavigationSection` / `IconListNavSection` now query `extension_for(widget, <side>)` directly instead of one ambiguous `extension_below` lookup plus a `flyout_side` re-check. `bind_group_flyout(group, flyout, side=…)` lets a host register one panel for a whole button group instead of a per-child bind loop. A flyout that declines a boundary arrow now hands the key back to the widget it was entered from (its `extension_owner`) and continues from *that* widget's section — registration order is meaningless for a flyout (its section is appended when shown), so the old neighbour hop landed on the toolbar section's `focus_last`: Up out of a value pill jumped the ring to the window's bottom row instead of the row above the anchor (one-shot `_skip_extension` keeps the handoff from re-entering the flyout it just left). Tests: `tests/test_nav_flyout_sides.py` (7: both sides survive a second link, legacy `link_below` contract, a group link serves every member, a member's own link wins over the group link on the same side, Up out of an above-linked flyout lands in the row above the anchor, a hidden flyout is not returned, a destroyed flyout is forgotten).

### Added

- **Unified UI-metrics change channel (`UiMetrics` / `connect_ui_metrics`) + `MetricsContainer`** — `UiFont.font_changed` and `UiScale.scale_changed` were two independent global signals, so every widget deriving geometry from either had to remember to subscribe to **both** (the asymmetry behind the tab strip's stale bar height). `sli_ui_toolkit.ui.managers.UiMetrics` folds them into one `changed` signal and `connect_ui_metrics(widget, slot)` wires a slot to it once (idempotent per `(widget, slot)`, returns the `(signal, connection)` pairs for teardown, auto-disconnects on `widget.destroyed`); a same-turn font+scale pair is coalesced through a zero-timer into **one** call, after both sources have settled. `UiFont._emit_changed()` and `UiScale.set_factor()` notify the channel on a real change (existing single-signal connections keep working — addition, not replacement). `MetricsContainer` (`sli_ui_toolkit.ui.widgets`, next to `ThemedContainer`) is the metrics analogue of the theme template method: `on_ui_metrics_changed()` = `on_metrics_derived()` → `on_metrics_children()` → `updateGeometry()` + `update()`. First adopter: `AdaptiveTabStrip` re-runs `_apply_layout_metrics()` + `_sync_visual_tab_height()` on a metrics change (the missing font path — the strip subscribed only to `scale_changed`), and `_AdaptiveTabBar` migrates its `scale_changed`/`font_changed` wiring to the unified channel. Tests: `tests/test_ui_metrics.py`, `tests/test_metrics_container.py`, `tests/test_adaptive_tab_strip_metrics_change.py`.

### Changed

- **The UI-metrics channel is now the appearance bus — one driver for theme + scale + font, with granularity** (`plan-ui-metrics-systemic` P3). `UiMetrics.changed` carries the axes that changed as a `frozenset[str]` ⊆ `{"theme","scale","font"}` (was a bare `Signal()`), so a consumer subscribed to one axis is no longer woken by an unrelated change — over-invalidation is the anti-pattern the bus exists to avoid. `connect_ui_metrics(widget, slot, *, axes=None)` filters per subscription (`axes=None` = every axis; `{"scale"}` wakes the slot only on scale changes), and a zero-arg slot (the T1 call style) is adapted — called with no args — so every existing call site keeps working unchanged. `ThemeManager` emits `{"theme"}` into the bus (its `theme_changed` stays a thin alias: existing subscribers keep working, synchronously, with no payload); `UiFont` / `UiScale` emit `{"font"}` / `{"scale"}` through the new coalesced producer entry `UiMetrics.emit_appearance(axes)`. `UiMetrics.begin_appearance()` / `end_appearance()` batch a group of producer notifications into **one** emission carrying the union of the axes seen in between — the app-side ordering trap (theme re-push → font re-apply) becomes one batched emit instead of a comment-enforced order. New `tests/test_appearance_bus_theme.py` (4: `set_theme(...)` reaches a bus subscriber with `{"theme"}`, the `theme_changed` alias still fires, theme+font in one turn coalesce to one union emit, a `{"scale"}` subscriber is not woken by a theme change) and `tests/test_ui_metrics_contract.py` (AST contract — a module connecting a raw `font_changed` / `scale_changed` must use `connect_ui_metrics` / `MetricsContainer` or carry a recorded exemption; lands at 0 findings with the 30 not-yet-migrated offender files from the plan's 2026-10-18 audit recorded as exemptions, ratcheting down as T2b migrates them). `tests/test_ui_metrics.py` +7 (axes payload per source, granularity both ways, batch union, batch merged with a same-turn direct emit, idempotency per `(widget, slot, axes)`, zero-arg adaptation). The mass migration of the 27 scale-only offenders is wave T2b, not this change.

- **T2b: the 25 migratable metrics offenders ride the bus, each with the axes it derives from** (`plan-ui-metrics-systemic` T2b). The contract's offender list (`EXEMPTIONS`) drops from 30 to 5: 25 files now subscribe through `connect_ui_metrics` — 12 with `frozenset({AXIS_FONT, AXIS_SCALE})` where the cached state is painted-text/font-metric derived (tab-bar widths, label/row/card/notice chrome sized from their text, group-title margins, the CSD title bar's zone balance after the centered title's metrics move, `Switch`'s `apply_ui_font` state text, the `text/**` engine canvases and `ComboBox`'s field/gear metrics), 13 with `frozenset({AXIS_SCALE})` where it is pure design-px (`scaled_px`) geometry (spinner square, slider/switch/line-edit/spinbox chrome, flyout focus-ring insets, icon-action/list-panel/sidebar/indexed-flyout/dialog-shell/console/CSD sizes, the console's system-`FixedFont` × factor). Handlers that took the raw `_factor` are payload-agnostic now (`*_args`), so the bus's axes `frozenset` is accepted and the existing direct callers keep working; `ComboBox.on_scale_changed` forwards a no-op factor to `Button.on_scale_changed` (the base derives from the live `UiScale` and reads no payload), and `CustomTitleBar._on_metrics_changed` adapts the bus payload to the mixin's raw-signal `on_scale_changed` (that handler lives in the not-owned `zones.py`). `windows/window_chrome.py` drops its bespoke `QMetaObject`/`_csd_scale_connection` teardown for the bus's auto-drop on a dead widget. `axes=` is passed as a real `frozenset` (the declared `frozenset[str] | None`), and `ui/widgets/text/engine/{canvas,document_canvas}.py` keep a noqa'd `UiScale` import because their `text_view`/`help_document` compatibility shims re-export it. The 5 remaining exemptions are recorded with reasons: `managers/theme_manager.py` (re-scales host QSS px literals; a `QObject` singleton, never a `QWidget`), `managers/ui_font.py` (its raw connects ARE the producer-side live-resync hook), `widgets/buttons/button.py` (connects theme+font+scale with bespoke destroyed-hook teardown for the stale-slot crash class), and the timeline `widget.py`/`interaction.py` pair (their raw connect/disconnect is a close→reshow transient unbind/rebind that the bus's per-`(widget, slot)` idempotency cache cannot express). Tests: `tests/test_ui_metrics_contract.py` (the 25-entry `MIGRATED_OFFENDERS` ratchet — a migrated file must never re-enter `EXEMPTIONS` — plus the 5-entry exemption list assertion) and new `tests/test_ui_metrics_sweep.py` (`TopTabBar` re-stamps its cached tab width from the larger font's size hint; falsified — with the bus wiring removed the width stays at its construction-time value). Two existing tests that asserted straight after `set_factor` / `set_family` now flush the coalesced bus (`tests/test_paint_periphery.py`, `tests/test_ui_font.py`).

### Fixed

- **`AdaptiveTabStrip`: the tab width no longer shrinks after a live UI-scale change, and `CloseButtonPolicy.ALL` always keeps the `×`** — the width reserved for the close slot in every tab (`_AdaptiveTabBar._tab_width`) was a **scaled snapshot** taken in the bar's constructor (`scaled_px(close_button_size)`) and never refreshed, while the slots themselves rescale through `_CloseButtonSlot.resync` on every factor change: after any post-construction `UiScale.set_factor` the tabs came out `new − old` px too narrow for the chrome they had to hold (measured offscreen at factor 1.5: `tabRect(0).width()` 236 against the 250 the real 42 px slot implies; the owner's live report was the single workspace tab changing width between states). The reservation is now **derived**: `_close_reserve_width(index)` returns the placed slot's own width, else the design size resolved through `scaled_px` at use time — both branches agree for the toolkit's slots, so selecting a tab still never changes any tab's width, but the number can no longer be stale. `_AdaptiveTabBar.__init__` takes `close_button_design_width` (design px) and the bar re-asserts `apply_ui_font(self)` at the top of `_on_metrics_changed`, so the width recomputed there is measured from the settled UI face (a scale-only metrics pass over a lagging bar font produced a 258-vs-265 px tab). `AdaptiveTabStrip.refresh_close_buttons` now ends with `_AdaptiveTabBar.refresh_close_slot_geometry()` — the (re)built slots are explicitly shown, re-placed and the rects re-fitted in the same pass — and `_should_show_close_button` treats `ALL` as authoritative, so a single tab built with `single_tab_closable=False` keeps its `×` (that combination previously dropped the slot outright: the owner's no-`×` state). Tests: new `tests/test_adaptive_tab_strip_state_stability.py` (5; run against the pre-fix source — `git archive 1ca5a59` — 3 of them are red: 236 vs 250 at factor 1.5, the dropped single-tab slot, 258 vs 265 for the lagging-font pass).

- **A closing flyout no longer drops keyboard focus onto the window's first tab-order widget.** While the hide fade ran, `FlyoutFadeController.sync_container_visibility` hid every direct child of the flyout so only the pre-rendered snapshot showed; when the keyboard focus sat on a row inside that child, Qt fell back to the window's first focusable (the CSD menu trigger) for the rest of the fade — the focus ring visibly hopped to the title bar and only returned when `_finish_hide` restored the anchor. Measured live 2026-10-18 through the app's focus trace: the focusChanged stack pointed at `on_fade_value_changed → set_opacity → sync_container_visibility → child.setHidden(True)` (the stale `_finish_hide` comment blamed `_unregister_nav_section`; corrected). The hide-fade step now hands focus to the flyout itself first (visible, `StrongFocus`), and `_finish_hide` still restores the anchor; fade-in is untouched (gated on `hide_fade_in_progress`). Tests: `tests/test_flyout_fade_focus_hop.py` (falsified against the pre-change `sync_container_visibility`). The flyout also *mutes its own ring* while it hides (`drop_focus_ring()`, `widget.py`) — the handed-off container must not wrap the whole panel in a ring beside the selected row's (reported 2026-10-18 as a follow-up).

- **Tooltips: the hand-over is instant, but a closed tooltip repays the full delay.** Hovering a target showed the bubble after Qt's hover wake-up plus `PathTooltip`'s 500 ms; moving a couple of pixels onto the neighbouring button hid the bubble (`Leave`) and the next `ToolTip` event re-paid the whole delay, so switching targets took the full cycle again. `PathTooltip` keeps a short "session" once a tooltip is **shown** (`_session_until_ms`, `SESSION_IDLE_MS = 1500`, `session_active()`), and `show_tooltip(...)` shows the next bubble **instantly** (delay 0) while the session is live. Qt's `dispatchEnterLeave` sends `Leave(old)` and then `Enter(new)` synchronously in one mouse-move dispatch, so a `Leave` now only *schedules* the close (`defer_hide_tooltip()`, one event-loop tick) and both filters use it: a same-dispatch `Enter` still finds the tooltip up and hands over instantly, while a `Leave` with no following `Enter` completes the close on the next tick. A **completed close ends the session** — `hide_tooltip()` clears `_session_until_ms` instead of extending it. Previously the session lingered 1500 ms after a close, so after the first tooltip every later tooltip in that window opened instantly even once the bubble had gone; the next hover now pays the configured show delay (500 ms) again. Tests: `tests/test_tooltip_session.py` (8; the close-repays / deferred-close cases fail against the pre-change base).

- **The first arrow press after a mouse click now moves focus (reveal-only consumption removed).** A click kills the visible focus ring (`MouseButtonPress` handling), so the next arrow press re-anchors the ring onto the widget nearest the click point. That press was then consumed as "reveal-only": it revealed the ring and did nothing else, so moving one step after *any* click took two presses — and when the realign target was a section's own container (the gallery's empty-zone click anchors on its scroll area, which `GalleryGridNavSection.owns()` claims) the revealed ring was not on a navigable item at all, so the first press looked completely dead. `ClickRealignCoordinator`'s docstring has always described the intended behaviour — the press "re-anchors the ring ... then lets that same key press navigate from there" — and the manager now does exactly that: after realigning, execution falls through to the section dispatch and steps from the freshly-anchored widget. Sections that decline still fall through to the neighbour handoff and the `yield_to_native` trial-dispatch (which keeps forwarding the event to the newly-focused widget when a realign happened). Tests: new `tests/test_nav_click_realign_single_press.py` (2; both fail against the pre-change manager with `one arrow press after a click did not move focus (reveal-only regression)`).

- **`ToolbarRowsSection` no longer traps focus in a text field.** Left/Right on a `QLineEdit`/`CustomLineEdit` were accepted by the field (caret movement) and the section returned "consumed" without moving — so focus could never leave the field at the row edge ("[nav] consumed (no movement)", e.g. the gallery filter edit). The section now yields Left/Right when the caret is at that key's edge and there is no selection (new `_caret_at_boundary` duck-typed on `cursorPosition()/text()/hasSelectedText()`), so the row is exited; mid-text it still lets the field move the caret.

### Added

- **Modal navigation sections — keys and focus never leave an overlay** — a `NavigationSection` may declare an optional `modal` property (`getattr(spec, "modal", False)`, the same read pattern as `extra_keys`; missing attribute = non-modal). While such a section is registered and its (QWidget) owner is visible, `NavigationManager` makes it the **ceiling**: arrow keys, the section's `extra_keys` and Tab/Backtab are routed into it; a declined arrow at its edge is **consumed** (no neighbour handoff, no native bubble to the tab behind the veil); Tab/Backtab cycle the owner's focus chain (`isVisible()`/`isEnabled()`/`TabFocus`, wrap at the ends, `focus_first` when the ring is empty) and are always consumed; a foreign widget stealing focus is pulled back on the next event-loop turn (`_reclaim_modal_focus`, reset on owner unregister). Sections registered *after* the modal section sit above it and keep normal behaviour (flyouts opened from inside the overlay), sections registered before it are behind the veil; hiding or unregistering the owner turns modality off. No public API added; behaviour with no modal section is byte-identical. Docs: `docs/dev/NAVIGATION.md` §4. Tests: `tests/test_nav_modal_section.py` (11, falsified against the pre-change base — 9 fail; the other 2 are non-modal regression guards).

- **Theme-refresh primitives: `lazy_icon`, `ThemedContainer`, `refresh_theme_subtree`** — (1) `sli_ui_toolkit.icons.lazy_icon(provider: Callable[[], QIcon])` returns an opaque lazy handle, and `resolve_icon(icon)` now resolves lazy handles and zero-arg callables at paint time so icons track the active theme without re-assigning handles; `normalized_icon_pixmap` resolves through `resolve_icon` before keying on `icon.cacheKey()`, preserving pixmap cache hits across paints when `provider` returns a cached `QIcon` per theme. (2) `ThemedContainer(ThemedWidget)` (`sli_ui_toolkit.ui.widgets` / `sli_ui_toolkit.widgets`) formalizes chrome-first theme refresh as `on_theme_derived()` → `on_theme_children()` → `super().on_theme_changed()` without altering existing `ThemedWidget` subclasses. (3) `refresh_theme_subtree(root)` (`sli_ui_toolkit.ui.managers.theme_manager`, re-exported from `sli_ui_toolkit.ui.widgets`, `sli_ui_toolkit.widgets`, `sli_ui_toolkit.theme`, and `sli_ui_toolkit.managers`) walks `root` and its `QWidget` descendants in pre-order (parents before children), calling `on_theme_changed()` once when present else `update()`. Docs: `API_CATALOG.md`. Tests: `tests/test_icons.py` (+3), `tests/test_theme.py` (+2), `tests/test_public_api.py` (+1).

- **i18n: subtree-scoped translators + declarative keys (`install_translator` / `bind_translator` / `translator_for`)** — a widget subtree can be bound once to a `Translator = Callable[[str, str], str]` (`(key, language) -> text`, the same convention as `translatable_*`). `install_translator(root, tr_func, *, events=None, defer_when_hidden=False)` binds `root` and every current **and future** descendant that implements the duck-typed protocol `set_translator(tr_func, *, defer_when_hidden=False)` / `retranslate(lang)`; future children are picked up through a dedicated `QEvent.Type.ChildAdded` event-filter object (never `installEventFilter(self)`), a **single** `language_changed` subscription fans `retranslate(lang)` to the whole subtree (immediate apply on install, mirroring `_bind_widget`), the subscription auto-detaches on `root.destroyed`, and dead C++ children are dropped defensively. `events=` selects a tab-owned bus for per-subtree isolation (default: the global singleton); `bind_translator` binds a single widget; `translator_for(widget)` returns the nearest bound ``parent()`` ancestor, else the global `tr`. Declarative keys (key wins over the literal on every retranslate; a miss paints the **key**, never silent English): `Button(text_key=..., badge_key=...)` + `setTextKey`/`setBadgeKey`, `ButtonRow.text_key`, `ButtonRegion.text_key`/`badge_key`, `Label`/`Text` `text_key`, and `ContextMenuAction.text_key`/`tooltip_key`. `Button.retranslate` updates the **actual rows** the painter reads (so it fixes the silent no-op where `translatable_text` called `setText` on a rows button); the context menu retains its entries and re-runs `refresh_metrics` + `_relayout_widths`. `translatable_*` is unchanged as the escape hatch. `configure_i18n(translator=..., language_provider=...)` is now **wired** (custom backend + current-language source) instead of silently ignored. Docs: `API_CATALOG.md` §i18n, `BUTTON_API.md`, `CONFIGURATION.md` §4. Tests: new `tests/test_i18n_translator.py` + `tests/test_i18n.py` extensions (the rows/badge/menu/child-added/isolation cases fail against the pre-change base — no such symbols — and the `configure_i18n` wiring tests assert against the previously-ignored params).

### Added

- **`Button.setHoverHost(host)` — composite-card hover for an embedded action button** — `HoverCoordinator` lit a widget only from its own area (`top_widget is widget or widget.isAncestorOf(top_widget)`), so an action button nested in a card (e.g. the clean-review filmstrip cell's Restore) did not light when the pointer hovered the card. A button can now declare a `hover_host`: the coordinator treats the host's area as the button's area (skipping the strict region hit-test, since the pointer is outside the button's own regions), and `setHoverActive(True)` lights the primary region when the live cursor is inside the host. `None` (default) keeps the historic per-widget hover. Tests: `tests/test_hover_host.py` (2, falsified against the pre-change base).

### Fixed

- **Context-menu submenu filter tolerates non-widget objects (`QWindow`)** — the menu installs an app-wide event filter while open (`base_flyout/lifecycle.py` `_grab_focus`), so `eventFilter` also receives the `QWindow` backing a popup/native surface and its forwarded MouseMove/HoverMove. `_is_forwarded_obj` called `submenu.isAncestorOf(obj)`, whose only overload takes a `QWidget`, raising an uncaught `TypeError` (`'PySide6.QtWidgets.QWidget.isAncestorOf' called with wrong argument types: (QWindow)`) — only `RuntimeError` was caught. `_is_forwarded_obj` (and `_branch_contains`) now gate on `isinstance(obj, QWidget)` first, mirroring `flyout_manager._is_inside_active_flyout`; behavior for widget objects is unchanged. Tests: new `tests/test_context_menu_forward_guard.py` (3 of 4 fail against the pre-change base with the exact `TypeError`).

### Fixed

- **Help TOC teardown hides before unparenting** — `_dispose_toc` detached the old TOC frame with `setParent(None)` while still visible, which spawns a transient toplevel and flashes the global busy cursor (the app's `test_no_visible_orphan_setparent` contract). It now calls `hide()` first, same as the hub's hover-widget teardown.

### Fixed

- **Help TOC keeps its frame after navigation** — `HelpDocumentView.set_blocks` tore the previous TOC frame down with `deleteLater` (deferred) and `_repolish` styled `findChild("HelpDocumentToc")`, which still returned the stale frame — so the freshly built TOC rendered border-less as soon as you followed a `help://` link to another page. The live frame is now tracked explicitly (`self._toc`), detached from the layout before `deleteLater`, and `_repolish` styles that frame. Tests: `tests/test_help_document_view.py` (`test_toc_stays_styled_after_page_navigation`, falsified against the pre-change base).

### Added

- **`ButtonRow` word wrap (`wrap=True`) for long card text** — an opt-in `ButtonRow.wrap` field breaks an overflowing row across multiple lines at word boundaries within the region's available width instead of clipping/overflowing on one line. The row reserves the extra line height (`RowsContent.measure_height`) and `Button` exposes it through `hasHeightForWidth()`/`heightForWidth()` plus `sizeHint`/`minimumSizeHint`; a fixed design height (`size=(0, 76)`) is relaxed into a floor so a host layout can stretch the card past it. Wrapping rows lay out at their natural stacked heights (so `ratio` is ignored while wrapping); `marquee` still wins over `wrap` on an overflowing row. `wrap=False` (default) keeps the historic single-line rendering and metrics exactly. Reuses the toolkit plain-text layout engine (`build_layout`, the `Text` widget's word-break path) rather than re-implementing word breaking. Docs: `BUTTON_API.md` § ButtonRow API. Tests: `tests/test_button_row_wrap.py` (7; the wrap/height/paint assertions fail against the pre-change base).
### Changed

- **Inline markdown is a hand-written scanner; the `kbd` wordlist is gone** — `parse_inline` no longer lexes with the single alternation regex `_INLINE_TOKEN_RE` (which could not nest, so `` **`Shift`+wheel** `` rendered with literal backticks and `[^*]+` broke on interior `*`) nor guesses keyboard keys via `_looks_like_shortcut` / `InlineKind.KBD` (unbounded — `F13`, `Page Up`, non-Latin keys — and wrong on `a+b`; markdown has no `kbd` concept). It now scans characters: `**…**` and `*…*` parse their bodies recursively so nested spans work (`` **a `b` c** `` → bold text + bold code + bold text), ``` `…` ``` scans to the next backtick and never nests, `[label](href)` links, and an unterminated delimiter stays literal — never raises, always advances. New `InlineSpan.bold` carries the inherited weight through `CharStyle` (selection index + layout) so nested code/link keep their own look and pick up bold; the layout bolds on `style.bold or kind == BOLD` and styles links by `href`. Inline code is always `InlineKind.CODE`; `spans_to_plain` / `blocks_to_plain_text` still strip markers. Tests: new `tests/test_markdown_inline.py` (9, all falsified against the pre-change base); the KBD cases in `tests/test_help_document_blocks.py` / `tests/test_help_document_view.py` are retargeted to code. Docs: `API_CATALOG.md` (`HelpDocumentView` no longer advertises kbd).

### Fixed

- **Document hit-test is glyph-strict (one fix, both viewers)** — `hit_test_text_offset` resolved clicks anywhere in a fragment's full block width and clamped to the nearest offset, so empty space past the glyphs showed the I-beam and selected/caret-jumped to line end. It now misses past the last glyph (whitespace counts by advance), on empty lines, and below content — shared by `HelpDocumentBodyCanvas` and TextView document mode, hence identical everywhere. Tests: wrapped-lines anchor moved to the glyph end + new empty-space test (falsified pre-fix).

### Fixed

- **Submit-preset Tab-adopt runs in the event filter (before focus travel)** — `QWidget.event()` diverts Tab to focus navigation before `keyPressEvent` ever runs, so in-flyout fields lost Tab to the next button and the placeholder was never adopted live. `_EditableTextKeyFilter` (already installed on every `CustomLineEdit`) now adopts Tab itself when the submit preset is on and the field is empty (Ctrl/Alt/Meta held keeps native travel); the `keyPressEvent` branch stays as the direct-invocation path. No behavior change for plain fields. Tests: `tests/test_custom_line_edit.py` (+1 filter-level, falsified pre-fix).
- **TextView caret blinks; empty click clears instead of jumping to nearest** — the code-mode caret was a solid non-blinking band (now a 500 ms blink while focused + editing, `CustomLineEdit` parity). Clicking past the glyphs (or below the last line) clears the selection and drops the caret instead of clamping it to the nearest position; any text click / edit / arrow move re-places it. Hover cursor follows the same glyph hit-test (I-beam only where characters stand — whitespace counts by width — Arrow elsewhere), so empty space no longer promises selectable text. Tests: `tests/test_text_view.py` (+3, falsified pre-fix; one legacy triple-click expectation moved from past-end to line-end).

### Added

- **`Text` engine-mode API (P2b): context menu, external links, `scroll_to_text`, `set_blocks`, `resolve_asset` setter, `selectionChanged`, typography** — (1) `textContextMenuRequested(QPoint)` fires on right-click in every mode (global position). (2) `open_external_links` (default `True`; ctor kwarg, `TextConfig` field, `set_open_external_links`) opens `http(s)` links from the engine via `QDesktopServices`; `linkActivated` is emitted either way. (3) `scroll_to_text(query) -> int | None` (document mode) selects the first normalized match and returns its content y, not a widget. (4) `set_blocks(blocks)` (document mode) takes parsed help blocks; `TextCanvas.set_document` now delegates to the new `TextCanvas.set_blocks`. (5) `resolve_asset` is set through a new `set_resolve_asset(fn)` setter that re-lays out the document; the ctor kwarg is unchanged. (6) `selectionChanged` is forwarded from the engine in both code and document modes and fires only when the effective selection value changes. (7) Typography in engine modes: code mode honors `pixel_size`/`bold`/`italic`/`underline`/`strike_out`/`family` and the variant's `pixel_size`/`bold`; document mode honors `pixel_size`/`family` for body text (layout builder takes optional body overrides, defaults unchanged); `color`/`color_token` set the code-mode base color. (8) Content-height changes in engine modes re-layout the host: `TextCanvas.contentHeightChanged` drives `Text.setMinimumHeight` + `updateGeometry`, so a `QScrollArea` range follows the content. Tests: new `tests/test_text_engine_api.py` (25; 23 fail against the pre-change base commit, the other 2 are parity/regression guards). Docs: `LABELS_API.md` (Text section). Full suite green (1454), mypy clean on touched files.
- **`Text` P2 checkpoint: hover glyph rule in plain mode, engine modes hosted, inspector descriptors** — (1) plain-mode `selectable` text now follows the strict glyph-hit rule the document/code engines use: I-beam only over characters, Arrow over the empty widget space (closes the P1-known gap; `plain.hit_glyph`). (2) `Text(mode="document")` and `Text(mode="code", editable=...)` are live: the existing painted `TextCanvas` engine is hosted as the single child filling the widget, with `set_markdown`/`anchor_y`/`selected_markdown` (document), `set_editing`/`is_editing`/`set_line_number_start` (code), `selectedText`/`hasSelectedText`/`selectAll`/`select_all_text`/`clear_selection`/`selected_plain_text` (both), and `textChanged`/`linkActivated`/`imageActivated` forwarded from the engine. `resolve_asset` and `editable` are new constructor kwargs (also on `TextConfig`). The engine is **hosted, not yet re-homed**: its code still lives under `composite/text_view/` and `TextView`/`HelpDocumentView` are unchanged (see the PR description for the gap list). (3) `Text.inspect_spec` / `Text.widget_descriptor` (family `Text`). Tests: `tests/test_text.py` (+12: hover glyph rule, descriptor, document pixel parity vs bare `TextCanvas`, document selection/`set_markdown`/signal forwarding, code edit switch + selection, child fills widget, mode guards; the P2-stub test became an engine-mode construction test). `TextView`, `HelpDocumentView`, and the old suites are unmodified and green.
- **`Text` painted display widget (P1: plain mode at `Label` parity)** — new `sli_ui_toolkit.widgets.Text(QWidget)` + frozen `TextConfig` (with `to_kwargs()`, mirroring `ButtonConfig`), the first step of the text unification plan (`docs/text-unification-plan`). `mode="plain"` paints through `QStyle.drawItemText` (the call `QLabel` makes), so unselected text is pixel-identical to `Label`, and sizes/`heightForWidth`/`minimumSizeHint` match `Label` (the wrapped `sizeHint` differs by design: single-line width instead of `QLabel`'s area-balanced hint). Same typography surface and variant registry as `Label` (`variant`/`family`/`pixel_size`/`bold`/`italic`/`underline`/`strike_out`/`color`/`color_token`/`alignment`/`elide`/`marquee`/`minimum_width`/`expanding`/`word_wrap`), plus `selectable` with mouse drag, double-click word, `Ctrl+A`/`Ctrl+C`, Shift+arrow/Home/End, the Copy / Select-all context menu, and `selectionChanged`. `mode="document"` and `mode="code"` raise `NotImplementedError` (P2). No caller migration; `Label`, `TextView` and `help_document` are unchanged. Docs: `LABELS_API.md` (Text section), `API_CATALOG.md`. Tests: new `tests/test_text.py` (39: pixel parity vs `Label` across 8 cases, metric parity, config/kwargs equivalence, variant registry sharing, P2 stubs, elide/marquee, selection/copy/context-menu, with falsified mutations checked by hand).
- **`CustomLineEdit` submit preset + wheel scrolling** — one standard single-shot submit-field contract for hosts (opt-in `CustomLineEdit(submit_preset=True)` / `setSubmitPreset(True)`, off by default so plain fields keep exact `QLineEdit` behavior): `Tab` on an empty field accepts the placeholder as starting text (cursor at the end, no selection); `Enter` emits the new `submitted(str)` signal with `text().strip()` (or the placeholder when empty) and rewinds the view and caret to the start (previously the view stayed pinned to the end after submit). The wheel now scrolls an overflowed line horizontally (`QLineEdit` parity); when the text fits the event is ignored so an enclosing scroller can take it. Docs: `INPUTS_API.md`. Tests: `tests/test_custom_line_edit.py` (+8: wheel pan + bubble, Tab-accept on empty/non-empty, submit typed/placeholder-fallback, rewind-to-start, preset-off parity); full suite green, mypy clean.

### Changed

- **`Text` engine motion (P2c): document/code engines moved under `ui/widgets/text/engine/`; old paths are thin delegates** — the painted engine modules (`composite/text_view/*` incl. `layout/*`, and `composite/help_document/canvas.py`) moved via `git mv` to `text/engine/` (`document_canvas.py` for the help-document body). The engine classes are now `TextCanvasCore` and `HelpDocumentBodyCore`; `Text` hosts `TextCanvasCore` directly. The old modules are delegate shims re-exporting every top-level name, and the old `TextCanvas` / `HelpDocumentBodyCanvas` names are thin subclasses of the cores (same `__name__`, same behavior). `TextView`, `HelpDocumentView`, and all callers are unchanged (zero caller churn, nothing deleted). No behavior change; old suites green unmodified. Tests: new `tests/test_text_engine_motion.py` (7: delegate identity, shared function objects, old-vs-core pixel parity, `Text` code/document hosting the core, falsification of the wrapper). Known gaps (lightbox relocation, TOC decision, public selection names) remain as recorded in the PR description.
- **`AdaptiveTabStrip` owns its `ButtonPosition` enum (no `QTabBar` dependency)** — the tab-button slot no longer references `QTabBar.ButtonPosition`: a toolkit `ButtonPosition(IntEnum)` (same values, exported from `adaptive_tab_strip`) is used internally, and `tabButton`/`setTabButton` normalize any host enum or int via its `.value`, so existing callers (including hosts passing `QTabBar.ButtonPosition.RightSide`) keep working unchanged. The toolkit source no longer imports `QTabBar`. Also documented the `TextView` canvas transparency-pin stylesheet as plumbing (not visual styling). No behavior change; full suite + mypy clean.

- **Comment hygiene: drop migration meta-mentions of replaced Qt widgets (no behavior change)** — docstrings/comments that narrated the removal/rebase of stock Qt widgets were rewritten to describe current behaviour only. Text widgets: `custom_line_edit`, `console_view`, `log_console_widget`, `process_console_widget`, `time_line_edit`, `marquee_state`, `text_view/{events,canvas}`, `editable_text`, `INPUTS_API.md`. Controls: `checkbox`/`radio` (`QCheckBox`/`QRadioButton` rebase narration), `progress_bar` (`QProgressBar`), `custom_group_widget` (`ButtonGroup`), `label_context_menu` (`QLabel` menu). API-parity descriptors: `radio`/`top_tab_bar`/`adaptive_tab_strip`/`sidebar_nav_list`/`context_menu`/`buttons`/`base_flyout`/`navigation_*` — `QButtonGroup`/`QRadioButton`/`QTabBar`/`QTabWidget`/`QListWidgetItem`/`QMenu`/`QAbstractButton` "-parity/-ish/-compatible" phrasing made widget-agnostic. No code/API change; full suite + mypy unchanged.

- **`MarkdownHelpDialog` renders on the painted `TextView` (dropped `QTextBrowser` + the `markdown`-to-HTML pipeline)** — each section is now set via `TextView.set_markdown(...)` (document mode: painted blocks, headings, inline spans, links, images) instead of `markdown` → HTML into a `QTextBrowser`; the HTML post-processing that only fed the browser (`ensure_heading_ids`, `build_page_toc`, `strip_html_tags`, the `.help-toc`/code/kbd CSS wrapper) is gone. Markdown headings are auto-anchored (`inject_heading_anchors`, same slug/dedupe rules as before) and the page TOC is emitted as markdown for pages with ≥2 `###` headings. New additive `TextView.scroll_to_anchor(anchor) -> bool` + `TextView.anchor_y(anchor) -> int | None` (backed by `TextCanvas.anchor_y`, reusing the layout's collected heading anchors) reproduce the old `anchor_vertical_offset`; internal `#anchor` links scroll the current page, external `http(s)` links open via `QDesktopServices`, and `help://slug#anchor` cross-section navigation is kept. Optional `resolve_asset` resolver (auto-set to the directory root by `set_sections_from_directory`) feeds inline images. Public `MarkdownHelpDialog` / `MarkdownHelpSection` API unchanged. Tests: new `tests/test_markdown_help_painted.py` (7); full suite green, mypy clean.

- **Painted `PreviewPanel` text surface (`TextView` instead of `QTextEdit`)** — `PreviewPanel`'s read/edit text area is now the painted `TextView`/`TextCanvas` (same painter pipeline as the rest of the toolkit), not `NonPropagatingTextEdit(QTextEdit)`; the panel keeps its public surface (`__init__(title, *, show_actions, edit_text, save_text, revert_text, parent)`, `set_title`, `set_action_texts`, `set_actions_visible`, `set_edit_mode`, and the edit/save/revert `Button`s) and gains `set_text(str)` / `text() -> str`. `set_edit_mode(True/False)` now drives `TextView.enter_edit_mode()`/`exit_edit_mode()` (`.is_editing()`), the widget name changed from `previewTextEdit` to `previewTextView`, and the old per-widget QSS text-surface block is gone (the panel group/surface theming is unchanged; the painted view needs no QSS). The legacy `NonPropagatingTextEdit` name is kept for import compatibility but now subclasses the painted `TextView`, consuming the wheel at the scroll edges so it never bubbles to the host. Tests: new `tests/test_preview_panel.py` (3: text round-trip + painted-type/object-name, edit-mode toggle + canvas mutation + button states, wheel consumed at top/bottom and vertical scroll away from the edges with no host propagation); full suite green, mypy clean.
- **Painted `ConsoleView`; `LogConsoleWidget` + `ProcessConsoleWidget` migrated off `QTextEdit`** — new `composite.console_view.ConsoleView(QWidget)` renders a read-only console through the toolkit painter pipeline (no stock text widget, no QSS): a `ConsoleLine(text, color, bold, italic)` model with `set_max_lines` trimming (oldest first), word-wrap to the viewport width, per-line color/emphasis, a vertical `MinimalistScrollBar`, follow-the-tail auto-scroll (only when already at bottom, else the scroll position is kept), mouse selection, `Ctrl+C`/`Ctrl+A` (and `Ctrl+Ins` copy), plus `lines()`/`text()`/`append()`/`clear()`/`set_font()`/`scroll_to_bottom()`/`is_at_bottom()`/`line_index_at(y)`/`visual_lines()` (wrapped rows bound to their source line). Both consoles keep their public API (`LogConsoleEntry`, `append_*`/`set_entries`/`entries`/`history`/`full_text`/`set_output_font`; `ProcessConsoleWidget` signals + input row); their `output` attribute is now a `ConsoleView` (not a `QTextEdit`). Level colors resolve through the theme tokens and recolor on `theme_changed`. Tests: new `tests/test_console_view.py` (9: per-visual-line content identity, wrap fidelity + width, `line_index_at`, trimming, tail-follow, scrolled-up position keep, `Ctrl+C`/`Ctrl+A`, `set_lines` scroll preservation); `tests/test_process_console_scale.py` still green; full suite green, mypy clean.

### Fixed

- **`FlyoutManager` sequences show cycles: a flyout waits for a closing one** — the popup's real `QWidget.hide()` lands only when its fade-out animation finishes, so a flyout opened while another was still closing used to start its show animation on top of the outgoing fade (the "two flyouts conflict/overlap" report). New opt-in `BaseFlyout.wait_for_close_before_show` (default `False`; transient popups like context menus keep replacing instantly): when set and another flyout is still mid hide-fade, `FlyoutManager.request_show` returns `False`, `show_aligned` bails, and the manager replays the show (via the stored full `_last_show_kwargs`) once the closing flyout emits the new additive `BaseFlyout.hidden` signal (or a popup menu's `aboutToHide`) — one cycle closes before the next opens. Detection covers both fade pipelines: in-window `_fade.hide_fade_in_progress` and a popup-surface context menu's `_popup_fade_in_progress` (so an Ask-AI flyout waits for a context menu dismissed on action-click, before its handler ran). The deferral is evaluated after the manager's dismiss pass, so a sibling it just started closing is awaited too. Tests: `tests/test_flyout_fade.py` (+3: waits-for-close then opens; no-opt-in replaces immediately; popup-menu close detection).

- **`CustomLineEdit`: single-letter window shortcuts ate typing; caret/selection spanned the whole field** — the painted field now claims `ShortcutOverride` for plain printable keys, so a window-level shortcut bound to e.g. `e` no longer consumes the key while the field is focused (`_is_typing_key` also masked `GroupSwitchModifier` for layout-switch keys). The caret and selection highlight are drawn as a text-height band (`_text_line_rect`, font `ascent+descent`, vertically centred) instead of the full 32px content rect. Tests: `tests/test_custom_line_edit.py` +2 (`test_shortcut_override_claims_plain_letters` — falsified pre-fix; `test_caret_and_selection_use_text_line_height`); full suite green, mypy clean.

- **Scrollbar policy: `OverlayScrollArea` native bars re-hidden at polish (`overlay-native-hidden` rule)** — call-site migrations to `OverlayScrollArea` kept stock-era `AsNeeded` overrides, showing a native scrollbar next to the custom one (gallery Quick Look sidebar). The proxy now re-asserts `AlwaysOff` on both native bars of every overlay area; the mirrored bars themselves are untouched. Tests: +1 in `tests/test_scrollbar_policy.py`.
- **`OverlayScrollArea` sync re-entrancy guard + spin breaker** — layout feedback (margins → viewport → ranges) can re-emit `rangeChanged` mid-sync, and each nested pass costs dozens of frames, so ~25 nested passes exhaust the stack (production `RecursionError`, tripped inside an env-flag lookup). Sync passes are now cut at depth ≥ 1 with one deferred re-sync queued (the sync is idempotent); a 256-consecutive-cut budget stops re-arming so a never-settling driver degrades to external-event re-syncs instead of pinning the 0ms timer. Cuts are logged through the existing `sdbg` stream. Tests: +3 in `tests/test_scrollbar_policy.py` (cut + defer, Qt-delivered nesting cut exactly once, breaker stops re-arm); mypy clean.

### Added

- **Per-member / per-region geometry accessors** — `ButtonFamily.memberRectsMappedTo(widget)` returns `{button: QRect}` for every *visible* member in another widget's local coordinates, and `memberRectMappedTo(button, widget)` is the single-member form (null when not a visible member) — the same walk `unionRect()` already does, so a host that lays one overlay per member (e.g. a badge pinned past a member's edge) stops mapping buttons by hand. `Button.region_rects()` / `region_rect(region_id)` expose live per-region geometry in the button's own coordinates (recomputed on demand) instead of the private `_region_rects`; `RegionHandle.rect` is the read-only single-region form (`button.region("thumb").rect`). Docs: `BUTTON_API.md` § "Linking separate buttons", `API_CATALOG.md`. Tests: `tests/test_button_family.py` (+1), `tests/test_button_regions.py` (+1); mypy clean.
- **Project-wide widget substitution: `WidgetPolicyProxyStyle` + `install_scrollbar_policy()` + `register_widget_policy()` (`ui.widgets.helpers.scrollbar_policy`, exported from `sli_ui_toolkit.widgets`)** — enforcement half for opt-in construction: a `QProxyStyle` that sees every widget at polish time and runs the registered substitution handlers (once per widget, all calls guarded). Built-in rule swaps every `QAbstractScrollArea`'s native bars for `MinimalistScrollBar` except `OverlayScrollArea` (its hidden mirrored native bars keep the mirror wiring) and areas already carrying minimalist bars. `install_scrollbar_policy()` is idempotent, uses a null-base proxy (dynamic delegation — steals no ownership; Qt deletes the previous style inside `setStyle`, so there is deliberately no uninstall), and sweeps pre-existing widgets; host apps call it once at startup. `register_widget_policy(cls, handler)` extends the same mechanism to future widget kinds (late registrations sweep live widgets). Proven during development: `QProxyStyle(base)` takes ownership of `base` (wrapping `app.style()` in a short-lived proxy segfaults on GC) and `setStyle` deletes the replaced style. Tests: new `tests/test_scrollbar_policy.py` (6: public surface, stock swap, overlay skip, idempotence, registry extension, install end-to-end); mypy clean.

### Added

- **Behavioral button family: `ButtonFamily` (`ui.widgets.buttons.family`, exported from `sli_ui_toolkit.widgets` and `...buttons`)** — a non-visual `QObject` linking separate `Button` widgets into one behavioral family ("one button, but different buttons", e.g. rank pills over gallery thumbnails): members keep their own visuals/paint/clicks, the family only mirrors state per its policies and reports combined area. Policies (independent, combinable): `shared_hover` (pointer inside any member lights `HOVERED` on all non-disabled regions; 50 ms poll backstop while hovered; transparent while off) and `exclusive` (checking one member unchecks the rest, any toggle `Button`). Combined geometry: `unionRect()` / `unionRectMappedTo()` / `center()` plus `geometryChanged` on member move/resize/show/hide. See `BUTTON_API.md` § "Linking separate buttons". Tests: new `tests/test_button_family.py`.
- **Synchronous layout settle: `ui.layout_settle.settle_layout(widget, *children)`** — one shared helper for the self-sizing-widget transient class (own size derived from a child while a `QLayout` places the children): refreshes each child's hint via `updateGeometry()` (skips `None`), then `layout().invalidate()` + `activate()` in the same call, so the widget and its contents agree in the first painted frame. No-op on layout-less widgets. App-side reference call site (`RecentProjectsPanel.settle_shelf_layout_now`) delegates to it; lane fixes must call it, never re-implement it. Tests: new `tests/ui/test_layout_settle.py` (5: grow/shrink same-call agreement, misattribution without hint refresh, None-skip, layout-less no-op).
- **Picker-anchor sizing: `Button.set_width_texts()` + `SimpleOptionsFlyout.content_width_hint()`** — a `Button` anchoring an options flyout can now size to the longest option instead of the current text: pass every option label (with any persistent affix, e.g. `" ▾"`) via the new `width_texts` constructor kwarg or `set_width_texts()` (`width_texts()` reads back, `None`/empty disables). `sizeHint`/`minimumSizeHint` take the max of the current content and the candidates measured with the paint font via `measure_text_width` (no clipping, no fixed width — live `UiScale` changes re-derive through the existing `updateGeometry` path). Recipe: `Button(text=..., width_texts=[...], size=(0, h))` + `show_below(button, match_card_width=True)` — the layout fits the button, the flyout card lands exactly on it (see `BUTTON_API.md` + `FLYOUT_SYSTEM.md`). `content_width_hint()` exposes the flyout's natural opaque-card width for the current rows (post-`populate`/`set_rows`); `geometry.update_size` now derives from it (no behavior change). Tests: new `tests/test_button_width_texts.py`.

- **`SimpleOptionsFlyout.show_below(..., width_mode="content")`** — width source switch per call site: `"anchor"` (default, unchanged: at least the anchor, `match_card_width` moves the match to the card) vs `"content"` (widest row only, anchor ignored for sizing; placement math unchanged). For anchors carrying affixes rows don't have (e.g. `" ▾"` on a `width_texts` button) where anchor-matching leaves trailing slack. Invalid values raise `ValueError`. Tests: `tests/test_simple_options_flyout_width.py` (+3).

- **Outer outline for region-composed buttons (`BorderLayer` + `borderWidth`)** — `BackgroundLayer` skips the border stroke for any region whose rect differs from the button rect, so `setBorderColor()` on a fully region-composed button (cover + text rows, segmented capsules) was a silent no-op: the override property was set but nothing ever stroked it. New widget-scope `BorderLayer` (runs right after `BackgroundLayer` in `default_layers`) strokes one outer rounded rect for region-composed buttons with an explicit `setBorderColor()` override; plain buttons, variant theme borders, and `setBorderColor(None)` behavior are unchanged, and the override keeps winning over disabled/`bg_locked` exactly like `BackgroundLayer`. Both layers now honor the `borderWidth` dynamic property (`float >= 1`, default `1.0`), so `setProperty("borderWidth", 2)` gives a 2px leader edge (previously hardcoded 1px). Exported from `sli_ui_toolkit.widgets` and `...buttons`. Tests: new `tests/test_button_outer_border.py` (6: override paints on region buttons, silence without override, 2px band, disabled parity, helper defaults, layer order); button/paint/flyout/tab-strip suites green (305 passed).

- **Marquee goes in-paint: `MarqueeState` + `paint_marquee_band` + `marquee_dirty_rect`** — the window-level `MarqueeBandOverlay` + `MarqueeBandGesture` pair (per-mousemove `setGeometry` + `raise_()` + `show()` on a translucent top-level child, content→window round-trip per move, viewport-clip intersection with hide/show flicker) is replaced by Dolphin-style state: `MarqueeState` tracks the drag as a content-local rect (moves consumed, LeftButton release finishes then passes through — hover-loss contract kept; degenerate start==end nudged, never invalid; `on_trace` injection instead of logger calls so `SLI_MARQUEE_DEBUG=1` needs no logger-level second gate), the host paints the band (fill a48 + 1px border a200, default `#0078D4`) in its own paint pass with region-limited `old∪new±1px` repaints. `ListPanel` migrated (own `_MarqueeContentWidget` host); `MarqueeBandGesture`/`MarqueeBandOverlay`/`map_content_rect_to_window` deleted with no shims. Tests: `tests/test_marquee_band.py` replaced by `tests/test_marquee_state.py` (8: identity, tiny, cancel, release pass-through, non-left witness, trace gate, pixels, dirty union); full suite green, mypy clean.

- **Marquee band paints over content (`MarqueeBandWidget`)** — the host-painted
variant hid under opaque cards (Dolphin paints its band after items, in
`KItemListView::paint`). New transparent mouse-transparent viewport child:
per move only `set_band` (`setGeometry` + `update`, no `raise_`/`show`
storm), visibility toggles twice per drag via `set_active`. Consumers
convert content→viewport synchronously per update. `ListPanel` and both app
shelves use it; `paint_marquee_band`/`marquee_dirty_rect` unchanged underneath.

### Changed

- **Painted `Label` context menu replaces Qt's stock popup** — `Label` inherited `QLabel::contextMenuEvent`, which popped Qt's native Copy/Select-all menu (platform style, off-theme, bypassing the painter pipeline) on right-click for selectable labels. `Label` now overrides `contextMenuEvent` and opens the toolkit `ContextMenu` (`surface="popup"`) built by the new `ui.widgets.atomic.label_context_menu` module: default entries are Copy (enabled when text is selected) and Select all, and `set_label_menu_builder()`/`get_label_menu_builder()` let hosts replace the entry builder (fail-open: a broken builder logs and never crashes the host). Non-selectable or empty labels still fall through to Qt (no menu), and the public `Label` API is unchanged. Tests: new `tests/test_label_context_menu.py` (8); mypy clean.

- **`CustomLineEdit` is now a painted single-line editor (no `QLineEdit`)** — the widget renders its own text through the toolkit painter pipeline (`ui_font` + `QPainter.drawText` + `QFontMetrics`, the same mechanism as the painted text surfaces / button rows) and implements caret, selection (drag + double/triple-click), clipboard, undo/redo and IME itself, instead of subclassing `QLineEdit`. This removes the native traps the old class worked around: palette/QSS freezing `setFont`, `minimumSizeHint` reserving a full character, and `acceptDrops` stealing drags. The `QLineEdit`-compatible surface the app relies on is preserved (`text`/`setText`/`textChanged`/`textEdited`/`editingFinished`/`returnPressed`, `setPlaceholderText`, `setValidator`/`hasAcceptableInput`, `setEchoMode` + `EchoMode`, `setClearButtonEnabled`, `setReadOnly`, `setMaxLength`, `selectAll`/`selectionStart`/`selectedText`/`setSelection`, `copy`/`cut`/`paste`/`undo`/`redo`, `cursorPosition`/`setCursorPosition`, `fontMetrics`, `textMargins`), so call sites keep working. `SpinBox`/`DoubleSpinBox`/`TimeLineEdit` are unchanged subclasses and inherit the painted rendering. Tests: `tests/test_custom_line_edit.py` +10 (typed signals, validator reject, max-length, echo/clear, selection/clipboard, return); full suite green, mypy clean.
- **Test hardening: index-identity sweeps (process only, no library change)** — the timeline-class "blind test" bug (green while content is swapped) was found in other index-fed widgets: suites asserted counts/geometry/`_item_index` but never that row/`i` renders its own content. Added content-identity sweeps: `AdaptiveTabStrip` tab titles stay bound to their index across select/close; `ComboBox` dropdown row `_text` equals its item; `ListPanel` and `VirtualListController` live windows assert `text() == f"...{index}"` at several scroll offsets; `IconListWidget` row button `_text` equals its item before and after a filter remap; the `MinimalistScrollBar` painted handle position tracks the scroll value (min hugs the groove start, max the end, monotonic between); `TextView` code-mode `line_at(y)` resolves each line's centre to its own index/text. Tests: `test_adaptive_tab_strip.py` +1, `test_combo_focus_reveal.py` +1, `test_list_panel_virtual.py` +1, `test_virtual_list.py` +1, `test_icon_list_widget_search.py` +1, `test_overlay_scrollbars_horizontal.py` +1, `test_text_view.py` +1.
- **`AGENTS.md`: diagnosis ladder pointer (process only, no library change)** — agents debugging toolkit bugs are pointed at the mandatory ladder (blast radius → working-sibling diff → grep known-bad → one-line discriminator → only then mechanism) in the private sibling docs, with the `Qt.Popup`-parented-to-top-level trap recorded as the first worked example.
- **`ButtonRow(elide=True)` truncates overflowing static text with an ellipsis** — `RowsContent` rows with `elide` (and `marquee=False`) paint `QFontMetrics.elidedText(ElideRight)` at the row width instead of hard-clipping (mirrors the existing `IconTextContent` behavior). Static paint, no timers — for hosts retiring marquee crawls. Tests: new `tests/test_button_row_elide.py` (3: default off, ellipsis unit, pixel difference elided-vs-clipped); mypy clean.
- **Hide-before-unparent sweep: 10 more sites (inspector/toast/tabs/list/pool)** — `widget.hide()` before `setParent(None)` in teardown paths flagged by the host contract `test_no_visible_orphan_setparent` (stillborn-toplevel dogma: hide first or justify). No behavior change besides suppressing stillborn visible orphans. Unblocks the host contracts gate.
- **Marquee ticks skip the painter pipeline (static-layer cache + marquee replay)** — dirty-rect ticks still ran the FULL pipeline per card per tick (context build incl. fonts/styles, region walk, background resolve, pixmap scaling, per-row `QFontMetrics`) even though only the crawling text moved (gallery: 25 cards x 60fps x ~0.7–2ms ≈ 1 saturated core idle). Now: after a full paint with live marquee rows, `Button` snapshots everything except the marquee glyphs into a DPR-aware `QPixmap` keyed by (size, per-region states, hover regions, content version, DPR); a tick whose event rect is covered by the driver dirty union blits the snapshot and replays the pre-resolved marquee rows through the existing strip path — zero context builds, zero region walks, zero background resolves, zero pixmap scaling, zero font metrics (measured ~8x per-tick win on a pixmap+rows card). Invalidation is exhaustive: every full-widget `update()` bumps the version (covers all style/content mutators without touching their call sites), hover/press/check/disable ride in the key, resize/font/theme/scale/DPR bust explicitly, an in-flight ripple forces the full pipeline, row-clipped paints never bake a snapshot, and overlay painters / custom layers snapshot through the same pipeline (their output is phase-independent; any animated paint code calls `update()`, which bumps the version and re-snapshots per frame — fail-safe, never frozen). Same 60fps crawl, fast frames byte-exact vs full frames at the same phase. Tests: new `tests/test_paint_cache.py` (71: fast-path taken with zero context builds, measured ≥5x tick collapse, every-mutator invalidation, byte-exact parity incl. compact rows and overlay painters, no-marquee never caches, resize/DPR bust, ripple guard, overlay fast-path over 60 ticks + overlay state-change bust); marquee/perf suites stay green, mypy clean.
- **Text marquee without the repaint storm (pre-rendered strip + dirty-rect ticks + clip skip)** — every overflowing `ButtonRow(marquee=True)` / `Label(marquee=True)` ran a 16ms `MarqueeDriver` timer calling full-host `update()` plus per-paint `drawText` + `QFontMetrics` measure (gallery: 25 cards x 60fps full painter-pipeline repaints idle). Now: the scrolling text renders ONCE into a `QPixmap` strip cached on the driver, keyed by (text, font key, pen color, rect size, gap, DPR) — cache hits blit two copies at the float offset with no `drawText` and no measurement (text-fits fast path stays plain `drawText`); `_tick` repaints only the union of row rects registered during paint (auto-captured from the paint device, explicit `set_dirty_rect()` override; falls back to full `update()` when unset); `_tick` is a no-op while `host.visibleRegion()` is empty, so off-viewport cards cost zero (phase-freeze is safe: the crawl resumes on the next visible tick, `set_active(False)` still resets). Same 60fps phase; integer offsets are pixel-identical, fractional offsets match within 1px AA-edge resampling (motion-identical). Public API backward compatible (`driver` is a new optional kwarg; `strip_cache_hits`/`strip_cache_renders` counters added for observability). Tests: new `tests/test_marquee_perf.py` (8: strip hit/invalidation, clipped-tick skip, dirty-rect-only tick incl. RowsContent plumbing, pixel parity); full suite green, mypy clean.
- **Inspector Colors rows show their label + source again** — the `ButtonRegion` migration rendered swatch/hex/detail but dropped the label column (`palette Window`, `QSS`, `= token`) and never showed the source path the row links to. `_add_color_button_row` renders the label region again and appends `(path:line)` to the detail when a source is set; `= token` rows render even when the source is unresolvable (no click tooltip then). Fixes the 2 `test_inspector_colors` failures. Tests: `test_inspector_colors.py` 8 passed, full suite 1216 passed, mypy clean.
- **mypy 2.x strictness: typed text_view cluster, no behavior change** — the `_CanvasEditingApi`/`_CanvasEventsApi`/`_CanvasPaintApi` mixins now declare the owner state they read (plain annotations, same pattern as the `_Flyout*Api` family); `super().<event>` calls in `events.py` are explicit `QWidget.<event>(self, ...)` (identical MRO target) with narrow `type: ignore[arg-type]`; `TextView.inspect_spec`/`widget_descriptor` declared `ClassVar`; unreachable-`None` asserts narrow the keyword tokenizer and theme selection color. Area suites green (80 passed).
- **mypy 2.x strictness: typed flyout/composite set, no behavior change (lane L2)** — the flyout shell (`base_flyout/` lifecycle/placement/widget), toast, timeline, simple-options flyout, sidebar nav list, list panel, adaptive tab strip, help document, calendar, top tab bar, dialog shell, context menu, indexed-toggle and icon-action flyouts now pass `mypy` with 0 errors (was ~122): `ClassVar` declarations for the module-bottom `inspect_spec`/`widget_descriptor` metadata, `cast()` at mixin→`QWidget`/`QObject` boundaries, `NavigationSection` (`QObject`) conformance for the flyout nav section, `TabSpec.close_button: Button | None`, the missing `focus_reason` on `IconActionFlyout.show_aligned` (forwarded to super), and narrowly-scoped `type: ignore[<code>]` only for genuine PySide6-stubs gaps (`shiboken6.isValid`, `setFocusProxy(None)`). Runtime behavior unchanged. Tests: flyout/composite area suites green (530 passed), full suite 1214 passed + 2 pre-existing `inspector_colors` fails.

- **`SimpleOptionsFlyout.show_below(..., match_card_width=True)`** — width matching measured the halo: `exact_width_match` equals the *outer* widget (card + shadow margins) to the anchor, so the white card always read narrower. The opt-in flag passes the margins back in, matching the opaque card to the anchor instead. Default behavior unchanged. Tests: `tests/test_simple_options_flyout_width.py` (+2: card-match, outer default).

- **`OverlayScrollArea` horizontal overlay bar + working thumb drags** — the area now owns a floating horizontal `MinimalistScrollBar` mirroring the vertical one (own visibility, bottom-anchored positioning, shared auto-hide policy, viewport-margin reserve per axis), plus a `widget_resizable=False` opt-out for fixed-size content. Also fixed: dragging either floating thumb previously set only the thumb's own value and never moved content (measured live: custom 152 vs native 0) — `custom→native` propagation is now wired both axes with a `_syncing_scroll` guard, so no feedback loop. Tests: new `tests/test_overlay_scrollbars_horizontal.py` (6: h hidden-when-fits, h bottom-anchored on overflow, h/v thumb drags drive native — all fail pre-fix — resizable opt-out, h auto-hide cycle); full suite green, mypy clean.

- **mypy 2.x strictness: typed atomic/combobox set, no behavior change** — declared the post-hoc `inspect_spec`/`widget_descriptor` class attributes (`ClassVar`) on all 13 atomic/combobox widgets, annotated `SpinBox` int state (float widening in `DoubleSpinBox` kept behind narrow `ignore[assignment]`), gave the inspector `items` lambdas named `Any`-typed helpers, and tightened `_overlay` slot/pool boundaries (`cast`, `QWidget | None` parent, `QWidget`-typed bind callback). No runtime behavior change; `mypy` over `ui/widgets/atomic/` + the three combobox modules reports 0 errors.
- **mypy 2.x strictness: typed managers/inspector/windows/buttons set, no behavior change** — `NavigationSection` protocol narrowed `QObject`→`QWidget` (every implementation and call site already uses widgets), missing annotations added (`_auto_rows`, `states`, `set_regions`, `WindowChrome` post-install attrs, `Button` spec `ClassVar`s, `CodeSectionEditor` legacy originals), `None`-narrowing via direct attribute checks and `isinstance` guards, `cast` for known-4-tuples, and narrow `type: ignore[<code>]` for genuine PySide6-stubs gaps (`shiboken6.isValid`, `Qt.Edge.value`, `setFocusProxy(None)`). One intended-behavior restoration: the Label inspector `text` getter was a 0-arg lambda that always raised `TypeError` (silently swallowed — the field never appeared); it now takes the widget like every sibling getter. Tests: area suites for managers/inspector/windows/buttons green, full suite green, `mypy` over the owned paths reports 0 errors.

### Fixed

- **`suspend_widget_updates` never freezes translucent CSD shells (punch-through guard, qt-selfsizing Phase 3)** — the freeze covered every top-level, so a geometry mutation mid-suspension (theme apply, UI-scale fan-out) left never-repainted see-through areas on `WA_TranslucentBackground` windows. Translucent top-levels (and ripple-active trees, as before) are now skipped; opaque windows still freeze atomically. Covers both call sites centrally (theme apply + app scale apply need no change). Tests: new `tests/test_theme_manager_suspend.py` (3: opaque frozen/translucent kept, prior-disabled restore, nesting; key test fails pre-fix).

- **`AdaptiveTabStrip` settles the tab-bar height synchronously (qt-selfsizing T1)** — `_sync_visual_tab_height` derives the tab-bar minimum from the add button while the strip layout places both, with only a deferred (`singleShot(0)`) parent resync: raising the minimum self-enforces, but lowering it never shrinks the bar, so the strip layout reclaimed the height a turn late and the bar painted one frame too tall. It now ends with `settle_layout(self, tab_bar, add_button)` (the deferred host re-flow stays — the parent above the strip is layout-external). Tests: new `tests/test_adaptive_tab_strip_settle.py` (2: grow/shrink same-call bar/minimum agreement; shrink fails pre-fix, grow locks in the self-enforcing raise).

- **`SimpleOptionsFlyout` settles derived sizes synchronously (qt-selfsizing T1)** — `geometry.update_size` fixes the flyout + container from live row hints while `QLayout`s place the children, with no synchronous settle: rows kept stale geometry for one painted frame. It now calls `settle_layout` (never a second implementation): rows refresh *before* the `setFixedSize` pair — the sizes propagate synchronously through the scroll area and that cascade pins the contents to the current minimum, so stale hints stuck a shrink wide for a frame — then container, flyout, and rows again after the ancestors resized the rows host (an outer activate alone misattributes growth through a nested fixed-size host). `_set_rows_raw` re-fits after `setUpdatesEnabled(True)` is restored (a layout on an updates-disabled widget ignores `activate()`). `show_below` settles after its post-show width re-assert. Tests: new `tests/test_simple_options_flyout_settle.py` (2: widen/narrow same-call row/container agreement; narrow fails pre-fix, widen locks in the cascade behavior).

- **Marquee survives native-window crossings mid-drag (per-event button desync)** — crossing into a sibling native window mid-drag (toolbar/stats-strip `QWindow`s, context-menu popups) empties the per-event button mask — sticky, even back on the press window — while the OS-level mask stays truthful (live-proven: gallery band froze ~3 s with `event.buttons() == 0` and global `LeftButton` held). `MarqueeState` now falls back to the global mask for moves while a drag is in flight (a real release always arrives as `MouseButtonRelease` and finishes, so in-flight origin + global Left means desync, not hover). Release pass-through is unchanged. Tests: `tests/test_marquee_state.py` (+1: desynced-event move still tracks — fails pre-fix).

- **Popup submenus join the live grab chain + open on hover** — a submenu opened from a popup-surface parent was transient for the logical anchor's window instead of the parent popup's window, so on live Wayland the compositor never transferred the xdg_popup grab and leaf clicks never dispatched (offscreen QTest stayed green — no compositor grab there). `toggle_submenu` now binds the child popup's transient parent to the parent menu's window (pre- and post-show, mirroring Qt's nested-QMenu nesting) while keeping `WA_ShowWithoutActivating` and the fade/positioning behavior; parent outside-close already recursed into the open submenu and parent hide already closes it (both verified). Parent rows also open their submenu on hover now (FM/Dolphin parity: `SUBMENU_HOVER_DELAY_MS = 300`, cancellable when the pointer leaves; click still toggles), and hovering a sibling leaf row closes the open submenu (QMenu parity). Once open, the submenu holds the mouse grab, so hover positions are forwarded to the owner menu: sibling-parent hover switches branches, sibling-leaf hover closes at once, motion inside the branch cancels pending state, and aiming across the gap never closes it (an outside-grace timer did — the submenu vanished mid-aim; QMenu parity closes on sibling hover, outside click, Escape, or parent hide instead). Tests: new `tests/test_context_menu_submenu.py` (10: hover open/cancel, transient parent, switch, leaf close, gap-aim keeps open, no double schedule).
- **Submenu hover dwell removed (`SUBMENU_HOVER_DELAY_MS = 0`)** — branches now open on the next event-loop pass after the pointer enters a parent row instead of after a 300ms FM-parity dwell (live-measured open latency was ~1s: aim + dwell + 160ms fade; our visual language wants immediate branches). The single-shot timer machinery stays, so a Leave within the same turn still cancels the pending open; click still toggles. Tests: hover budget assertion is now `== 0`, cancel/switch/close coverage unchanged.
- **Submenus never fade (branches show/hide instantly)** — a branch is its own popup; fading the outgoing branch in/out left it mapped for ~150ms while the incoming branch opened, so on a switch the two popups overlapped and the new branch read as "died" (the reported "second submenu dies"). `toggle_submenu` no longer arms the branch fade controller or calls `_start_popup_fade_in`, `should_popup_fade_out` is False for `_is_submenu`, and `close_submenu` deletes the branch immediately (its hide is synchronous — no fade finish handler). Only the root menu keeps the fade; owner close still snapshots before detaching so the owner row's open-highlight survives (no one-frame unhover flash), and a native child-first close (outside press hides the topmost popup) still hides the still-claiming owner. Tests: `tests/test_context_menu_submenu.py` (+5: submenu never fades under a fade mode, root still fades, switch hides the old branch before the new one, child-first close hides the branch instantly, owner hide closes the branch instantly).
- **Closing a submenu no longer reopens it (post-hide hover re-enter)** — when a popup branch hides, Qt re-delivers a hover `Enter` to the owner-menu row still under the pointer; that re-scheduled the hover-open, so the branch blinked (closed then reopened) and the owner row's highlight flashed off/on. `close_submenu` now arms a `_submenu_closed_row` guard and `_schedule_submenu_hover` ignores a hover-open for that row until the pointer actually leaves it (cleared on the row's `Leave`/`HoverLeave` or when another row is entered). Click-to-close keeps working (a click still toggles); only the spurious post-hide hover re-enter is swallowed. Tests: `tests/test_context_menu_submenu.py` (+2: toggle-close stays closed across the re-enter, re-enter after a real leave reopens).
- **Owner-row highlight no longer blinks on menu close (fade snapshot from frame one)** — `start_popup_fade_out` captured the snapshot but left `opacity == 1.0`; `paintEvent` composites the snapshot only while `opacity < 1.0`, so the same-turn repaint that clears the owner row's `_submenu_open` highlight (and any other live repaint) painted the live plain row for a frame before the fade took over — the selected button flashed off/on. The fade-out now drops below 1.0 and hides the live children immediately, so the snapshot path is active from the first frame. Tests: `tests/test_context_menu_submenu.py` (+1: snapshot active before first frame).
- **Outside click dismisses the whole menu chain, not just the submenu** — a Qt popup grab natively hides only the topmost popup, so an outside press with an open branch left the parent visible with a stale `_open_submenu`. QMenu dismisses everything: the branch's `aboutToHide` now hides a still-claiming owner (cascades through nested owners; owner-driven closes clear the branch first, so no ping-pong). Tests: `tests/test_context_menu_submenu.py` (+2: branch hide hides the owner, owner-driven close stays single).
- **Submenu no longer closes on the first step into it** — the owner installs itself as an event filter on the submenu's rows (mouse-grab forwarding), but `Enter`/`Leave` on branch rows fell into the "sibling leaf hovered" path: opening e.g. `recent-empty` Sort by and moving onto its first child closed the branch as a sibling leaf (`close reason=sibling-leaf-hover`, caught live via the new `[ctx-menu]` firehose). The owner now ignores `Enter`/`HoverEnter`/`Leave`/`HoverLeave` from rows inside its open submenu branch (sibling logic runs on own rows only; nested branches covered). Tests: `tests/test_context_menu_submenu.py` (+3: branch-row Enter keeps the branch, branch Leave keeps a pending switch, owner-leaf Enter still closes).
- **Submenu hover firehose (`[ctx-menu]` traces)** — `SLI_CTX_MENU_DEBUG=1` previously logged only keyboard (Escape/Enter/Up/Down), leaving the hover path invisible when a submenu "vanishes on leave". The same env-gated stream now logs every hover-path transition with a `reason=`: open-keep/toggle-open/toggle-switch/toggle-close, close (`toggle-same-row | toggle-switch | forward-sibling-leaf | sibling-leaf-hover | row-click | entries-reset | popup-reopen | parent-hide`), forwarding install, forwarded-move dispatch, forward hit-test decisions (switch-schedule / sibling-leaf close / keep with inside-branch vs owner-chrome/outside-gap cause), hover schedule/cancel/timeout, row enter/leave, menu hide, and submenu geometry at position time. Row-level transitions are covered too (`rows.py`): every `submenu-open` toggle and `hover-enter`/`hover-leave`; plus the just-closed-owner guard (`armed row=… reason=…`, `cleared (pointer left row|entered other row)`, `suppressed (just-closed owner)`) so a "parent button blinks on submenu close" report pins the exact row and transition. App side logs the outside-close verdict (`pos / inside / submenu_open`, same-key toggle vs replace) under `[ctx-menu]` on the host logger. Off by default; no behavior change. Tests: `tests/test_context_menu_submenu.py` (+3: trace-off silence, trace-on open/forward/close lines, trace-on close-guard + row transitions).
- **Marquee band no longer restacks/repaints on identical geometry** — `MarqueeBandOverlay.set_band()` is driven per mousemove (100+/s) and used to `setGeometry` + `raise_()` + `update()` on every event even when the rect did not change, making the band edge judder against compositor paint frames. Same-geometry calls (while visible) skip geometry/repaint; stacking is established on show and re-asserted (without repaint) only when a sibling flyout covered the band — context menus restack themselves on open, which previously left the band painting underneath until the next geometry change. Tests: `tests/test_marquee_band.py::test_marquee_band_set_band_skips_identical_geometry` + `::test_marquee_band_set_band_reraises_when_covered`.

- **Pixmap region corners clip with antialiasing** — `PixmapContent` clipped the rounded path without the AA hint, leaving stair-step fringe pixels in rounded corners (visible as dirt on gallery list thumbs). The clip now paints antialiased.

- **Marquee release no longer desyncs Qt press-tracking (hover death)** — `MarqueeBandGesture.eventFilter` finishes the gesture on LeftButton release but lets the release pass through (`return False`) instead of consuming it. Rationale: the matching press went through the window before the child filter consumed it, so a consumed release left press-tracking stuck on "held" — later moves grab-routed to the press receiver with no hit-testing and no `Enter` (gallery hover capsule + delete badge stayed dead until some other balanced click; see the project's internal engineering notes on gallery hover loss). `_finish_at` already removes the app filter, so this only resumes normal delivery. Tests: `tests/test_marquee_band.py::test_marquee_release_reaches_widgets` (finish runs, filter removed, overlay hidden, release passes).

- **Hover-frequency flyouts no longer storm window activation on show** — `BaseFlyout.show()` honors a new `_no_window_activate` opt-out (skips the `activateWindow()` kick when the window reports inactive). Rationale: hover pills shown per pointer Enter (e.g. the gallery card capsule, including cards sweeping under a stationary cursor during scroll) minted one xdg-activation request per show under Wayland's mid-scroll inactive report, and the compositor answers the storm with busy-cursor feedback (same class as the MC wheel-zoom storm and the hide-time focus-restore banner). Default behavior unchanged (opt-out is off unless the host sets it). Tests: new `tests/test_flyout_show_activate_optout.py` (4).
- **Sidebar rows shrink below text width** — `IconListWidget` row buttons now use horizontal `Ignored` (not `Expanding`, which honors `minimumSizeHint`): narrowed hosts shrink rows so `ContentLayer` elides instead of wedging the host at the widest entry. Tests: `tests/test_icon_list_widget.py` layout regression.
- **Wrapped labels keep heightForWidth** — `Label._apply_style` rebuild wiped the `heightForWidth` flag `setWordWrap()` maintains while forcing vertical `Fixed`; `setWordWrap()` now resyncs the vertical policy (`Preferred` when wrapped) and the flag survives style re-application. Tests: new `tests/test_label_word_wrap_policy.py` (4).
- **Eager-annotation imports (`QSize`, `ContextMenu`)** — `CustomLineEdit.minimumSizeHint` annotated `-> QSize` with only a body-level import, and `toggle_submenu` annotated `menu: ContextMenu` with a circular-dodge body import: both raise `NameError` at import time on Python ≤ 3.13 (only masked locally by PEP 649 lazy annotations on 3.14+, which is why CI on 3.13 went red while Termux stayed green). `QSize` moved to the module `QtCore` import; the submenu annotation is now quoted.

- **Flyout focus-restore no longer pages the compositor** — hiding flyouts (`BaseFlyout._finish_hide`, `SimpleOptionsFlyout.hide`) dropped `activateWindow()` entirely and re-assert widget focus only when the host is the app's active window (new `should_restore_host_focus()` choke point, exported from `base_flyout`). Rationale: xdg-activation tokens go stale across event-loop turns by construction (the fade delay proved it) — a denied restore marks the host demanding attention ("«App» is ready" banner), observed on minimize/deactivate where `activeWindow()` is None. Behavior on the active host is unchanged (focus stays where the user put it). Tests: new `tests/test_flyout_focus_restore_guard.py` (8: helper matrix incl. the minimize case + hide() integration asserting zero compositor calls).
- **Timeline order-invariant keyframe evaluation [task-fix-toolkit-unsorted-keyframes-2026-09-21]** — `layout._evaluate_channel_at_timestamp`, `layout._channel_value_at_timestamp` (prefer-exact), `layout.visible_keyframe_segments`, and `segments._enum_state_spans` assumed time-sorted `channel.keyframes`; shuffled host input dropped or misplaced spans. All four sites now route through the new `layout._ordered_keyframes` helper (stable sort, no host-data mutation), so sorted and shuffled input evaluate identically; behavior on sorted input is unchanged. Tests: new `tests/test_timeline_keyframe_order.py` (5: sorted-vs-shuffled parity for scalar step evaluation, prefer-exact lookup, enum spans, scalar segments, and color track values, plus a no-mutation check); full suite only the 2 pre-existing `inspector_colors` fails, mypy 0 new.
- **Timeline scalar stagger stability [task-timeline-track-render-remainder-2026-09-19]** — `layout.visible_keyframe_segments` advanced its stagger parity counter only for appended (in-damage) segments, so partial repaints assigned different lane y values than full repaints and scalar lanes jumped between partial paints (playhead/hover/selection) and full paints. The counter now advances per eligible segment before the damage cull (enum/color lanes already index parity over pre-cull spans). Tests: new `tests/test_timeline_stagger_stability.py` (2: mid-window and left-edge partial-vs-full y + curve_points agreement; verified red on pre-fix code). — `DecisionJournal.note()` emitted via `logging.getLogger("ImproveImgSLI")`, a host-tree logger with no handlers unless the host app configured it (wrong tree, invisible in the host log file). It now logs on the module (`sli_ui_toolkit.*`) tree, which `setup_logging()` wires handlers to; hosts that skip `setup_logging()` still see the records via root propagation. Gating unchanged (`SLI_FLYOUT_DEBUG` et al). Tests: new `tests/test_flyout_timer_logging.py` (3: toolkit-tree emission, host-tree silence, flag-off silence, no-setup visibility).
- **Chrome services [task-fix-toolkit-chrome-services-2026-09-20]** — `prewarm_widget_window` records pre-show visibility and only re-hides widgets it revealed (prewarming a visible window no longer hides it); `prewarm_widget_window_once` gains `reset_prewarm_once` for reconfigure paths. `IconService` gains a TTL negative cache (`NEGATIVE_CACHE_TTL_S`, 30s) bounding repeat-miss stat storms, a first-root revisit (fresh misses still re-check the primary theme dir, so newly-dropped icons resolve immediately), `invalidate()`, and `get_icon_service` rebuilds on an explicit differing root instead of pinning the first root forever. `ToolkitDragDropService` resolves overlapping targets by real stacking order (`QApplication.widgetAt` ancestor match, last-registered fallback), emits `drag_state_changed(bool)` on start/finish/cancel, and hardens registration (`_purge_dead_targets`, identity-based unregister, snapshot iteration so mid-sweep unregisters skip nothing). `CustomTitleBar` Left/Right at cluster ends now falls through (`eventFilter` returns False) instead of swallowing the key, so NavigationManager owns cross-section handoffs. Tests: new `tests/test_chrome_services.py` (13); wave-2 chrome/dragdrop/icon/title-bar suites green, mypy 0 new.

- **Chrome resize/move [task-fix-toolkit-chrome-resize-2026-09-20]** — min/max are honored in the content frame: the outer-band patch translates widget min/max into frame space (+2*band) at install and `remove_frameless` restores them, so Qt/compositor enforcement, the manual per-move clamp, and the new native release clamp (same `_content_frame_limits` helper — parity by construction) all agree; content max is reachable again and the content floor can't be breached. Title-bar drag attempts `startSystemMove` on PRESS (Wayland binds the press serial; a later move-event attempt always failed) and ignores app-level moves while the compositor owns the drag; the manual path re-anchors instead of teleporting when the press un-maximizes. Corner-mask rebuilds coalesce across resize streams (`request_csd_mask_sync`: one deferred rebuild per burst; layout/bg/title-bar sync stays synchronous), and `WindowChrome.install` targets the pre-install content size + band with an explicit `sync_csd_chrome` (hidden windows get no Resize events — the body layer no longer freezes at a pre-expansion size). Tests: new `tests/test_chrome_resize_move.py` (11: content-frame min/max, native parity, press system-move, exact-delta move, un-maximize re-anchor, mask coalescing, DPR mask safety, move stability); full suite only the 2 pre-existing `inspector_colors` fails, mypy 0 new.
- **Chrome lifecycle [task-fix-toolkit-chrome-lifecycle-2026-09-20]** — `WindowChrome.install` is idempotent (returns the existing chrome instead of double-patching `resize`/`setGeometry`, stacking geometry filters, and orphaning title bars); the outer-band geometry patch applies once and `remove_frameless` restores the original `resize`/`setGeometry`. The resize margin is per-window (`_csd_resize_margin` property, snapshotted by the resize filter) — installing with `resize_margin=` no longer mutates process-global `frameless.RESIZE_MARGIN`. `CustomTitleBar.attach_window` dedups same-window re-attach (refresh only), detaches the previous window on re-attach (exact-slot disconnect), and unpins the target on destroy (`_target_window` → None). Tests: new `tests/test_chrome_lifecycle.py` (7); full suite only the 2 pre-existing `inspector_colors` fails, mypy 0 new.
- **Inspector honesty [task-fix-inspector-staleness-2026-09-20]** — `_layout_tree_key` is now the window id plus the full ordered `(label, widget, indent)` fingerprint: middle reorder/removal/rename changes the key, so the window-level Layout cache can never serve a stale tree (worst case is a rebuild; also fixes the inverted "costs a rebuild at worst" comment). `capture_tokens` discloses empty repaints instead of returning `()`: hidden widgets get a `capture_limitation=hidden` row (grab cannot repaint them), visible-but-keyless repaints a `capture_limitation=cached` row (paints from cached state, not live lookups). `inspect_widget` marks failed spec/extractor runs with an `extractor:<family>` state row (`meta extractor_failed`) on the generic fallback instead of silently posing as complete; the Theme page titles disclosure-only captures "Live capture (no tokens recorded)". Tests: new `tests/test_inspector_honesty.py` (13); inspector suites green, mypy 0 new.
- `_AdaptiveTabBar` relayouts on `FontChange` (no more detached add button / dead zone after font switches).
- Shared logging re-entry keeps `min(app, toolkit)` handler level so a second `setup_logging()` call can't silence the host's debug stream.
- `Window` -> `surface.background` token migration for missed painter reads, `token_family` lists, and CSD window-body defaults (`Window` kept as `get_color` fallback).
- **Timeline gutter debug traces (`[timeline-gutter]`)** — `SLI_TIMELINE_DEBUG=1` now logs the gutter/zoom ordering: zoom-commit entry, post-`setValue` clamp, `update_fixed_width` width step, synchronous band repaint with live-scrollbar drift flag, per-paint damage-vs-band hit, sticky-overlay arg-vs-live skew, host-scroll band, gutter-drag width. Each line carries `tick=N` so a ~1-frame gutter lag reads off the log order. Tests: `tests/test_timeline_gutter_debug.py` (gate-open fires + formats clean, gate-closed silent).
- **Timeline Phase 3 polish (no behavior change)** — single quantize contract documented on `viewport.pos_to_frame` (`frame_to_pos` now nearest-pixel `int(round())`); all paint/cull passes derive from the single `layout.DAMAGE_PAD` (ruler `±20/±50` literals removed, label overhang derived); per-row/per-tick `QColor`/`QPen` hoisted to per-paint locals and shared read-only `primitives._alpha_color`/`_pen_for` caches (double-paint deterministic); strip-chrome tokens verified split per theme with AA contrast. Tests: +44 (round-trip, damage singularity, determinism, contrast); full only 2 pre-existing `inspector_colors`, mypy 0 new.
- **Timeline lifecycle coherence (Phase 2 T-life)** — `_destroyed`/`isValid` gates on every commit/playhead/ingest/thumbnail entry (shared `interaction.is_alive`); symmetric show/teardown restores tooltip, playhead-easing, inner-scrollbar, and UiScale connections with registry-paired event filters that forget dead viewports on host change; `eventFilter` returns True when handled and only pings the settle gate (no re-entrant commit cascade); gutter drag commits exactly once on release with one synchronous band repaint (live assert removed); ingest explicitly freezes the tile aspect (`interaction.freeze_thumb_aspect`, in-place swaps re-freeze); prune keep-window from block units with batched linear inserts (same policy + 512 cap); hover hit-sets rebuild damage-independent post-paint (identical full/partial, consistent color/enum/scalar); track-kind/outline/row-rule tokens split per light/dark; tuning centralized into interaction constants. Tests: 11 tokens + 2 keyboard new; 144 targeted green, full only 2 pre-existing `inspector_colors`, mypy 0 new.
- **Timeline preview identity (Phase 1: T-paint + T-state)** — strip lookup is now exact-match only: new canonical `viewport.thumbnail_for_rep(rep)` (`None` on miss, no `bisect`, no `idx[0]`), consumed by `render.draw_thumbnail_strip` through one thin alias (temporary IDENTITY-SHIM removed at merge); missing reps paint a theme-token placeholder (`timeline.track.background`), never a neighbor pixmap; degenerate blocks `continue` instead of aborting the strip; `+1px` seam overdraw applies only while collapsed (never at 1:1). Strip geometry frozen at ingest: tile aspect derives once from snapshot size metadata (`16/9` fallback) and no longer tracks arrivals/evictions/pixmap dimensions; `calculate_min_zoom` uses `frame_span` like the logical width; zoom diff epsilons unified behind `state.ZOOM_DIFF_EPS` (`1e-4`); new block-unit `viewport.visible_strip_block_range` shared by prune/fetch derivations. Debug audit reports per-block `hit_exact`/`missing` and strip `exact`/`missing` counts. Tests: new `tests/test_thumbnail_identity.py` (8 identity contracts: distinct payloads, sparse/evicted → placeholder, zoom remap without cross-binding) + 11 state/window tests; timeline suites green, full suite only the 2 pre-existing `inspector_colors` fails, mypy 0 new.
- **Timeline single geometry + gutter unification (structural refactor waves A+B)** — lane centers now go through one `layout.row_center_y()` contract and paint through a single `primitives.draw_center_line()` QRectF primitive (no `int()` truncation of `.5` centers); cull uses one `layout.DAMAGE_PAD`; `group_toggle_hit` rebuilt on `visible_row_window` (signature frozen); gutter exposes `viewport.visible_row_gutter_window()` + `hover_points_for_rows()` + `clamp_gutter_width()` with drag traveling the frozen `TimelineViewportState` shape (commit cutover marked CUTOVER-C for the lifecycle wave); `viewport.tooltip_for_keyframe` is fail-open on missing color comps (no-alpha tracks no longer crash live paint). Tests: new `test_timeline_center_line.py`, `test_timeline_gutter.py`; timeline suites 85 passed, full suite only the 2 pre-existing `inspector_colors` fails.
- **Timeline lifecycle (structural refactor wave C-T)** — terminal `close()` teardown (UiScale/host-scrollbar/child disconnects, event-filter removal, destroyed-gate on deferred flush/settle), per-instance i18n only (construction no longer overwrites process-global hooks), thumbnail store bounded to visible window + margin (512 hard cap), deleted deprecated `resized`/`layoutSettled` signals (use `viewportChanged`/`viewportChangedState`), `_commitState` accepts `source="gutterDrag"` (viewport family only). Tests: `test_timeline_state.py` +11; timeline suites green, full suite only the 2 pre-existing `inspector_colors` fails, mypy 0 new.
- **TimelineWidget keyboard/a11y** — Up/Down yield to navigation (`event.ignore()`); PageUp/PageDown step 10 frames; bare Space emits new `playPauseRequested` signal (host wires it to `toggle_playback`; Space with modifiers untouched); Plus/Minus zoom ×1.25 about the viewport center; `AccessibleName`/`AccessibleDescription` set. Tests: `test_keyboard.py` +9.
- **Timeline thin-owner phase 2 (widget.py 1264 → 612 lines)** — zero behavior change. Zoom/state orchestration lives as plain widget-taking functions in `viewport.py` (`commit_zoom`, `current_state`/`commit_state`/`refresh_viewport_state`/`recompute_fitted_state`; single `_zoom_level` writer besides `__init__`; `get_pixels_per_second` delegates to the single pps formula; `set_zoom`/`set_pps` `anchor` validated and forwarded; `fit_view` commits via `_commitState(source="fitView")`; viewport leg of the layout↔viewport import cycle broken). Row geometry is single-sourced via `layout.iter_row_rects` (kills the ×3 y-accumulation loops); group geometry lives in `layout` (`group_key`, `is_group_collapsed`, `toggle_group_collapsed`, `group_header_rect`, `group_chevron_rect`, `group_accent_color`) with same-named one-line widget delegators; widget gutter copy deleted (canonical `viewport.gutter_band_rect`); `set_data`/thumbnail-prune/playhead/geometry/settle/scroll/flush/lifecycle bodies moved to `interaction.*` (16 dead wrappers deleted after zero-caller proof; `keyPressEvent` untouched for the keys-a11y follow-up). Group/ruler wash alphas promoted to theme tokens (`timeline.group.wash.track/first/channel.alpha`, `timeline.ruler.minor.tick.alpha`) with identical per-theme defaults, resolved through `timeline_alpha` (render helper collapsed onto it). Tests: unified-commit, anchor-variant, pps-edge, wash-override, color-setter suites; timeline 163 passed, full suite only the 2 pre-existing `inspector_colors` fails, mypy 0 new. Docs: `CHARTS_API`/`API_CATALOG` TimelineWidget sections refreshed to the real API.
- **Timeline Phase 4D API** — new `TimelineDataSource` Protocol + `set_data(source=...)` overload (explicit args win, fail-open legacy), public `set_zoom()`/`set_pps()` (clamp/commit/anchor-center, silent no-change), per-lane `lane_value_color` delegate hook on `TimelineCallbacks` honored by `theme.track_value_color` (explicit accent > delegate > kind token > widget accent, fail-open), `timeline.center.line` split per theme (light #696B77 / dark #BEBEC4, both >= 3.0:1 vs lane_bg), widget-side thumbnail window contract tests. Keyboard/a11y surface specified (Up/Down yield, PageUp/PageDown ±10, Space playPauseRequested, +/- zoom) — key handling + AccessibleName land as follow-up (needs NavigationSection design + host play behavior).

- **Dialog auto-size settles synchronously (qt-selfsizing T2)** — `auto_size_dialog` derived the dialog size from its content hint (`resize` from `sizeHint`) with no synchronous settle (bare `singleShot(0)`): the widget and its contents disagreed for the first frame. New synchronous core `apply_auto_size(dialog, min_w, min_h)` (also exported from `sli_ui_toolkit.ui.dialogs`): refreshes child hints first so `adjustSize()`/`sizeHint()` see current state, resizes from the fresh hint, re-syncs group frames (each `StyledGroupFrame` parent now ends with `settle_layout`), then settles the dialog layout in the same call. `auto_size_dialog` applies it synchronously when the dialog is already visible/polished and only defers while hidden (hints invalid); the deferred leg carries a torn-down guard. Tests: new `tests/ui/test_layout_settle_t2_dialogs.py` (5: grow/shrink same-call agreement incl. minimums, hidden-deferred preservation, core direct — 4 fail pre-fix).

- **Inspector pages settle on stack resize / tab switch (qt-selfsizing T2)** — `QStackedWidget` only lays out its current page, so hidden section pages kept creation-time internals (a 640x480 scroll area inside a resized page — reproduced live) and flashed one stale frame on switch. Both sync legs (`_InspectionPane.eventFilter` on stack resizes, `_on_sidebar_row` on switches) now end with `settle_layout(page, scroll_area)` — settling the page, a different widget than the watched stack, never inside anyone's own `resizeEvent`. Tests: new `tests/ui/test_layout_settle_t2_inspector_view.py` (3: hidden-page grow/shrink same-call agreement, desynced-switch agreement — all 3 fail pre-fix).

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

- `TimelineWidget` colors are now `timeline.*` theme tokens — every
  previously hardcoded `QColor` in the timeline paint path resolves through
  `ThemeManager.try_get_color` with a per-theme fallback, and the
  per-`is_dark` hardcoded branches are gone from `theme.py` /
  `primitives.py` / `segments.py`: gutter/group/lane/footer/track
  backgrounds (`timeline.gutter.background`, `timeline.group.background`,
  `timeline.lane.background`, `timeline.footer.background`,
  `timeline.track.background` → `AlternateBase`), grid/separator colors
  (`timeline.grid.color` → `separator.color`,
  `timeline.separator.strong` → `dialog.border`,
  `timeline.separator.soft`), scrollbar fills
  (`timeline.scrollbar.idle/hover`), track kind colors
  (`timeline.track.bool/enum/state/vec2`), the keyframe dot outline
  (`timeline.keyframe.outline`) and the playhead halo
  (`timeline.playhead.outline`). The accent-wash translucencies are
  alpha tokens too (`timeline.gutter.wash.top/bottom.alpha`,
  `timeline.gutter.edge.alpha`, `timeline.group.header.start/end.alpha`,
  `timeline.scrollbar.track.alpha`) — a host overrides one by registering
  a `QColor` whose alpha carries the value. Hosts can restyle any of these
  via `register_palettes` without touching the widget; defaults render byte-
  identical to the old hardcodes in both light and dark. New helpers
  `keyframe_outline_color()` / `playhead_outline_color()` /
  `timeline_alpha()` (plus the `TIMELINE_TOKENS` tuple) are the handoff API
  for the `render.py` / `viewport.py` call sites owned by the parallel paint-
  contract work, which still hold their own hardcoded fallbacks. Public API
  unchanged (`track_line_color`, `group_content_bg` signatures intact).
  Guarded by `tests/test_timeline_tokens.py` (light+dark resolution, token
  override wins, no-`is_dark`-branch source scan, real-widget light/dark
  render smoke test).
- Timeline token handoff closed on integration: `render.py` row rules /
  center lines (`timeline.separator.row`, `timeline.center.line`, defaults
  byte-identical to the old hardcodes) and   `viewport.py` scrollbar fallbacks
  (`timeline.scrollbar.idle/hover`) now resolve through the new helpers
  (`row_separator_color()`, `row_center_line_color()`,
  `scrollbar_idle_color()`, `scrollbar_hover_color()`). No hardcoded
  `QColor` remains in the timeline paint path; `inspect_spec`
  `token_family` extension deferred to the timer/state phase (owns
  `widget.py`).
- Timeline timer/state cleanup: the playhead lerp `QTimer` is a
  `QPropertyAnimation` (150 ms OutCubic — same smoothing, `headMoved`
  still fires synchronously), the two `singleShot(0, fit_view)` calls are
  coalesced through the layout settle gate, `TimelineViewportState` is the
  single mutation source (zoom commits go through `_commitState` with
  identical emit semantics; silent write-through keeps readers fresh), and
  localization hooks are per-widget (`bind_widget`, process-global
  callbacks kept as fallback for handle-less paint paths).
  `inspect_spec.token_family` now references `theme.TIMELINE_TOKENS`.
  Guarded by `tests/test_timeline_state.py`. Host note: the private
  `timeline._lerp_timer` poked by old host cleanup code is gone — guarded
  `hasattr` call sites simply skip.

### Removed

- **PyPI and AUR publishing workflows** — `.github/workflows/publish.yml` and
  `.github/workflows/aur-publish.yml` removed; the toolkit is consumed from
  source by host apps, not published as a distribution.
- **Release-metadata CI gate** — the `Validate release metadata` step and
  `build/ci/validate_release_metadata.py` are gone, along with the stale
  `build/AUR-template/PKGBUILD` they checked. CI no longer requires the AUR
  `pkgver` to match `pyproject.toml` / `_version.py`; version bumps still keep
  those two plus `CHANGELOG.md` in sync (see `AGENTS.md`).

### Changed

- **Timeline Ctrl+wheel zoom is cursor-anchored and coalesced (Z1+Z2+Z3)** — `pps = zoom * base_pps` is now the documented single zoom scalar (`viewport.get_base_pixels_per_second` / `pixels_per_second_for_zoom`); the wheel step keeps the time under the cursor fixed (`scroll = cursor_time * new_pps + LEFT_GUTTER - cursor_viewport_x` via `viewport.cursor_time_at_x` / `anchor_scroll_for_zoom`, replacing the playhead-centered jump); per-tick factor `1.15` → `1.25` (`viewport.WHEEL_ZOOM_FACTOR`, single site). Ticks accumulate inside one frame window and flush once (`_flush_wheel_zoom` → single `_commitState`, source `"wheelZoom"` for a lone tick / `"wheelZoomCoalesced"` for a coalesced window) with the scrollbar set synchronously — no `singleShot(0)` roundtrip. No-change ticks at min/max stay silent. `zoomChanged` / `viewportChanged` / `viewportChangedState` contract, `fit_view` semantics, and public signatures are unchanged (wheel path never sets `_needs_fit_view`).

- **`ColorSettingsButton` uses `bind_auto_preview`** — `bind_flyout(..., side="above")` → `bind_auto_preview(..., side="above")` (with fallback). Hover/focus preview + Enter interactive + Esc/focusOut wiring now via `_AutoPreviewController` event filter, not per-anchor `enterEvent/leaveEvent/focusIn/keyPress/focusOut` duplication. Business signals (`elementHovered`, underline colors) kept.

- **Debug streams unified on env-gated helpers** (host `LOGGING.md` unique-prefix convention) — every subsystem stream is now a call-time `_xxx_debug_enabled()` / `_xxx_debug()` pair over `core.debug_flags` (permissive: any non-empty except `0/false/no/off`), off by default even under host `--debug`, existing `[prefix]` tags unchanged. New canonical `SLI_*` vars with legacy aliases: `SLI_NAV_DEBUG` (`UI_NAV_DEBUG`, shared with host router), `SLI_FLYOUT_DEBUG` (`IMGSLI_FLYOUT_DEBUG`, `FLYOUT_DEBUG`), `SLI_TIMELINE_DEBUG` (`IMGSLI_TIMELINE_DEBUG`, `IMGSLI_VIDEO_EDITOR_DEBUG`), `SLI_SCROLLBAR_DEBUG` (`IMGSLI_SCROLLBAR_DEBUG`), `SLI_DND_DEBUG` (`IMGSLI_DND_DEBUG`, `IMGSLI_IMAGE_COMPARE_DEBUG`, `IMGSLI_IC_DEBUG`); unchanged singles `SLI_UI_NAVLIST_DEBUG`, `SLI_UI_COLORS_DEBUG`, `SLI_RESIZE_DEBUG`. New shared helpers: `core/debug_flags.py`, `base_flyout/debug.py`, `timeline_widget/debug.py`.
- **No more host-app leaks in the toolkit** — `logging.getLogger("ImproveImgSLI...")` and import/call-time `logger.setLevel` mutations removed from all unified streams (timeline, flyout, DnD overlay, scrollbar, resize); `SLI_TOOLKIT_DEBUG` / `debug_env_var` handling in `core/logging.py` is now permissive like the rest (was strict `=="1"`).
- **Debug-stream follow-up: inspector / textview / marquee / tab-strip / context-menu gated** — the remaining ungated clusters converted to the same call-time `_xxx_debug_enabled()` / `_xxx_debug()` recipe (off by default even under host `--debug`): new `SLI_INSPECTOR_DEBUG` (`[inspector]`, `ui/inspector/tree.py` hover/cursor/gap traces), `SLI_MARQUEE_DEBUG` (`[marquee]`, marquee-band gesture — also deletes the `ImproveImgSLI.flyout` host-tree logger leak), `SLI_TABSTRIP_DEBUG` (`[TAB-BAR]` key trace kept, now gated), `SLI_CTX_MENU_DEBUG` (`[ctx-menu]` key traces, were fully ungated `logger.debug`); `SLI_TEXTVIEW_DEBUG` migrated from strict `== "1"` to permissive `any_flag` with `IMGSLI_TRACE` kept as legacy alias, new `[textview]` prefix, repaint/`_sync_height` warnings now stream-gated (none kept ungated); `ui/managers/realign.py` `[nav]` lines moved from raw `isEnabledFor(DEBUG)` gates onto the existing `SLI_NAV_DEBUG` stream. Stream table in `docs/dev/LOGGING.md` updated.
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

- **`TimelineWidget` paint contract + row virtualization (Phase A)** —
  `render.paint_timeline` no longer mutates geometry: the
  `update_vertical_scrollbar` call (which did `setVisible`/`setGeometry`/
  `widget.update`) moved out of the paint path — scrollbar sync lives only
  in the resize/settle/scroll paths (`resizeEvent`,
  `_onViewportGeometryChanged`, `_on_layout_settle`, `_on_scale_changed`,
  `_on_host_scroll`); the pure desired state is queryable via the new
  `viewport.vertical_scrollbar_state()`. Damage handling is formalized:
  `event.rect()` → `start_x`/`end_x` drives the strip frame range, ruler
  ticks, lane fills (now clipped to the damage instead of full-width),
  selection fill/handles, playhead, and the sticky-gutter vertical damage
  band. Rows paint through the new cached `layout.visible_row_window()`
  slice (offsets cached per `_row_layout` identity, O(visible) paint —
  both paint passes previously iterated the whole layout) with per-row
  horizontal culling via the new `layout.row_time_x_range()` (segment
  computation skipped when a row's keyframe content sits fully outside
  the damage). `widget._hover_points` is still rebuilt per paint but is
  hit-test scratch, not geometry, and is now damage-scoped. Signals,
  slots, and all public methods are unchanged. Covered by the new
  `tests/test_timeline_paint_contract.py` (no-geometry-mutation spies,
  narrow-damage subset, window-vs-brute-force, public-surface checks).

### Fixed

- **Timeline playhead without `updateState` spam** — smoothing is a `QVariantAnimation` value interpolator; the target-less `QPropertyAnimation` spammed `Changing state of an animation without target` on every start/stop.
- **Timeline curve center line stays visible** — drawn after the keyframe segments instead of under them (the 1.5px curve + dots buried it); lane substrate (light) is now grayish instead of near-white.
- **Timeline strip blocks overlap by 1px** — adjacent thumbnail draws now share one pixel so DPR rounding / smoothing fringes can no longer leave static background slivers at block seams (they do not scale with zoom, unlike content). Layout (`strip_block_layout`) stays exactly tiled; the neighbor simply wins the shared pixel.
- **Timeline strip debug audits its own coverage** — the `draw_strip` paint-debug block now logs per-block drawn rects (`block x/w drawn=`, full precision) plus a `strip_coverage` line (visible span vs union of drawn rects with explicit gap list), so background-showing gaps are distinguishable from dark scene content by geometry. Same change fixes the `draw_strip` format/args mismatch (`blocks=%s` without the arg crashed every paint's logging handler) and adds a regression test that formats every captured timeline record.
- **Timeline thumbnail strip uses fixed-width blocks (NLE-style)** — `draw_w` no longer oscillates `~base..base+slot` as the collapse quantum (`ceil(base/slot)`) crosses steps on zoom; while collapsed every block is exactly `base_tile` wide (zoom changes frames-per-block only), zoomed past 1:1 each block is exactly one slot wide. Paint (`render.draw_thumbnail_strip`) and generation priority (`viewport.get_visible_thumbnail_frame_indices`) now share one `viewport.strip_block_layout` helper, so both always agree; the `draw_strip` debug line reports `fpb` (frames per block) instead of the removed `step`.
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

### Fixed

- **Timeline sticky gutter no longer slides a frame behind on scroll sets** — the gutter is painted in content coords at `gx=scroll_offset` while every horizontal `setValue` moves the content widget window synchronously (Qt `scrollContentsBy`) and all correction paints were async `update()`. `_flush_wheel_zoom` now issues one synchronous band-only `repaint()` (`[scroll, scroll+LEFT_GUTTER+2] x [0, footer_top]` via the new `gutter_band_rect_for_scroll(widget, scroll)` helper in `timeline_widget/widget.py`) right after the programmatic scrollbar set, and `_on_host_scroll`'s scroll-changed path unions the same band into the damage for signals-live paths. Budget unchanged (one commit + one sync band repaint per coalesced window), emit contract / `fit_view` / strip layout untouched.

## 3.1.11

### Fixed
- Headless-CI double-click test coordinates were flaky; the probe now hits the widget's real centre instead of a display-dependent offset.

## 3.1.10

### Fixed
- `Button.sizeHint()` forwarding after the MRO change (the custom button lost its content-derived size hint).
- PySide6 multiple-inheritance memory corruption that could crash a dangling-widget test.

## 3.1.9

### Fixed
- Qt 6 `setFontFamily` deprecation warning.
- Windows QPainter access violations in the underline painter: `QPen` is out of the paint path (`fillPath`/`fillRect` instead).
- Crashing tapered arc: the manual segment loop was replaced with a `QLinearGradient` arc so the pen/brush cannot be GC'd mid-paint.
- `paintEvent` save/restore is now wrapped defensively in `Button` and `CustomLineEdit`.

## 3.1.8

### Fixed
- `QPen` GC access violation in `draw_bottom_underline`: the painter state is saved/restored around the call.

## 3.1.7

### Fixed
- Windows QPainter access violation in `Button.paintEvent`.

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