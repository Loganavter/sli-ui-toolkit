# Development TODO

Shared engineering backlog. Completed work belongs in the living docs
(ARCHITECTURE, API_CATALOG, CHANGELOG), not here — entries get pruned once
`Done`. Priority markers: P1 (visible breakage for hosts), P2 (should be
planned), P3 (cleanup). Status: Open / In progress / Done / Blocked.

Source reviews: [reviews/2026-08-25-cross-family-review.md](reviews/2026-08-25-cross-family-review.md)
(A/B/C/D section references below).

## P1 - Hard-rule violations & host-visible silent failures (review A)

Status: `Done (2026-08-25 wave)` — A1-A5 closed; no host fallbacks, silent token/black & hardcoded-hex fallbacks now warn/palette-routed, tab dark bypass removed, icon blanks logged, stderr → logging.

- Host fallback `from core.constants import AppConstants` removed — host-agnostic `AutoPreviewConfig` + `get_flyout_timings()` injection, 400ms warn fallback (`ui/managers/auto_preview.py:30 AutoPreviewConfig`, `:65 injected delay`, `:131-143 logger.warning fallback`; `navigation_manager.py:922-929` wrapper also cleared — `grep -rn "from core.constants" src` 0).
- `ThemeManager.get_color` silent black + dead-except hardcoded hexes → warn + palette fallback (`ui/managers/theme_manager.py:188 get_color`, `:201 warning "unknown theme token"`, `:202-212 try_get_color + Window/WindowText/Base/Text fallback`); fallbacks now via palette: `ui/widgets/atomic/drop_zone_label.py:64-66 try_get_color("dialog.border")→"separator.color"`, `ui/widgets/composite/list_panel/style.py:12-14 try_get_color("accent")→get_color`, `ui/widgets/composite/base_flyout/widget.py:233-239 invalid focus-ring color warn + accent fallback`, `ui/widgets/composite/help_document/view.py:236-238 try_get_color("help.separator")→"dialog.border"`.
- Dark-theme bypass `tab_bar._palette()` hardcoded light hexes → theme-aware palette defaults (`ui/widgets/composite/adaptive_tab_strip/tab_bar.py:614 _palette`, `:618 color()` via `try_get_color`→`get_color` fallback; `strip/background/border/hover/text` now via `button.toggle.background.*`/`Window`/`separator.color`/`WindowText`).
- Icon resolver blank silently → `logger.warning` like `config.py` wrappers (`icons.py:39-46` → `src/sli_ui_toolkit/icons.py:40 warn blank mapped`, `:44 warn raise`, `:58 warn blank`, `:63 warn blank`, `:68-72 warn raise/blank`; `src/sli_ui_toolkit/ui/managers/icon_manager.py:0` no fallback import).
- stderr per-frame `traceback.print_exc()` → `logging` throttled (`ui/widgets/buttons/button.py:781 paintEvent` → `:30 throttle 5.0s`, `:789-795 logger.exception`/`logger.debug`; `workers/generic_worker.py:53` → `:57 logger.warning` + `traceback.format_exc()` via `error` signal; `ui/widgets/atomic/minimalist_scrollbar.py:21` → `:13 _sdbg_logger`, `:29 logger.debug`; `grep -rn "print_exc" src` 0).

## P2 - Reentrancy & lifecycle (review C)

Status: `Open`

- Drop `QApplication.processEvents()` from flyout hide/focus-restore
  (`base_flyout/lifecycle.py:523`; fires at hover frequency) and from
  simple_options_flyout show path (`widget.py:474`).
- Evict destroyed flyouts: `FlyoutManager._registered_flyouts` strong set
  without destroyed-hook (`flyout_manager.py:29`) — copy ContextMenu's
  `destroyed → discard` one-liner; same for
  `NavigationManager._flyout_side` dict (`navigation_manager.py:412`).
- Dedup ToastManager's singleShot(0) reposition storm
  (`toast/manager.py:158-166`); coalesce timeline's stacked
  `singleShot(50, fit_view)` via its own SettleGate
  (`timeline_widget/widget.py:202`).
- Tooltip interceptor: check event type before inspecting widgets
  (`atomic/tooltips.py:106-112`) — one-line reorder, app-wide win.
- NavigationManager allWidgets() sweeps per click → maintain a registry
  of `_keyboard_focus` holders (`navigation_manager.py:568,593,684`).
- Consider a drain/inspect API on GenericWorker so hosts can detect
  wedged workers (the shape behind the host's shutdown deadlock).

## P2 - Paint-path performance (review C)

Status: `Open`

Heaviest first:

1. text_view canvas: cache regex token spans per line (invalidate on
   text change), honor `event.rect()` clipping
   (`canvas_paint.py:39-136`, tokenizer `highlight.py:50` uncached).
2. help_document canvas: clip to exposed rect, stop full-document
   repaint per selection-drag mouse move (`canvas.py:224-235,278`).
3. Marquee: shared ticker for all drivers + cached text width instead of
   per-label 16 ms timers with per-frame font metrics
   (`marquee_text.py:22,46`).
4. Scrollbar viewport mask: debounce alongside `_queue_scrollbar_sync`
   or replace setMask with border-radius painting
   (`minimalist_scrollbar.py:306-326`).
5. LoadingSpinner: stop ticking while hidden (`loading_spinner.py:53`).
6. Button DrawContext/region-sort caching (`buttons/painter.py:36-87`)
   — moderate, whole-window-event cost.

## P2 - Duplication consolidation (review B)

Status: `Open`

- CheckBox ↔ RadioButton `_IndicatorButtonBase` extraction (~130 LOC;
  sizeHint fudges already diverged) (`atomic/checkbox.py` ↔ `radio.py`).
- WidgetDescriptor boilerplate ×24 files → `WidgetDescriptor.from_spec()`
  (~250 LOC; notification.py copy already diverging).
- Adopt ThemedWidget internally (30 manual theme subscriptions, three
  attribute names) for pure-repaint widgets at least.
- Route fade builders through `make_fade_animation`
  (simple_options_flyout, context_menu popup; reconcile OutQuad drift).
- SpinBox/DoubleSpinBox shared mixin (~45 LOC); close-button hover
  forwarding helper (×2); `_lerp_color` dedup.
- Naming drift decision needed: camelCase vs snake_case signals/APIs
  coexisting within families (`style_api.py`, simple_options_flyout);
  shadow/scrim colors → `shadow.color` token; inline duration literals →
  config/timings module.
- FAMILIES.md stale flat-file paths.

## P3 - Dead/demo-only code & host coupling (review B)

Status: `Blocked` (verify Tkonverter usage first)

- `markdown_help_dialog.py` (530 LOC, superseded by HelpDocumentView,
  demo-only users) and `process_console_widget.py` (272 LOC, demo-only)
  — verify Tkonverter, then deprecate via deprecations.py registry.
- Host coupling inside `dragdrop_service.py` (`list_num in (1,2)`,
  `image_number`) — violates "no host-specific logic"; parameterize.
- Liveness-guard convergence: pick shiboken6.isValid as the idiom
  (currently three idioms coexist); un-swallow toast repositioning loop
  (`toast/manager.py:126-152`).

## P2 - Test suite gaps (review D)

Status: `Open`

Ranked by silent-breakage risk:

1. Autouse widget-cleanup fixture in conftest.py (≥6 files leak top-level
   windows every run — known Windows-AV class from host KNOWN_BUGS).
2. Direct golden tests for `ThemeManager._scale_qss_px` (HiDPI QSS
   rewriting is unpinned; a regex regression blinds both hosts).
3. Parametrize widget-level token-resolution tests over BOTH themes.
4. Pin `WidgetDescriptor.from_inspect_spec` legacy adapter.
5. Structural test for `gpu_fill/widget.py` QRhi path (incl.
   releaseResources-before-initialize safety).
6. ToolkitDragDropService lifecycle coverage (+ fix its host coupling).
7. Negative-path tests: invalid theme name, UiScale garbage factors,
   unregistering unknown items.
8. De-brittle internals-poking navigation tests (`_instance = None`
   resets, private attr drives) → public API + reset fixture.
