# Button region architecture

`Button` uses one region schema at runtime and in declarative specs.

## Single schema

| Layer | Role |
|-------|------|
| `ButtonRegion` (`regions.py`) | Sole config shape (~26 fields). Used by `Button(regions=[...])`, `update_region()`, `RegionHandle`, and `ButtonController.regions`. |
| `ButtonSpec.regions` (`specs.py`) | `tuple[ButtonRegion, ...]`. `from_regions()` / `to_regions()` are passthroughs. |
| `DrawContext.region_*` (`context.py`) | Paint-time projection filled in `Button.iter_regions()` from each `ButtonRegion`. |

Behaviors (`ClickBehavior`, `ToggleBehavior`, `LongPressBehavior`) are computed on
demand by `region_behaviors(region)` / `ButtonController.behaviors(...)` from the
region's own fields (`toggle`, `long_press`, `menu`, `action` /
`action_data` / `action_callback`). There is no separately stored behavior
spec that can drift from the region.

`action` / `action_data` / `action_callback` on `ButtonRegion` drive
`Button.actionTriggered` for both `regions=` and `spec=` / `from_spec(...)`
construction.

## Invariants

- Adding a region field is a one-place dataclass change plus paint/controller
  use sites — not a multi-schema copy list.
- Underline (`show_underline`, `underline_color`, `underline_thickness`) is
  stored on every region for imperative convenience, but only the `"_main"`
  region's values feed the underline layer (`layers/underline.py`, via
  `Button._make_context()`). Setting them on other regions is ignored.
- Prefer describing behavior with `ButtonSpec` / region fields; attach
  capabilities manually only for specialized internals.

## Out of scope (optional follow-ups)

- Moving underline fields off `ButtonRegion` onto a whole-button property.
- Changing how `DrawContext.region_*` is projected (still field-by-field from
  the single `ButtonRegion` source).

See also: [BUTTON_API.md](../user/BUTTON_API.md).
