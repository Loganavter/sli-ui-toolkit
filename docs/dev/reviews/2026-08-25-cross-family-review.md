# Code review 2026-08-25: cross-family audit

Four-pass read-only review (error handling, cross-family duplication/API
drift, threading + paint performance, test quality). Context-loaded from
AGENTS.md, ARCHITECTURE.md, DESIGN_LANGUAGE.md and the 2026-08-08
API_CONSISTENCY_AUDIT so already-fixed items were not re-reported.
Open items are tracked in [TODO.md](../TODO.md); every finding verified
against source (file:line).

---

## A. Error handling / silent degradation

Headline: only 33 of 284 modules define a logger; the dominant library
idiom is *fallback-to-default silently*, which hosts cannot debug.

| # | Finding | Where |
|---|---|---|
| A1 | Host-app fallback import: `from core.constants import AppConstants` resolves against the **host's** sys.path, fails always for Tkonverter, swallowed silently — hard-rule violation ("no fallback imports from hosts") | `ui/managers/auto_preview.py:100-105` (+ swallowing wrapper `navigation_manager.py:922-929`) |
| A2 | Missing theme token → silent black (`get_color` returns `QColor("#000000")`, no warning; `try_get_color` unused), plus dead except-wrappers leaving hardcoded hex fallbacks (`#aaaaaa`, `#00b7ff`, `#3b82f6`) | `theme_manager.py:188-201`; `drop_zone_label.py:65`; `list_panel/style.py:11`; `base_flyout/widget.py:233`; `help_document/view.py:305` |
| A3 | Failure ⇒ assume light theme (buttons/ripple/text_view only): `is_dark()` wrapped in bare except → light-theme rendering assumptions in a dark host | `buttons/variants.py:68`, `layers/ripple.py:213`, `text_view/highlight.py:120` |
| A4 | stderr instead of stdlib logging: `traceback.print_exc()` in Button.paintEvent (per paint frame!), generic_worker double-reporting, minimalist_scrollbar installs its own stderr handler | `button.py:781-784`; `generic_worker.py:53`; `minimalist_scrollbar.py:21` |
| A5 | Icon resolver failure → blank icons app-wide, zero diagnostics (same extension mechanism as config.py, opposite policy) | `icons.py:39-46` |
| A6 | Flyout family: four error-handling dialects incl. silent permanent deregistration of live flyouts on transient errors, private-state poking from custom_title_bar | `flyout_manager.py:456,141…`; `base_flyout/lifecycle.py`; `custom_title_bar/widget.py:352-367` |
| A7 | Bad enum-ish strings silently coerce to four different destinations ("below" ×2, center ×1, defaults ×1) | `auto_preview.py:38`, `navigation_manager.py:409`, `base_flyout/geometry.py:26`, `style_bridge.py:30` |
| A8 | Liveness-guard fragmentation (shiboken vs objectName-proxy vs conditional-import) + toast repositioning loop fully swallowed | `toast/manager.py:126-152`; idiom split `tooltips.py:138` vs `:203` |

Clean: zero `print(`; deprecations registry intact; config.py wrappers
logged correctly; button painter cleanup correct.

## B. Cross-family duplication & API drift

Verified already-consolidated (do not re-chase): flyout family all
subclasses BaseFlyout; atomic combobox shims intentional; buttons
content/regions/layers are layers not generations; help_document consumes
text_view; wheel policy centralized via WheelScrollPolicyMixin.

| # | Duplication | LOC | Risk |
|---|---|---|---|
| B1 | CheckBox ↔ RadioButton clone pair (hover property/anims/hit-test/rects byte-identical; sizeHint fudges and `_text_rect_available` already diverged) | ~130 | Med |
| B2 | ThemedWidget written to kill manual theme subscriptions but has **zero internal consumers**; 30 hand-rolled subs with three attribute names (`_theme`/`_theme_manager`/`theme_manager`) | ~60 | Med |
| B3 | WidgetDescriptor boilerplate copy-pasted in ~24 widget files; notification.py's copy already grew diverging fields | ~250 | Med |
| B4 | Dark-theme bypass: tab_bar `_palette()` falls back to hardcoded light hexes instead of palette defaults — light-mode colors render in dark mode if tokens omitted | ~10 | High (visual) |
| B5 | Fade builders triplicated around BaseFlyout (menu drifts OutQuad) instead of `make_fade_animation` | ~50 | Low-Med |
| B6 | markdown_help_dialog.py (530 LOC) legacy QTextBrowser dialog vs HelpDocumentView — demo-only users; verify Tkonverter before removal | 530 | Low |
| B7 | SpinBox ↔ DoubleSpinBox handler duplication (~45 LOC, routing contract copied verbatim) | ~45 | Low |
| B8 | Close-button hover forwarding implemented twice (adaptive_tab_strip vs top_tab_bar); signal naming camelCase vs snake_case coexisting even within one family (`rowClicked` vs `item_chosen`); style_api mixes `setBadge`/`set_override_bg_color` | ~30+API | Low |
| B9 | Shadow/scrim colors ignore `shadow.color` token; inline duration literals; `_lerp_color` duplicated | ~20 | Low |

Also: FAMILIES.md rows point at pre-package flat paths (stale only).

## C. Threading, event filters, paint performance

Toolkit echoes two host-bug shapes:

- **C1** `QApplication.processEvents()` inside flyout hide/focus-restore —
  runs at hover frequency, reentrancy hazard while half-torn-down
  (`base_flyout/lifecycle.py:523`).
- **C2** processEvents between `show()` and animation start in
  simple_options_flyout — user input processed before animation start pos
  is computed (`simple_options_flyout/widget.py:474`).

Paint-path costs (heaviest first):

1. **C3** text_view canvas: uncached regex re-tokenization per line per
   paint + ignores `event.rect()` — full repaint at input rate
   (`canvas_paint.py:39-43,127-136`; tokenizer `highlight.py:50`). Most
   likely visible jank in the toolkit (inspector code preview).
2. **C4** help_document canvas: `del event`, full-document repaint,
   `update()` per selection-drag mouse move (`help_document/canvas.py:224-235,278`).
3. **C5** Marquee: one 16 ms timer + per-frame font-metrics per label;
   N labels = N pipelines (`marquee_text.py:22,46`; `text_labels.py:292`).
4. **C6** Scrollbar viewport mask (QPainterPath→QRegion→setMask) rebuilt
   raw on every resize tick, undebounced (`minimalist_scrollbar.py:306-326`).
5. **C7** Tooltip process-wide interceptor inspects widgets (virtual
   `toolTip()` call) for every app event *before* checking event type —
   trivial reorder, app-wide win (`atomic/tooltips.py:106-112`).
6. **C8** NavigationManager sweeps `QApplication.allWidgets()` three ways
   per click/keyboard focus (`navigation_manager.py:568,593,684`).

Leaks/lifecycle:

- **C9** `FlyoutManager._registered_flyouts`: strong set, eviction only
  manual/RuntimeError — destroyed-without-unregister flyouts scanned on
  every press/wheel forever (`flyout_manager.py:29,144`). ContextMenu does
  it right (`menu.py:106 destroyed→discard`) — copy that.
- **C10** `NavigationManager._flyout_side` plain dict, no eviction hook
  (`:412`).
- ToastManager singleShot(0) storm on window resize/move without dedup
  flag (`toast/manager.py:158-166`); timeline stacks `singleShot(50,
  fit_view)` per show despite owning a SettleGate (`timeline_widget/
  widget.py:202`); LoadingSpinner never stops when hidden
  (`loading_spinner.py:53`).
- GenericWorker has no drain/inspect API — the exact shape that produced
  the host's `waitForDone` deadlock remains undetectable by hosts
  (`workers/generic_worker.py`).
- Also carries Improve-ImgSLI-specific semantics inside
  dragdrop_service.py (`list_num in (1,2)`, `image_number`) — hard-rule
  violation.

Sound: editable_text coordinator, combo filter pairing, gear_drag
cleanup, snapshot-fade pipeline, SettleGate, virtual_list pooling, ripple
self-stop, ui_font filter, in_window_overlay guards, i18n show-flush; no
waitForDone/os._exit/QGraphicsBlurEffect anywhere.

## D. Test quality (94 files, ~610 tests)

Highest-risk unpinned areas:

| Area | Pinned? | Silent-regression scenario |
|---|---|---|
| `ThemeManager._scale_qss_px` | none | regex stops matching `Npx` → whole-toolkit QSS unscaled at HiDPI in both hosts |
| Token resolution light/dark parity | palette contrast tests strong; widget-level resolution effectively one-theme | light-only token typo ships invisibly |
| `gpu_fill/widget.py` QRhi path | zero refs in tests AND demo | documented Windows see-through bug class returns |
| `WidgetDescriptor.from_inspect_spec` adapter | none | legacy `inspect_spec` hosts lose registration after refactor |
| `ToolkitDragDropService` lifecycle | indirect only | drag lifecycle breaks with no noise (+ host coupling violation) |
| UiScale defensive branches | happy path only | clamp change / NaN into QSS unnoticed |

Lifecycle: conftest enforces nothing; 244 `.show()` calls, only 28 files
use `qtbot.addWidget`; ≥6 files leak top-level windows every run
(`test_rounded_window_mask.py` leaks 3/run) — same Windows-AV class the
hosts already hit (host KNOWN_BUGS). Assertion-quality: smoke-only
`test_widgets_smoke.py:34`; `FakePainter` swallows everything but
drawText; getattr-defensively-consumed `_FakeFlyout` attributes make
drift fail soft by design. Good patterns worth copying: tolerant gap
asserts (`[0, spacing]`), docs-as-tests (`_nav_contract.py`,
`test_flyout_links.py`).

Top recommendations: (1) autouse cleanup fixture in conftest; (2) direct
`_scale_qss_px` golden tests; (3) parametrize token-resolution over both
themes; (4) pin `from_inspect_spec`; (5) structural gpu_fill test; (6)
drag-drop lifecycle coverage + de-host-coupling; (7) negative-path tests
(invalid theme/factor/unregister); (8) de-brittle internals-poking nav
tests.
