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
- Retrofit existing ones opportunistically — when a widget file is touched
  for an unrelated change, upgrade its string kwargs to `Literal[...]` in
  the same PR, rather than a single giant sweep PR that touches everything
  at once (matches the existing `ThemedWidget` migration pattern already
  used in `docs/dev/ROADMAP.md`'s "fold onto ThemedWidget when touched"
  item).
- Candidates identified so far (non-exhaustive): `Button.variant`,
  `IconListWidget.selected_icon_mode`, `RatingListItem.item_type` /
  `.position`, text-input `alignment` parameters, `ContextMenuSurface`
  (already a `Literal`, just move it next to the others for consistency).

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
- Prioritize the public top-level modules first if this gets picked up:
  `i18n.py`'s 23 errors are the highest-value fix (small file, genuinely
  public, all clustered around `TranslationManager`'s attribute
  declarations — likely fixable by declaring the attributes with real
  types in `__init__` instead of wherever they're currently first
  assigned).
- Treat `ui/` internals as lower priority and fix opportunistically per
  file when touched, same policy as item #4's `Literal[...]` retrofit.
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
