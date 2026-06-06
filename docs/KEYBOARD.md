# Keyboard Navigation & Focus Audit

Tracks the state of keyboard reachability, focus indicators, and key bindings
across toolkit widgets. The audit was performed against
`src/sli_ui_toolkit/ui/widgets/` (atomic, buttons, comboboxes, composite).

## Methodology

For each widget the audit checks:

- **Tab reachable** — does Tab / Shift-Tab move focus to the widget?
  (Qt default is `NoFocus` for `QWidget` subclasses unless a focus policy is set.)
- **Focus indicator** — is the focused state visually distinct?
- **Activation** — Space / Enter triggers the primary action.
- **Arrow keys** — relevant for lists, sliders, spin boxes, combo boxes.
- **Escape** — closes flyouts / dismisses dialogs.
- **`setFocusPolicy`** — explicit, not relying on platform default.

A widget is **OK** if all relevant checks pass for its role. **Fix needed**
marks a verified gap. **N/A** means the row does not apply (e.g. Escape on a
button).

## Findings Summary

| Widget | Base class | Focus policy set | Tab reachable | Activation | Arrows | Escape | Status |
|---|---|---|---|---|---|---|---|
| `Button` | `QWidget` | ✅ `StrongFocus` | ✅ yes | ✅ Space/Enter/Return | N/A | N/A | **Fixed** |
| `Switch` | `QWidget` | ✅ `StrongFocus` | ✅ yes | ✅ Space/Enter/Return | N/A | N/A | **Fixed** |
| `CheckBox` | `QCheckBox` | inherited | ✅ yes | ✅ Space (Qt default) | N/A | N/A | OK |
| `RadioButton` | `QRadioButton` | inherited | ✅ yes | ✅ Space (Qt default) | ✅ in group | N/A | OK |
| `Slider` | `QSlider` | inherited | ✅ yes | N/A | ✅ ←/→ (Qt default) | N/A | OK |
| `SpinBox` | `QSpinBox` | inherited | ✅ yes | N/A | ✅ ↑/↓ (custom, Shift = ×10) | N/A | OK |
| `TimeLineEdit` | `QLineEdit` | inherited | ✅ yes | N/A | ✅ custom (`keyPressEvent`) | N/A | OK |
| `CustomLineEdit` | `QLineEdit` | inherited | ✅ yes | N/A | ✅ caret (Qt default) | N/A | OK |
| `ComboBox` | `QComboBox` | ✅ `StrongFocus` | ✅ yes | ✅ Enter / Space | ✅ ↑/↓ | N/A | OK |
| `ScrollableComboBox` | `QComboBox` | ✅ `StrongFocus` | ✅ yes | ✅ Enter / Space | ✅ ↑/↓ | N/A | **Fixed** |
| `InstancesCounterButton` | `QWidget` | ✅ `NoFocus` (explicit) | ❌ by design | ⚠️ no key activation | N/A | N/A | **Fix needed** (clickable but not keyboard-activatable) |
| `BaseFlyout` / `SimpleOptionsFlyout` | overlay widget | ✅ `StrongFocus` | n/a | N/A | N/A | ✅ `Key_Escape` closes | **Fixed** |
| `IconActionFlyout` | overlay widget | ✅ inherited from `BaseFlyout` | n/a | N/A | N/A | ✅ inherited | **Fixed** |
| `IndexedToggleFlyout` | overlay widget | ✅ inherited from `BaseFlyout` | n/a | N/A | N/A | ✅ inherited | **Fixed** |
| `UnifiedFlyout` (bootstrap) | overlay widget | ✅ `StrongFocus` | ✅ yes | N/A | N/A | ✅ `Key_Escape` closes | **Fixed** |
| `SidebarNavList` | `QListWidget`-based | ✅ `NoFocus` | ❌ by design (use `IconListWidget`) | N/A | N/A | N/A | OK (deprecated path) |
| `IconListWidget` | `QListWidget` | inherited | ✅ yes | ✅ Enter (Qt default) | ✅ ↑/↓ (Qt default) | N/A | OK |
| `SidebarDialogShell` | `QDialog` | inherited | ✅ yes | N/A | N/A | ✅ Esc (Qt default) | OK |
| `MarkdownHelpDialog` | `QDialog` | inherited | ✅ yes | N/A | N/A | ✅ Esc (Qt default) | OK |
| `CalendarDayButton` | inherits `Button` | ✅ inherited from `Button` | ✅ yes | ✅ Space/Enter | N/A | N/A | **Fixed** (via `Button`) |
| `EditableListItem` | composite (`QWidget`) | ✅ `NoFocus` (Qt default) | ✅ via children | ✅ via child checkbox / button | N/A | N/A | OK (container is a layout shell; Tab walks `CustomLineEdit` → `CheckBox` → delete `Button` in layout order) |
| `TimelineWidget` | `QWidget` | ✅ `StrongFocus` | ✅ yes | ✅ Delete / Backspace = `deletePressed` | ✅ ←/→ frame, Shift+←/→ ×10, Home/End jump to bounds | N/A | **Fixed** |
| `LogConsoleWidget` output | `QPlainTextEdit` | ✅ `NoFocus` | ❌ by design | N/A | N/A | N/A | OK (read-only display) |

## Status

Fixes for items 1–4 in the priority list below have landed and are covered by
`tests/test_keyboard.py`. Item 5 (`InstancesCounterButton`) is deferred —
the widget is mouse-only by design.

Second pass (0.2.7) extended the audit into composite widgets:

- `EditableListItem` was re-classified from **Fix needed** to **OK**. The
  container intentionally has no focus of its own; Tab traverses its three
  child widgets (`CustomLineEdit`, `CheckBox`, delete `Button`) in layout
  order, all of which are individually focusable and keyboard-activatable.
- `TimelineWidget` previously had `StrongFocus` and a `deletePressed` signal
  but no `keyPressEvent` — keyboard users could focus the widget without
  being able to act on it. A `keyPressEvent` now maps Delete/Backspace →
  `deletePressed`, ←/→ → frame step (`headMoved`), Shift+←/→ → ×10 step,
  and Home/End → jump to bounds.

## Top-Priority Fixes

1. **`Button.keyPressEvent` + focus policy.** `Button` inherits `QWidget`, so it
   has no focus policy and no Space/Enter handling. Set
   `self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)` in `__init__`, override
   `keyPressEvent` to trigger `click()` on `Key_Space` / `Key_Return` /
   `Key_Enter`, and add a focused outline / ring in `ButtonPainter` driven by
   `hasFocus()`. (CHANGELOG 0.2.4 added `focused_underline_*` for inputs — a
   matching focus ring for `Button` belongs next to that.)
2. **`Switch.keyPressEvent` + focus policy.** Same gap as `Button`. Set
   `StrongFocus`, toggle on `Key_Space`, and paint a focus outline.
3. **Flyout Escape handling.** `BaseFlyout` (and the children that inherit from
   it) should handle `Key_Escape` to close the flyout. Today closing relies on
   outside-click / anchor-click; keyboard users cannot dismiss a flyout once
   focus is elsewhere.
4. **`ScrollableComboBox` Tab focus.** `ClickFocus` makes the widget
   unreachable via Tab. Switching to `StrongFocus` aligns it with `ComboBox`.
5. **`InstancesCounterButton` activation.** It is `NoFocus` by design but it
   is still an interactive trigger; either accept that it is mouse-only and
   document this, or give it `StrongFocus` + Space activation.

## Non-Issues / Confirmed OK

- `QSlider`, `QSpinBox`, `QLineEdit`, `QCheckBox`, `QRadioButton`, `QComboBox`,
  `QListWidget`, and `QDialog` give correct keyboard behavior out of the box;
  the toolkit subclasses do not regress them.
- `setFocusPolicy(Qt.FocusPolicy.NoFocus)` is intentional on
  `SidebarNavList`, the `LogConsoleWidget` output pane, and `UnifiedFlyout`'s
  bootstrap container — those are passive surfaces.

## Verification

After fixes land, walk through `python -m demo` with the keyboard only:

1. From each demo page, Tab through every visible interactive widget — a focus
   indicator must be visible at every stop, and Shift-Tab must reverse the
   order.
2. Activate buttons / switches / checkboxes with Space.
3. Adjust sliders with ←/→, spin boxes with ↑/↓, time inputs with ↑/↓.
4. Open a flyout, then press Escape — it must close.
5. Open `MarkdownHelpDialog`, navigate sections with Tab, dismiss with Escape.

Each fix should also extend `tests/test_widgets_smoke.py` with a focused
test using `pytest-qt`'s `qtbot.keyClick(widget, Qt.Key_Space)` to assert that
the widget reacts.
