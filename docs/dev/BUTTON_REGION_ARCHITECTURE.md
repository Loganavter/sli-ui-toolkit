# Button region architecture: problem, target, migration

## Problem

`Button` region config exists in three independently-maintained shapes that
describe the same data:

1. `ButtonRegion` (`regions.py`) — flat imperative dataclass, ~26 fields. This
   is what `Button(regions=[...])`, `update_region()`, and `RegionHandle`
   operate on, and it is the actual runtime storage
   (`ButtonController.regions: list[ButtonRegion]`).
2. `ContentSpec` / `RegionStyle` / `RegionSpec` (`specs.py`) — a "declarative"
   re-statement of the same fields, grouped, used only as the public shape of
   `ButtonSpec.regions` and rebuilt from `ButtonRegion` on *every* call to
   `set_regions()` (`ButtonSpec.from_regions()` inside
   `ButtonController.set_spec()`), even when no caller ever touched
   `ButtonSpec` directly.
3. `DrawContext.region_*` (`context.py`) — the paint-time projection, filled
   field-by-field in `Button.iter_regions()`.

`RegionStyle.from_region` / `RegionSpec.from_region` / `RegionSpec.to_region`
hand-copy every field between (1) and (2). Nothing enforces that the three
lists agree. A field added to `ButtonRegion` and not also added to these three
functions compiles, runs, and silently does nothing — this is exactly how
`corner_radii` shipped broken for months (see `test_button_regions.py`,
`test_button_region_round_trip_preserves_all_fields`, added as a guard after
the fact, not before).

A second, worse symptom of the same root cause: `ClickBehavior(action=,
callback=)` dispatch (`Button.actionTriggered`) only works through the
`ButtonSpec`/`RegionSpec` construction path. `ButtonRegion` (the path 90% of
call sites use) has no equivalent fields, so `RegionSpec.from_region()` always
produces a `ClickBehavior()` with `action=None`, and `_dispatch_region_behavior`
silently no-ops. The feature exists, is tested
(`test_button_spec_click_behavior_dispatches_action`), and is simply
unreachable from the imperative API — not documented as such, not enforced,
just quietly asymmetric.

Three fields (`show_underline`, `underline_color`, `underline_thickness`) have
the inverse problem: they exist on `ButtonRegion`/`RegionStyle` for *every*
region, but only the `"_main"` region's copy is ever read (underline paints
once for the whole button — see `layers/underline.py` and the 0.3.0
changelog fix). Setting them on any other region is accepted and silently
ignored.

## Root cause

Not the specific fields — the fact that there are three hand-synced schemas
for one concept, with no mechanism that fails loudly when they drift. A flat
26-field dataclass copied field-by-field into another dataclass, copied
field-by-field into a third, is a manual-sync problem disguised as a data
modeling problem.

## Target architecture

Collapse to **one schema**. `ButtonRegion` becomes the only representation;
`ContentSpec`, `RegionStyle`, `RegionSpec` are deleted, not kept as a second
form to synchronize:

- `ButtonSpec.regions: tuple[ButtonRegion, ...]` (was
  `tuple[RegionSpec, ...]`). `from_regions()`/`to_regions()` become identity
  operations — there is nothing left to drop, structurally, because there is
  only one shape.
- `ButtonController.behaviors(region_id, kind)` computes the
  `BehaviorSpec` tuple on demand directly from a `ButtonRegion`'s own fields
  (`toggle`, `long_press`, `menu`, and the new `action`/`action_data`/
  `action_callback` fields below) instead of reading a separately-stored
  `RegionSpec.behaviors` that was captured once at `from_region()` time.
  `region_specs: dict[str, RegionSpec]` is deleted along with it.
- `ButtonRegion` gains `action: str | None`, `action_data: Any`,
  `action_callback: ActionCallback | None` so `actionTriggered` dispatch is
  reachable from the imperative API too — closing the asymmetry instead of
  documenting it.
- The main-only underline fields keep the invariant enforced by
  `Button._make_context()` (only `"_main"`'s config feeds the underline
  layer); this doc does not change that, only records it as a known
  intentional asymmetry (a whole-button property that happens to be stored
  per-region for imperative-API convenience), not a hazard to add more
  Style-only fields next to.

## What this buys, concretely

- Adding a new region field is a one-line dataclass addition. There is no
  second or third place to remember to update, because there is no second or
  third schema.
- `test_button_region_round_trip_preserves_all_fields` becomes a tautology
  (identity function) rather than a regression guard for a manual copy — kept
  as a cheap smoke test that `ButtonSpec` round-trips at all, not because it
  is doing load-bearing work anymore.
- `action=`/`callback=` behavior dispatch works the same way regardless of
  whether a button was built via `regions=` or `spec=`.

## Migration (breaking, ships as a normal minor bump per this repo's
pre-1.0 convention — see `CHANGELOG.md` precedent: `scrollable=` and
`ContextMenu`/`QMenu` removals both shipped this way)

1. Delete `ContentSpec`, `RegionStyle`, `RegionSpec` from `specs.py`.
2. `ButtonSpec.regions` becomes `tuple[ButtonRegion, ...]`;
   `from_regions`/`to_regions` become passthroughs.
3. `ButtonController`: drop `region_specs`; `behaviors()` builds
   `BehaviorSpec` tuples directly from the matching `ButtonRegion`.
4. Add `action` / `action_data` / `action_callback` to `ButtonRegion`.
5. Update the one direct internal consumer of `RegionSpec`/`ContentSpec`/
   `RegionStyle` (`InstancesCounterButton._button_spec()`) to build
   `ButtonRegion(...)` directly.
6. Update `tests/test_button_regions.py` accordingly; update public exports
   (`buttons/__init__.py`, `sli_ui_toolkit/widgets.py`) to drop the three
   removed names.
7. `CHANGELOG.md` + version bump documenting the removal, same shape as prior
   breaking-change entries.

## Deliberately out of scope for this pass

- Making the main-only underline fields structurally main-only (e.g. moving
  them off `ButtonRegion` entirely). Worth doing, but it is an independent,
  smaller breaking change and shouldn't be bundled with the schema collapse.
- Any change to `DrawContext.region_*` — that projection is still built field
  by field in `iter_regions()`, but it now has exactly one source
  (`ButtonRegion`) instead of two, which was the actual duplication risk.
