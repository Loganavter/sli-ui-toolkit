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
  movement) is free to accept them — nothing else claims them by default.

**Correct examples:**

- `Slider` (`ui/widgets/atomic/slider.py`): Up/Down always `event.ignore()`,
  never `super()`'d. Left/Right are accepted for value-stepping (Slider is
  not a text field, so there's no cursor-movement conflict).
- `ComboBox` (`ui/widgets/comboboxes/combo_box.py`): Up/Down are consumed
  only `while self._expanded` (the dropdown is open) — idle, they fall
  through to routing.
- `SpinBox` / `DoubleSpinBox` (`ui/widgets/atomic/spinbox.py`): Up/Down
  always `event.ignore()`. Unlike `Slider`, SpinBox is a text field where
  Left/Right must stay cursor movement — value-stepping there uses
  PageUp/PageDown instead, which nothing else claims.

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

## 3. Contract test: `assert_yields_arrows_when_idle`

`tests/_nav_contract.py` provides `assert_yields_arrows_when_idle(make_widget)`:
constructs a fresh widget and asserts Up/Down are left unaccepted
(`event.isAccepted()` is `False`) in its idle state, using the same
trial-dispatch technique `ToolbarRowsSection._widget_handles` uses at
runtime. Add your widget to `tests/test_nav_arrow_key_contract.py` (or a
dedicated widget test module, wiring in the same helper) whenever you add
or touch a `keyPressEvent` override that mentions Up/Down or Left/Right —
this is what would have caught `SpinBox`'s bug before it shipped.

## 4. Checklists

**Adding a new widget with its own arrow-key handling:**

- [ ] Up/Down: `event.ignore()` unless you're in a transient state that
      legitimately owns them (document why, same as `ComboBox`'s
      `self._expanded` check).
- [ ] Left/Right: fine to accept unconditionally *unless* your widget is a
      text field (then they're cursor movement — use PageUp/PageDown or
      another key instead, see `SpinBox`).
- [ ] Add a case to `tests/test_nav_arrow_key_contract.py` using
      `assert_yields_arrows_when_idle`.

**Adding a new navigable page/toolbar:**

- [ ] Build rows with `NavRowBuilder`, not a hand-assembled list.
- [ ] Set `widget_descriptor.navigation` and call `register_navigation`
      instead of calling `NavigationManager.register()` directly.
- [ ] If your rows include content from an external contributor callback,
      make sure those rows go through `builder.extend(...)` — a
      contributor that adds widgets straight to a layout without going
      through the builder is invisible to keyboard navigation.
