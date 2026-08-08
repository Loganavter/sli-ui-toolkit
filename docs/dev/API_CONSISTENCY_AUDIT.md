# API Consistency Audit (2026-08-08)

Findings from a documentation pass over the full public surface (see
[docs/user/API_CATALOG.md](../user/API_CATALOG.md) and its linked
per-family docs), plus one follow-up finding (#7) discovered while
verifying the first pass of fixes rather than during the original review.
This is an opinionated review, not a bug list — each item below is a
design tradeoff, not a crash. Grouped by status so it's clear what
actually changed vs. what's still a proposal.

## Done this pass

### 1. Silent exception swallowing in `config.py` host callbacks

**Finding:** `resolve_overlay_layer`, `create_rating_gesture`, and
`get_dragdrop_service` each wrapped the host-supplied callback in
`except Exception: return None` / fall back silently, with zero log output.
A broken `overlay_resolver` (say, a host app passes a callable that raises
on some widget type) degrades silently to "no overlay" with nothing in the
logs pointing at why.

**Fix:** added a module logger (`logging.getLogger(__name__)` →
`sli_ui_toolkit.config`, already captured by `setup_logging` per
[CONFIGURATION.md](../user/CONFIGURATION.md)) and a `logger.warning(...,
exc_info=True)` call in each of the three `except` blocks before falling
back. No behavior change for the happy path; failures are now diagnosable
instead of silent.

**Files:** `src/sli_ui_toolkit/config.py`,
`tests/test_config_callback_errors.py` (new — asserts the `WARNING` +
`exc_info` on each of the three failure paths, and that a *successful*
callback logs nothing).

**Verified this was the full extent of the pattern, not a guess:** grepped
all 103 `except Exception:` blocks in `src/sli_ui_toolkit` for ones
immediately preceding a call into a host-supplied `resolver`/`_factory`/
`callback`/`getter`-shaped name. Only the three above matched; the rest are
unrelated (Qt cleanup on possibly-deleted widgets, `shiboken.isValid`
guards, string `.format()` fallback in `i18n.py`, etc.) — not the same
silent-host-error anti-pattern, left untouched.

### 5. `RatingListItem` / `EditableListItem` not publicly exported

**Finding:** both are real, documented-in-CHANGELOG widgets
(`sli_ui_toolkit.ui.widgets.list_items`) but were never added to
`sli_ui_toolkit/widgets.py`'s import list or `__all__` — the only public
convenience surface. Neither name appeared anywhere in
`docs/user/API_CATALOG.md` before this audit either (`RatingListItem` was
listed under the wrong name, `RatingItem`; `EditableListItem` wasn't listed
at all). No circular-import reason for the omission — checked
`rating_item.py`'s own imports; it doesn't import `sli_ui_toolkit.widgets`.

**Fix:** exported both from `sli_ui_toolkit.widgets` (additive, no existing
import path removed — `sli_ui_toolkit.ui.widgets.list_items.RatingListItem`
still works). Updated
[LIST_ITEMS_API.md](../user/LIST_ITEMS_API.md) and
[API_CATALOG.md](../user/API_CATALOG.md) to document both, including
`EditableListItem`'s real signal (`delete_clicked` — there is no
`textChanged`/`deleteRequested`; connect to `item.input_field.textChanged`
directly for live text updates) and `get_value_data()`'s real key
(`"value"`, not `"text"`).

**Files:** `src/sli_ui_toolkit/widgets.py`,
`docs/user/LIST_ITEMS_API.md`, `docs/user/API_CATALOG.md`.

## Proposed, not started

These three are architecture-level and touch either a widely-called public
function or every widget module. Doing them well needs a version bump and,
for #2 especially, coordination with the host apps (Improve-ImgSLI,
Tkonverter) before landing — not something to change quietly inside a docs
pass. Recorded here so the tradeoff is written down instead of re-litigated
next time someone reads `config.py`.

### 2. `configure_toolkit` bundles 8 unrelated concerns

**Finding:** one function configures flyout/dropdown timing, in-window
overlay placement, the rating-item drag gesture factory, the drag-drop
service, context-menu rendering surface, button ripple duration, default
click deferral, and underline fade — none of which relate to each other
except "this is process-wide state." `config.py` as a module boundary is
organized by "when it's set" (all at startup), not by "what it's for."

**Why not fixed now:** `configure_toolkit(...)` is the single most-called
config entry point in host apps today (see `demo/main.py`). Any signature
change is either additive-only (which just grows the kwarg pile further)
or a breaking split (which forces every caller to update in lockstep with
a major version).

**Recommended plan, when there's appetite for a `0.4.0`-scale change:**
- Introduce narrower, focused functions that `configure_toolkit` internally
  delegates to, so both APIs work simultaneously during a deprecation
  window:
  - `configure_interaction(timings=None, ripple_duration_ms=None, default_defer_click=None, default_underline_fade=None)`
  - `configure_overlay(resolver=None)`
  - `configure_context_menu(surface=None)`
  - `configure_dragdrop(service_getter=None, rating_gesture_factory=None)`
- Keep `configure_toolkit(**kwargs)` as a documented thin compatibility
  shim (calls the four functions above) for at least one minor version
  past the split, then formally deprecate it via the existing
  `deprecations.py` registry (see #6).
- Land docs (`CONFIGURATION.md` already has per-parameter tables — those
  move almost as-is under the new function names) in the same change.
- Do **not** do this until it's motivated by a real pain point (a host app
  actually wanting to configure interaction without touching overlay
  wiring, e.g.); splitting a working, fully-optional-kwargs function for
  taxonomy alone is churn without payoff. Revisit if `configure_toolkit`
  grows a 9th unrelated parameter.

### 4. Enum vs. bare-string inconsistency across constructor kwargs

**Finding:** some options are real enums (`ClickBehavior`,
`CloseButtonPolicy`, `OverlaySlot`), a couple are `Literal[...]` type
aliases (`ContextMenuSurface`, `DEFER_CLICK_AWAIT_RIPPLE`), but most
string-valued options are untyped `str` with the allowed values living only
in a docstring or the docs pages written during this pass —
`Button(variant="surface")`, `IconListWidget(selected_icon_mode="invert")`,
`RatingListItem(item_type="image", position="middle")`,
`CustomLineEdit(alignment="left")`. A typo in any of these is caught at
runtime (if at all) instead of by a type checker or IDE autocomplete.

**Why not fixed now:** this spans effectively the whole widget surface.
Retrofitting `Literal[...]` onto existing `str` parameters is type-safe and
backward compatible (a `Literal["a", "b"]` still accepts any `str` at
runtime, mypy/pyright just narrow it), so it's actually a **safe, additive**
change unlike #2 — but it's ~20+ call sites across the codebase and needs
someone to actually enumerate the legal values per parameter correctly
from source, not guess.

**Recommended plan:**
- Adopt a project rule going forward: any new `str`-typed constructor kwarg
  with a closed set of valid values must be typed `Literal[...]`, not bare
  `str`. Add this to `AGENTS.md`'s "Good Defaults" section.
- ~~Retrofit existing ones opportunistically~~ **Done for the closed-set
  cases**, in one pass rather than opportunistically (explicit maintainer
  decision, see chat log):
  - `IconListWidget.selected_icon_mode: Literal["invert", "replace"]` —
    `sidebar_nav_list.py` (alias defined next to the widget; setter/getter
    and internal normalizer updated too).
  - `RatingListItem.position: Literal["first", "middle", "last", "only"]`
    (`RatingItemPosition`, `rating_item.py`) — also threaded through the
    one caller that constructs it, `unified_flyout/panel.py`.
  - `RatingListItem.item_type` / the `list_type` family:
    `Literal["image", "simple"]` (`ListItemType`, defined once in
    `unified_flyout/common.py` since the concept spans `rating_item.py`,
    `unified_flyout/delegate.py`, `panel.py`, `content.py`, `layout.py`).
  - `ButtonRegion.image_fill` / `PixmapContent.image_fill`:
    `Literal["cover", "contain", "stretch"]` (`ImageFill`, defined once in
    `buttons/content.py`, reused by `buttons/regions.py`).
  - `CustomLineEdit.alignment` (+ `SpinBox`, `TimeLineEdit` forwards):
    `Qt.AlignmentFlag | Literal["left", "center", "right"]`
    (`TextAlignment`, `custom_line_edit.py`) — this one was untyped
    entirely before (accepted a `Qt.AlignmentFlag` or a string alias, no
    annotation at all), not a `str`→`Literal` narrowing.
  - Verified additive/non-breaking: full test suite (370 tests) still
    green, mypy shows zero new errors on any touched file (pre-existing
    `ui/`-internals noise from item #7 unaffected).
- **Deliberately not touched:** `Button.variant` (and the same-shaped
  `WidgetStyleTokens.variant`, `Toast.variant`, Label `variant`) — these
  are backed by a runtime-extensible registry
  (`register_variant()`/`register_label_variant()`), so a closed
  `Literal[...]` would be actively wrong: it would reject variant names a
  caller legitimately registered at runtime. Needs a design decision
  (e.g. `Literal["default", "surface", "ghost"] | str` for editor
  hinting without a hard reject) before touching, not a mechanical swap.
- `ContextMenuSurface` was already a `Literal`, already colocated with its
  owning module — no action needed there.

### 3. Global singleton state instead of explicit dependency injection

**Finding:** `ThemeManager` (`get_instance()`), and every module-level
`_xxx` in `config.py`, `icons.py`, `i18n.py`, `buttons/feedback.py` are
process-wide mutable globals read implicitly by widgets at construction/
paint time. This is simple and matches "one desktop app, one process," but:
- two independently-configured widget subtrees in the same process (e.g.
  isolated test fixtures, or a plugin host embedding the toolkit twice)
  aren't possible without manual save/restore of every global;
  `tests/conftest.py` already has to do this kind of reset for the test
  suite to be independent test-to-test.
- nothing stops a widget from being constructed before its config hook
  ran, silently picking up defaults instead of erroring.

**Why not fixed now:** this is the deepest and riskiest item — every
widget file assumes `ThemeManager.get_instance()` and the `config.py`
globals are reachable from anywhere without being threaded through
constructors. Converting to explicit DI (an injected `ToolkitContext`
object) is a genuine major-version architecture change, not a patch.

**Recommended plan (not a commitment — needs a maintainer decision, not
just an audit note):**
- Do **not** attempt a blanket DI conversion. The realistic payoff (multi-
  context-per-process) doesn't clearly outweigh the cost (touching ~200
  files) for a toolkit whose only two consumers are single-window desktop
  apps today.
- If multi-context ever becomes a real requirement, the incremental,
  non-breaking path is: keep today's global-singleton API as the default
  (`ThemeManager.get_instance()` stays), but make `ThemeManager.__init__`
  itself fully independent of the singleton (already true — confirmed by
  reading `theme_manager.py`), so an app that *does* need isolation can
  construct its own `ThemeManager()` and pass it explicitly to whatever
  widgets accept a `theme_manager=` override, added widget-by-widget only
  where a real caller needs it. No global sweep required.
- Document the tradeoff explicitly in `CONFIGURATION.md`'s "Rules Of
  Thumb" section (single process-wide config, not a DI container) so it
  reads as an intentional design choice rather than an oversight.

### 7. `py.typed` was added without checking whether the codebase passes a type checker

**Finding:** added earlier in this doc pass (see CHANGELOG) as a "cheap,
pure-upside" item — but never actually ran a type checker before shipping
the marker. Checked it after the fact: a stock `mypy --ignore-missing-imports`
pass against `src/sli_ui_toolkit` finds **562 errors across 66 of 202
files**. Breakdown by top-level location:

| Location | Errors |
|---|---|
| `ui/` (internal widget implementation) | 661* |
| `i18n.py` (public top-level module) | 23 |
| `utils/`, `deprecations.py` | 1 each |

*(Some lines report more than one error, so the `ui/` line-count exceeds
the 562 distinct-file total — still the overwhelming majority of the
total.)*

Most of the `ui/` errors are `union-attr`/`attr-defined` on
`QWidget | None`-typed attributes — a common pattern in Qt code that
initializes widget-holding attributes to `None` and narrows them later,
which mypy flags by default without `--check-untyped-defs`/narrowing
help. Not necessarily *wrong* behavior, but it does mean `py.typed`
currently asserts "trust our types" for internals that were never
type-checked. The 23 errors in `i18n.py` are more concerning since it's a
public top-level module: `TranslationManager` assigns `self._cache`,
`self._events`, `self._current_lang`, etc. in a way mypy can't resolve to
declared attribute types (likely assigned dynamically outside
`__init__`, or through a decorator/metaclass mypy can't see through).

**Why not fixed now:** 562 errors is a real type-hygiene backlog, not a
five-minute fix, and much of it is internal-only (`ui/`) where a host
app's type checker never looks unless it reaches through
`sli_ui_toolkit.ui.*` directly — which the project's own docs already
discourage (`API_CATALOG.md`: "prefer `sli_ui_toolkit.widgets`"). Blindly
adding `# type: ignore` everywhere to make the count zero would be worse
than leaving `py.typed` honestly imperfect.

**Recommended plan:**
- Keep `py.typed` — PEP 561 doesn't require zero mypy errors, only that
  the package's own inline annotations are meant to be read by checkers
  rather than treated as absent. Removing it wouldn't fix anything, only
  hide the (currently accurate) signal that types exist and are
  best-effort.
- ~~Prioritize the public top-level modules first if this gets picked up:
  `i18n.py`'s 23 errors are the highest-value fix~~ **Done.** `i18n.py`'s
  22 errors (21 from `TranslationManager.__new__` assigning through
  `cls._instance._x` instead of a self-typed instance, 1 from an untyped
  `_shiboken = None` fallback assignment) are fixed: attributes are now
  declared with class-level type annotations and assigned via a local
  `instance` variable in `__new__`, and `_shiboken` gets an explicit
  `Any` annotation. `mypy src/sli_ui_toolkit/i18n.py --follow-imports=silent`
  is now clean. No behavior change; full test suite (370 tests) still
  passes.
- ~~Treat `ui/` internals as lower priority and fix opportunistically per
  file when touched~~ **In progress**, explicit maintainer decision to
  batch through it now rather than wait for opportunistic touches (chat
  log). Full test suite (370 tests) green after every batch — one
  regression caught and fixed mid-batch (see below), none shipped.
  - **Bonus finds, not just type-noise:** two real bugs surfaced by
    getting mypy to actually check these files, both pre-existing (not
    introduced by this pass):
    1. `timeline_widget/layout.py`'s `visible_keyframe_segments()`
       returned a bare tuple `(x, y, x, keyframe, keyframe)` for the
       single-keyframe case instead of the `dict[str, Any]` shape (built
       via `_segment_payload()`) that every caller (`render.py`) expects
       and indexes with `segment["x1"]` etc. — would have raised
       `TypeError: tuple indices must be integers` at runtime for any
       channel with exactly one keyframe. No test exercised this path
       (the toolkit's test suite doesn't cover `timeline_widget` at all).
       Fixed to route through `_segment_payload()` like every other
       branch.
    2. `help_document/canvas.py`'s `_sync_anchor_markers()` had two
       `for` loops both using the loop variable name `marker`; renaming
       the second loop's variable during the type-fix (to resolve a
       mypy type conflict between the two loops) exposed a latent
       `marker.show()` call at the end that was silently relying on the
       *first* loop's leftover `marker` binding rather than the
       newly-created/looked-up one in the second loop. Test suite caught
       it immediately (`UnboundLocalError` once renamed) — fixed by
       using the correct local (`anchor_marker.show()`).
  - Also fixed one place where mypy's typing actually caught a subtly
    wrong constraint: `ManagedFlyout` (a `Protocol` in `flyout_manager.py`)
    doesn't declare `contains_global`, so `flyout_timer_service.py`'s
    direct `child.contains_global(...)` call on a `Protocol`-typed value
    was only "working" because the whole block was wrapped in a blanket
    `try/except Exception`. Switched to the same `getattr(...)`-guarded
    pattern already used elsewhere in `flyout_manager.py` for the same
    optional-capability check — same runtime behavior, but no longer
    depends on an exception swallowing a `AttributeError` that a
    `Protocol` mismatch would otherwise always raise.
  - **Continued past the small files into the large mixin-composition
    ones** (explicit maintainer decision, see chat log). Progress overall:
    **562 → 222 errors, 65 → 23 files.**
  - `buttons/style_api.py` (77→0) and `buttons/events.py` (61→0): both are
    bare mixins (`_ButtonStyleApi`, `_ButtonEvents`) folded into
    `Button(QWidget, WheelScrollPolicyMixin, _ButtonStyleApi, _ButtonEvents)`
    — neither declares any base, so every `self.foo` that actually lives
    on `Button`/`QWidget`/the sibling mixin was unresolvable. **First
    attempt made both mixins inherit `QWidget` under `TYPE_CHECKING`
    (same trick as `ThemedWidget`) — this was wrong and caused a
    regression**: since `Button` itself already lists `QWidget` as a
    direct base, giving two more of its bases (`_ButtonStyleApi`,
    `_ButtonEvents`) their own separate `QWidget` ancestry made `Button`'s
    static MRO ambiguous, which cascaded into ~200 *new* errors across
    unrelated files that merely construct or subclass `Button`
    (`rating_item.py`, `calendar_widget/widget.py`, etc.). Reverted
    immediately (caught before commit, full-suite mypy re-run showed the
    spike). Correct fix: declare the missing attributes/methods as plain
    `ClassVar`-style annotations (`_controller: Any`,
    `update_region: Callable[..., None]`, etc.) directly on the mixin
    with **no base class change at all** — mypy resolves `self.x` from
    the annotation without touching `Button`'s real bases. The handful of
    cases that generically can't be expressed this way (`Signal.emit()`
    needs a real `QObject`-typed owner; `QWidget.mouseMoveEvent(self, ...)`
    static super-calls need a real `QWidget`-typed `self`) got narrow
    `# type: ignore[call-overload]` / `# type: ignore[arg-type]` comments
    instead — the standard, low-risk escape hatch for exactly this
    "mixin can't statically prove its host" situation.
  - `unified_flyout/` (6-way mixin: bootstrap/style/layout/refresh/
    content/dragdrop composed into `UnifiedFlyout(..., QWidget)`, plus
    `_UnifiedFlyoutBootstrapMixin` itself extending
    `_UnifiedFlyoutSessionMixin`): ~125 errors across `layout.py`,
    `content.py`, `dragdrop.py`, `refresh.py`, `session.py`, `bootstrap.py`
    → same root cause, same near-miss avoided. Fix: one shared
    `_UnifiedFlyoutBase` type-only class in `common.py` (plain attribute/
    `Callable` annotations, **no** `QWidget` inheritance) that every mixin
    now lists as a base; `UnifiedFlyout` itself gained zero new errors
    since `_UnifiedFlyoutBase` was never given a real Qt ancestor. Result:
    unified_flyout package errors 125 → 0 (13 remaining errors in
    `panel.py` are pre-existing and unrelated to the mixin split).
  - Runtime-verified both fixes directly (not just via the test suite):
    constructed a `Button` and a `UnifiedFlyout` in a live `QApplication`,
    printed `type(x).__mro__`, confirmed both are unchanged from before
    this pass and that `setEnabled`/`setBadge`/`set_regions` still work.
  - Two more incidental bug-shaped findings while narrowing types, both
    fixed: `Button.badge`/`setBadge()` were typed `int | None` while
    `ButtonRegion.badge` (the region-level source of the same value)
    allows `int | str | None` — widened `Button`'s badge typing to match
    rather than narrowing the region's (str badges already render fine
    via `str(self._badge)`, just weren't reachable through the type
    system). And `_ButtonEvents._defer_click_ms` was declared `int` during
    the mixin-annotation pass but the real value (`coerce_defer_click_ms`)
    is legitimately `int | None` (`None` = "emit synchronously") — fixed
    the annotation rather than the (correct) code.
  - Remaining ~222 errors, concentrated in `gpu_fill/liquid_glass_widget.py`
    (60), `comboboxes/capabilities/gear_drag.py` (38),
    `gpu_fill/widget.py` (27), `timeline_widget/render.py` (23), and a
    long tail of smaller files — not yet started.
- Do not add a CI mypy gate until the count is low enough that it's
  actually enforceable — an aspirational gate that's disabled from day one
  because it's red is worse than no gate.

## No action needed

### 6. `deprecations.py`'s centralized registry

**Finding:** this module (`DeprecationEntry` dataclass with `since`,
`remove_in`, `changelog` link, `warn_deprecated`/`warn_deprecated_symbol`
helpers) is genuinely good practice — a single source of truth for every
deprecated symbol's message, comparable to how larger libraries (pandas,
numpy) centralize deprecation warnings instead of scattering
`warnings.warn(...)` calls ad hoc through the codebase. Called out here as
a baseline to preserve, not change — future deprecations (including the
`configure_toolkit` split in #2, if it ever happens) should route through
this registry rather than inventing a new pattern.

**Action:** none. Noted so it doesn't get lost/reinvented later.

---

See also [ROADMAP.md](ROADMAP.md) for how these track against the release
plan, and [ARCHITECTURE.md](ARCHITECTURE.md) for the layering rules items
#2–#4 above would need to respect.
