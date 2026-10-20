# Text Unification — one display widget (plan)

Status: in progress — P1-P2 landed, P3 caller waves running (see Progress log).
Target: a single painted text display widget, designed
like `Button` (one class + configuration, no subclasses). Inputs
(`CustomLineEdit` and everything built on it) are a different category
and out of scope.

## Why (the decision)

Three display widgets (`Label`, `TextView`, `HelpDocumentView`) paint
text with three behavior sets: caret blink exists only in code mode,
empty-click clears only in some paths, hover I-beam promises
unselectable space in document mode. Fixes have to be carried from one
to the other by hand. Raw paint cost is not the argument (text is
cheap); the split is functional — static (native Qt behavior for free)
vs interactive (toolkit rules) — but the interactive side itself is
split in two with no principled boundary. Hence: one widget.

Direction picked once, Button-style: `TextView` survives (a painted
canvas can shrink to static; a native `QLabel` cannot grow editing,
IME, or custom selection — the reverse migration is impossible).
`Label` and `HelpDocument*` become migration sources, then get
deleted. Where behaviors diverge, exactly one variant is kept (§6).

## 1. Single class + configuration (Button §1 mirror)

One class: `Text(QWidget)` — a plain widget, never a scroller.
Scrolling composes outside (host `QScrollArea`, as `Button` never
scrolls itself and `HelpDocumentView` already wraps its canvas).

Fixed in the class (never per-instance subclasses):

- `QWidget` identity; `paintEvent` → internal painter over a snapshot
  (Button: `Painter.paint(make_draw_context())`, `button.py:1065-1083).
- Signals: `linkActivated(str)`, `imageActivated(str)`,
  `selectionChanged`, `textChanged` (edit mode only). No `submitted` —
  submit is input semantics, kept out (as `Button` keeps menus
  app-owned, `BUTTON_API.md:602`).
- State properties + theme/scale connections + `destroyed` cleanup
  (Button: `button.py:459-490`).

Configurable per instance — three channels like `Button`
(`button.py:238-356`):

| Channel | Shape |
|---|---|
| Flat kwargs | `text/mode/formatting/editable/selectable/variant/...` (below) |
| `config=` | frozen `TextConfig` with `to_kwargs()` (mirrors `ButtonConfig`, `specs.py:141-197`; `Label` already has this shape as `LabelConfig`) |
| Modes, not subclasses | `mode="plain"` (static, `Label` parity) / `"document"` (markdown) / `"code"` (editable buffer). Micro-settings, not classes: `formatting=True/False`, `editable`, `selectable`, `word_wrap`, `elide`, `marquee`, `line_numbers`, `resolve_asset`, `show_toc=False` (TOC stays a separate list widget composed by hosts — as `ButtonFamily` composes buttons instead of absorbing them, `family.py`) |

Constructor sketch:

```python
Text("Caption", mode="plain", variant="body", pixel_size=16, elide=True)
Text(md, mode="document", formatting=True, selectable=True,
     resolve_asset=..., alignment="left")
Text(code, mode="code", editable=True, line_numbers=True)
Text("x", config=TextConfig(mode="plain", variant="body", ...))
```

Typography surface = `Label`'s, verbatim (variant registry, family,
pixel_size, bold/italic/underline/strike_out, color/color_token,
alignment, minimum_width/expanding): option names do not change, so
`Label(...)` call sites migrate mechanically to
`Text(..., mode="plain")`.

## 2. Layering (Button §2 mirror)

| Button seam | Text seam | Notes |
|---|---|---|
| `button.py` facade (signals/init/paint plumbing) | `text.py` facade | Same split: facade owns nothing but wiring |
| `state.py` (`ButtonState` + `StateSet`) | tiny `TextState` (`FOCUSED/SELECTED/EDITING` — vocabulary only) | Derived states stay in the snapshot |
| `controller.py` (runtime rects/states) | existing selection states, untouched | `DocumentSelection`/`TextSelection` already shared; no new machine |
| `context.py` (`DrawContext` snapshot + `effective_*`) | paint reads live widget state (text is cheap; no snapshot cache needed — unlike buttons, no per-state pixmap cache exists today) | Deliberate non-mirror: no problem, no cache |
| `painter.py` + `layers/` | content painters per mode (plain run / document layout / code buffer) + shared `CaretLayer`/`SelectionLayer` semantics | One blink controller + one empty-click rule consumed by all modes (§6) |
| `content.py` polymorphism | modes ARE the content polymorphism (`plain/document/code` ≈ `TextContent/RowsContent/IconContent`) | No second axis needed |
| `variants.py` registry | keep `Label`'s `LabelVariantSpec` registry, renamed to text variants | Same `register_variant` shape |
| `style_api.py` setters + Qt dynamic properties | keep `Label`'s setter surface (`setPixelSize/setBold/...`) + `TextView`'s (`set_markdown/enter_edit_mode/exit_edit_mode`) | Mechanical merge; dynamic-property bridge only where style needs it |
| `capabilities/` + `ButtonFamily` | nothing (display has no gestures beyond click/drag-select, already internal); TOC/search panels compose outside like `ButtonFamily` | Explicit non-mirror |

## 3. Extension without subclassing (Button §3 mirror)

- New **variant**: `register_text_variant(...)` (same shape as
  `register_variant`, `variants.py:87-89`).
- New **option**: ctor kwarg + setter + paint consumption (same 6-step
  recipe as Button options, minus `DrawContext`).
- New **content kind**: none — modes are closed (`plain/document/code`
  cover every current caller; a new kind is a plan-level decision).
- New **behavior**: internal (selection/caret/clipboard stay in the
  widget; hosts use signals). No `BehaviorSpec` equivalent needed.

## 4. Composition (Button §4 mirror)

- Regions-in-one-capsule → n/a (text has no sub-targets except
  links/images, already hit-tested).
- `ButtonFamily` → document chrome (TOC list, search field, lightbox)
  composes OUTSIDE the widget (as today in `MarkdownHelpDialog` /
  the app help dialog). The widget exposes `anchor_y`,
  `scroll_to_anchor`, `selected_plain_text`, `linkActivated`,
  `imageActivated` (all exist today across the two viewers — unified
  names in §5).

## 5. State machine (Button §5 mirror)

- Storage: existing selection states (`TextSelection` code,
  `DocumentSelection` document) + `editing` flag + focus (Qt).
- Writers: mouse (press/move/release), keys (edit mode), programmatic
  (`select_all_text/clear_selection`), `set_editing`.
- Consumption: paint gates (caret iff editing + focused + placed +
  blink-on + no active selection — already the rule post-#56).
- No snapshot cache (see §2).

## 6. Divergence resolutions (one variant each — decided, not proposed)

| Divergence | Kept | Dropped |
|---|---|---|
| Selection state | shared `DocumentSelection` / `TextSelection` | per-viewer machines (none remain) |
| Hit-test | strict glyph (`hit_test.py`, #57; whitespace counts) | full-block-width + clamp-to-nearest |
| Empty click | clear selection + drop caret (#56 code, doc already clears) | jump-to-nearest |
| Caret | blink while focused + editing (500 ms, `CustomLineEdit` parity, #56); document modes paint none | solid caret |
| Hover cursor | I-beam iff glyph hit, Arrow otherwise (#56 code; #57 doc via shared hit-test) | widget-wide I-beam |
| Tab-accept/Enter-submit | toolkit submit preset on the input side (#55); display widget has no submit | hand-rolled per-surface |
| Scrolling | host-composed (`QScrollArea`), widget is plain `QWidget` | `TextView(QScrollArea)` inheritance |
| Typography presets | `Label`'s variant registry shape | ad-hoc per-viewer tokens |
| Elide/marquee/wrap | options on plain mode (from `Label`) | n/a |
| Markdown figures/TOC/search/anchors | document options + externally composed panels (from `HelpDocumentView`) | second canvas implementation |

## 7. Migration map

| Today | Target | Notes |
|---|---|---|
| `Label(...)` (measured 2026-10-20, tests excluded: 27 toolkit sites / 10 files, 44 app `src` sites / 17 files) | `Text(..., mode="plain")` | kwargs overlap 1:1 by design; codemod-able. Gallery domain done (12 sites, app PR #429) |
| `TextView` code/edit (+ preview panel, inspector) | `Text(..., mode="code", editable=True)` | editor surface as-is, re-homed |
| `TextView` document (`MarkdownHelpDialog`, inspector) | `Text(..., mode="document")` | same |
| `HelpDocumentView` (app help dialog, topic search, image props) | `Text(..., mode="document", figures/links/search...)` + external TOC | last mover (richest surface) |
| `help_document/*`, `text_view/*` (old), `text_labels.py` | deleted | only after callers are gone + tests moved |
| `CustomLineEdit` family | untouched | input category, out of scope |

## 8. Phases + tests

- P0: this contract (review gate — merge this doc first).
- P1: `Text` skeleton (QWidget + typography/variant system + plain
  mode at `Label` parity) + `TextConfig`; no caller moves; new
  `tests/test_text.py` (parity vs `Label`: same text/options ⇒ same
  pixels/metrics).
- P2: document + code engines re-homed under `Text` (shared seams
  already exist: selection, hit-test, caret, hover); old classes
  become thin delegates (zero caller churn; old suites green).
- P3: caller waves (plain captions → document surfaces → app help);
  delete `help_document/*`, then `Label`, then old `TextView`.
  Each wave: moved tests, `API_CATALOG.md`, `CHANGELOG.md`.
- P4: close-out (unmerged-epics audit, ref prune).

Test strategy throughout: parity grabs (old vs new pixels for the
same options), falsification stories per new behavior (house rule),
`mypy` clean (CI gate), local-green merge signal while GH CI is
rate-limited.

## Progress log

- 2026-10-20 — **slice 3 (gallery domain, P3)**: 12 direct `Label(...)` sites
  migrated to `Text(..., mode="plain")` in `src/tabs/image_gallery/` (widget,
  stats_strip, clean_review, ask_ai, grid_view/series) via app PR #429.
  Parity proven before editing: offscreen probe, Label vs Text `sizeHint`
  identical for all 15 migrated parameter sets. Deliberately left: the
  `clean_review/populate.py` thumb placeholder (Label pixmap path) and the
  `ask_ai.py` result pane (`word_wrap` pin), plus toolkit `DropZoneLabel`
  subclasses. No `def/class` changes; `tests/contracts` green on the merged tree.
- 2026-10-19 — slices 1-2 (settings/export/help display labels) via app PRs
  #420 and #423.
- Retirement blocker measured 2026-10-20: **not only callers.** `Label`/
  `LabelConfig` are public exports (`widgets.py`) and
  `ui/widgets/text/variants.py` imports `LabelVariantSpec` from
  `atomic/text_labels.py`, so `Label` cannot be deleted before that seam moves.
  Remaining callers measured on the same day (`grep -rE "(^|[^A-Za-z_])Label\("`,
  tests excluded): app 44 sites over 17 files (image_compare primitives+layout,
  the video-editor dialog sections, gallery leftovers in ask_ai / clean_review
  populate / quick_look labels_theme / states / toolbar, session_picker,
  diagnostics dialog, the two shared dialogs, palette, colour picker, form
  controls, shelf, ui_inspector); toolkit 27 sites over 10 files (inspector
  rendering/code/tree/view, base_flyout builder, help_document view,
  marquee_text, custom title bar, text_labels itself).
- Document-surface slice (P3 tail) still open: `Text(mode="document")` hosts the
  engine but does not yet offer the HelpDocumentView-only surface (TOC, lightbox,
  scroll_to_text/scroll_to_anchor), so those callers stay on the old class.

## Open points (decided at P0 review, not later)

- Class name `Text` (proposed) vs keeping `TextView`: `TextView` lies
  (it will not be a scrolled view); `Text` matches `Button`/`Label`
  brevity. Rename cost is contained (new class; old names delegate
  then die in P3).
- Accessibility: painted text loses native `QLabel` screen-reader
  exposure unless `QAccessibleInterface` is implemented — recorded
  here as P1/P2 scope, not a veto.

## Audit findings (text-audit1, 2026-10-13 — accepted, cell removed)

Full report preserved at `~/.cache/opencode/text-audit-REPORT-2026-10-13.md`
(call-site tables omitted here; method documented in the report §8).
Binding deltas for the contract above:

- `alignment`: Qt flags, not strings (3 call sites; plan example
  corrected) — P1 must accept `Qt.AlignmentFlag`.
- QLabel getters on `Label` instances are load-bearing
  (`setWordWrap`/`setAlignment`/`setTextInteractionFlags` + getters,
  incl. tests): P1 `Text` must provide them (plain `QWidget` has
  none).
- `marquee`: zero callers in both repos — dropped from P1 scope.
- `register_text_variant` rename must update the app-side
  `icon_manager.py:17` import-time override (`group-title`).
- Inspector descriptors (`inspect_spec`/`widget_descriptor`) required
  on `Text`, or inspector registry tests break.
- `word_wrap` needs `heightForWidth`; `selectable` changes meaning
  (Qt-native → painted — 16 sites); `findChildren(QLabel)`
  consumers stop seeing migrated widgets.
- Document gaps for P2 (all nine, §2 table): public selection API
  names, `textContextMenuRequested`, `open_external_links`,
  `resolve_asset` ctor+setter, `scroll_to_text` (y-offset, not
  QWidget), `set_blocks`, anchor API unified on y, lightbox
  relocation, TOC single decision; plus `panel_fill`,
  `size_hint_from_content`, `line_number_start`, wheel-edge policy.
- P3 sizing: captions ≈92 sites + wrappers; documents 4 TextView +
  1 HDV + package; app help 5 files. `DropZoneLabel`/`_LinkLabel`
  need subclass-vs-compose decisions; `**kwargs` wrappers get
  explicit signatures on migration.
