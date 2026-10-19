# Keyboard navigation

Canonical reference for `NavigationManager` (`ui/managers/navigation_manager.py`)
and its consumers. Read this before adding a widget with its own arrow-key
handling, or a new navigable page/toolbar.

## 1. The trial-dispatch contract

`NavigationManager` installs an event filter on `QApplication` and owns
arrow-key consumption on it **exclusively** — no other event filter or
`keyPressEvent` override may consume arrow keys; they must let events
propagate to the manager (see the class docstring's stated contract).

Concretely, for any widget with its own `keyPressEvent` override:

- **Up/Down are never yours to keep**, even if your widget could plausibly
  do something with them. `NavigationManager` always consumes Up/Down for
  a widget owned by a registered `NavigationSection` (to avoid infinite
  re-delivery), so your widget's `keyPressEvent` never even sees them in
  that case — but a `ToolbarRowsSection` row still gives the focused widget
  *first refusal* via a synthetic trial-dispatch (see
  `ToolbarRowsSection._widget_handles`) before treating Up/Down as
  row-to-row movement. If your widget wants to intercept Up/Down for its
  own purposes in some *transient* state (e.g. a combo box's open
  dropdown), accept the event only in that state; otherwise call
  `event.ignore()` (do **not** call `super().keyPressEvent(event)` if the
  base class would accept it) so the key stays available for routing.
- **Left/Right are left alone by default** — native widget handling
  (`QTabBar`, text-cursor movement in an edit field, ...) gets them unless
  a `NavigationSection` opts in via `extra_keys` (e.g.
  `ToolbarRowsSection` uses Left/Right to move between buttons in a row).
  A widget with its own Left/Right behavior (value-stepping, cursor
  movement) may accept them — but a *value control* must gate that on the
  value-edit contract below instead of eating navigation keys.

### 1.1 The value-edit contract (a value changes only after an explicit Enter)

Owner request 2026-10-19: navigating must never change a value. A control
that steps a value with the arrow keys owns an explicit **edit mode**; until
the user enters it, arrows navigate the ring.

| State | Up / Down | Left / Right | Enter | Esc |
| --- | --- | --- | --- | --- |
| **Navigating** (idle, ring on the control) | move the ring (rows) | move the ring (inside the row) | **enter edit mode**, capture the entry value | — |
| **Editing** | adjust the value | adjust the value | **commit** and leave edit mode | **revert** to the captured value and leave |

- The control reports the state through a duck-typed `is_editing() -> bool`
  (implemented by `Slider`; WASD — `W/A/S/D` mapped to Up/Left/Down/Right —
  also adjusts while editing, for 2-D surfaces).
- A visible **editing affordance** is mandatory: the user must be able to
  tell "the focus ring is on this control" from "this control is being
  edited". Reuse the toolkit's focus-ring/state colours (`Slider` switches
  its groove border + thumb ring to the accent while editing; it does not
  invent a new look).
- The gate lives in the sections/flyout, not the control:
  `navigation_sections.arrow_gate_open(widget)` returns `False` while a
  control with `is_editing()` reports not-editing, so
  `ToolbarRowsSection`/`AutoNavigationSection` and the flyout's
  `_FlyoutNavigationSection` keep the arrow for ring navigation. A control
  **without** the `is_editing()` attribute keeps today's behaviour (gate
  open) — nothing else breaks.
- `Enter`/`Esc` are non-arrow keys: sections reach them natively, and a
  flyout gives its focused child first refusal for them (its `extra_keys`),
  so `Enter` enters edit mode even when the slider sits inside a flyout.

**Correct examples:**

- `Slider` (`ui/widgets/atomic/slider.py`): the value-edit contract above.
  While navigating it `event.ignore()`s **all four** arrows (Up/Down and
  Left/Right) so they stay available for routing; only inside edit mode does
  it step the value. `Enter`/`Esc` toggle/revert edit mode.
- `ComboBox` (`ui/widgets/comboboxes/combo_box.py`): Up/Down are consumed
  only `while self._expanded` (the dropdown is open) — idle, they fall
  through to routing.
- `SpinBox` / `DoubleSpinBox` (`ui/widgets/atomic/spinbox.py`): Up/Down
  always `event.ignore()`. Unlike `Slider`, SpinBox is a text field where
  Left/Right must stay cursor movement — value-stepping there uses
  PageUp/PageDown instead, which nothing else claims (so SpinBox does not
  implement `is_editing()` for the arrow gate).

**Negative example (fixed, kept here as the cautionary case):** `SpinBox`
used to unconditionally `setValue()` + `event.accept()` on Up/Down, with no
comment explaining why — unlike `Slider` two files over, which named the
contract explicitly. That silently made any `SpinBox` inside a
`ToolbarRowsSection` row permanently unreachable by row-to-row Up/Down.
Nothing caught it because no test asserted the *absence* of acceptance —
see §3's contract test for the fix.

## 2. Wiring a new page or toolbar

Three different questions come up, and they don't share one mechanism —
see `docs/legacy/plan_navigation_descriptor_unification.md` §1 for the
full rationale. Two are covered by toolkit APIs; the third is per-app.

### (A) "What are this page/toolbar's navigable rows, in order?"

Use `NavRowBuilder` (`ui/managers/nav_row_builder.py`) to accumulate rows
in construction order instead of hand-assembling a list at the end (the
old pattern, and the actual source of order-drift bugs — nothing enforced
that a hand-built list's order matched visual layout order):

```python
from sli_ui_toolkit.managers import NavRowBuilder, register_navigation

builder = NavRowBuilder(tag="settings-general")
lang_row = builder.row(lang_combo)          # wraps a bare widget/layout into a row
theme_row = builder.row(theme_row_widget)
builder.extend(extra_rows_from_a_contributor)  # absorb rows built elsewhere

section = builder.build(on_exit_left=sidebar_section.focus_first)
page.widget_descriptor = WidgetDescriptor(family="SettingsGeneralPage", navigation=section)
register_navigation(page)
```

`register_navigation(owner)` reads `owner.widget_descriptor.navigation`
(instance-level attribute first, then the class-level descriptor from
`@widget_descriptor`) and registers it with `NavigationManager`, returning
`False` harmlessly if there's nothing to register. Prefer this over calling
`NavigationManager.get_instance().register()` directly — it's the one
place every nav-participating widget in the app answers "do you have
navigation?" the same way.

### (B) "What is the app shell's fixed section registration order?"

Not a per-page pattern — a single, one-time, ordered manifest for the
whole app shell (main window title bar / tab strip / session picker, or
equivalent). This is app-specific, not a toolkit API: give it its own
small module in the host app with the ordering rationale written **once**,
and have startup call that one function instead of several separate
`register()` calls whose order is enforced only by a repeated comment.

### (C) "When may this control consume an arrow key itself?"

Not a registration problem — see §1. New widgets with in-widget arrow-key
behavior should follow the `Slider`/`ComboBox`/`SpinBox` pattern above and
add a case to `tests/test_nav_arrow_key_contract.py`.

### (D) Flyout side and focus — declarative, no 40+ lines

For any anchor→flyout, declare side and nearest focus on the flyout class,
and bind in one line — no manual `enterEvent/leaveEvent/focusIn/keyPress`:

```python
from sli_ui_toolkit.managers import bind_flyout, bind_auto_preview

class MagnifierColorOptionsFlyout(IconActionFlyout):
    _nav_side = "above"      # Up enters, Down exits (below→Down, left→Left, right→Right)
    _nearest_focus = True    # Up/Enter lands nearest to anchor, not always leftmost
    _nav_exit = "down"       # Down from any button → anchor (not only at edge)

# 1 line instead of 5× show_aligned + 90 lines handlers:
bind_flyout(btn, flyout, side="above")               # just side routing
bind_auto_preview(btn, flyout, side="above")         # + hover/focus/Enter/Esc auto
```

`BaseFlyout` reads `_nav_side`, `_nearest_focus`, `_nav_exit` (`lifecycle.py:270`, `widget.py:324`). `bind_flyout` sets `NavigationManager._flyout_side` + `FlyoutManager.link`; `bind_auto_preview` installs a single `eventFilter` on the anchor for preview (hover→`grab=False`, Enter/click→`grab=True`).

### (E) Any container — zero-config rows

For any container with many `StrongFocus` children (calendar, checkbox group, any grid), no manual rows:

```python
from sli_ui_toolkit.managers import auto_navigation, declare_navigation_rows

auto_navigation(calendar_widget)  # finds StrongFocus, clusters by y into rows, sorts by x
# or explicit rows if you already have row widgets:
declare_navigation_rows(owner, [row1, row2, row3], tag="my-panel")
```

Replaces `calendar_manager`/`checkbox_manager` — one generic `AutoNavigationSection` (`navigation_sections.py:413`) instead of 100 managers. For `IconList` use `IconListNavSection` directly.

## 3. Contract test: `assert_yields_arrows_when_idle`

`tests/_nav_contract.py` provides `assert_yields_arrows_when_idle(make_widget)`:
constructs a fresh widget and asserts the arrows are left unaccepted
(`event.isAccepted()` is `False`) in its idle state, using the same
trial-dispatch technique `ToolbarRowsSection._widget_handles` uses at
runtime. Add your widget to `tests/test_nav_arrow_key_contract.py` (or a
dedicated widget test module, wiring in the same helper) whenever you add
or touch a `keyPressEvent` override that mentions Up/Down or Left/Right —
this is what would have caught `SpinBox`'s bug before it shipped. A
value control that implements the value-edit contract (§1.1) must leave
**all four** arrows unaccepted while idle (`Slider` has its own
Left/Right case in that module); `tests/test_slider_edit_mode.py` drives
the full Enter/arrows/WASD/Enter, Esc and configurable-affordance contract
against real widgets.

## 4. Modal sections — overlays that own the keyboard

A section can claim *all* keyboard input for its window while it is up by
declaring an optional `modal` property (an attribute/property, never a
method):

```python
class VeilSection:
    @property
    def modal(self) -> bool:
        """True while this section must own ALL keyboard input for its window."""
        return True
```

While such a section is registered and its (QWidget) `owner` is visible, the
manager treats it as a **ceiling**:

- every arrow key, the section's `extra_keys`, and `Tab`/`Backtab` are routed
  into the ceiling section. A declined arrow at its edge is **consumed** —
  never handed to the neighbouring section and never bubbled natively to the
  widget behind the veil;
- `Tab`/`Backtab` cycle inside the owner's focus chain (owner + its
  descendants, filtered to `isVisible() and isEnabled() and TabFocus`),
  wrapping at the ends; an owner with no tab-focusable widget falls back to
  the section's `focus_first`. Tab/Backtab are **always** consumed;
- if a foreign widget behind the ceiling steals focus, the manager pulls it
  back with the section's `focus_first` after one event-loop turn (a widget in
  another top-level window is exempt);
- non-arrow `extra_keys` (`Esc`-like) are still offered to native handling
  *inside* the overlay.

Registration order is the veil boundary: sections registered **after** the
modal section sit **above** it and keep their normal behaviour, so a flyout
opened from inside the overlay still works; sections registered **before** it
are behind the veil and cannot be focused or navigated into. A section without
the attribute is non-modal (`getattr(spec, "modal", False)`). Hiding the modal
owner — or unregistering it — turns modality off again.

There is no public API for this: hosts only declare `modal`, while the ceiling
lookup (`_modal_ceiling`), effective-index resolution
(`_effective_section_index`), Tab ring (`_modal_tab_ring`) and deferred reclaim
(`_reclaim_modal_focus`) are private manager internals. Behaviour with no modal
section registered is unchanged.

## 5. Checklists

**Adding a new widget with its own arrow-key handling:**

- [ ] Up/Down: `event.ignore()` unless you're in a transient state that
      legitimately owns them (document why, same as `ComboBox`'s
      `self._expanded` check).
- [ ] Left/Right: a **value control** must gate on the value-edit contract
      (§1.1) — `event.ignore()` while navigating, accept only while
      `is_editing()`. Otherwise, Left/Right are fine to accept *unless* your
      widget is a text field (then they're cursor movement — use
      PageUp/PageDown or another key instead, see `SpinBox`).
- [ ] Add a case to `tests/test_nav_arrow_key_contract.py` using
      `assert_yields_arrows_when_idle` (value controls: all four arrows).

**Adding a new navigable page/toolbar:**

- [ ] Build rows with `NavRowBuilder`, not a hand-assembled list.
- [ ] Set `widget_descriptor.navigation` and call `register_navigation`
      instead of calling `NavigationManager.register()` directly.
- [ ] If your rows include content from an external contributor callback,
      make sure those rows go through `builder.extend(...)` — a
      contributor that adds widgets straight to a layout without going
      through the builder is invisible to keyboard navigation.

**Adding a modal overlay section:**

- [ ] Declare `modal` (property) returning `True` while the overlay is up,
      and give the section a `focus_first` that lands on a real control so the
      focus-reclaim has somewhere to go.
- [ ] Register it so anything that must stay reachable above it (a flyout
      opened from inside) is registered *after* it.
