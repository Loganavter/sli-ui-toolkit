# Flyout System

The toolkit ships several flyout primitives plus a singleton manager that
ensures only one flyout is open at a time and that flyouts close when their
anchor moves or the user clicks elsewhere. All flyouts are in-window: they are
reparented into an overlay layer on top of the host window, not native popup
toplevels. This keeps them inside the dialog/window decoration, prevents focus
issues on tiling WMs, and lets them inherit theming from the host.

Module map:

- `sli_ui_toolkit.ui.managers.flyout_manager` — `FlyoutManager` singleton
- `sli_ui_toolkit.ui.widgets.composite.base_flyout` — `BaseFlyout`
- `sli_ui_toolkit.ui.widgets.composite.simple_options_flyout` — `SimpleOptionsFlyout`
- `sli_ui_toolkit.ui.widgets.composite.icon_action_flyout` — `IconActionFlyout` + `IconAction`
- `sli_ui_toolkit.ui.widgets.composite.indexed_toggle_flyout` — `IndexedToggleFlyout`
- `sli_ui_toolkit.ui.widgets.composite.color_options_flyout` — `ColorOptionsFlyout`
- `sli_ui_toolkit.ui.widgets.composite.unified_flyout` — `UnifiedFlyout` (heavy: dual lists, drag-drop)

There is also an ad-hoc value popup attached to scrollable buttons — see
[Scroll-button value popup](#scroll-button-value-popup).

---

## Concepts

### Anchor

Every flyout is shown relative to an **anchor widget** — the button or input
that triggered it. The anchor is used for:

- placement (`show_aligned`, `show_below`, `show_above`, `show_for_button`)
- the close-when-anchor-moves heuristic in `FlyoutManager`
- hit-testing in `anchor_contains_global` (so a second click on the anchor
  does not immediately reopen what is being closed)

### Overlay layer

`BaseFlyout` reparents itself onto an overlay attached to the anchor's top-level
window via `attach_in_window_widget`. The overlay is transparent for input
outside the flyout container and stacks on top of normal widgets. This is what
makes the flyout visually "float" while remaining a child of the window.

### Manager

`FlyoutManager` is a singleton (`FlyoutManager.get_instance()`) that:

- tracks all live flyouts (`register_flyout` / `unregister_flyout`)
- enforces single-active: when `request_show(f)` runs, every other registered
  flyout is hidden
- installs a global event filter that closes the active flyout on outside
  mouse press, window deactivate, and when the anchor widget moves
- snapshots anchor geometry so we can detect anchor movement reliably

Most callers never touch the manager directly — `BaseFlyout` plugs in
automatically.

---

## BaseFlyout

`BaseFlyout(parent)` is the building block. `parent` must be a widget in the
target window — the overlay is derived from it. Subclass to build a custom
flyout, or use one of the prebuilt composites below.

### Useful API

| Method | Purpose |
| --- | --- |
| `add_widget(w)` | Append a raw widget to the content column. |
| `add_section(text, *, pixel_size=12)` | Bold heading row. |
| `add_row(label, widget, *, label_pixel_size=11, stretch_before_widget=True)` | Label on the left, widget on the right. |
| `add_radio_row(label, options, *, default=None)` | Label plus inline `RadioButton` group. Returns `(label, QButtonGroup, {value: RadioButton})`. |
| `make_color_swatch(color, *, size=28, alpha=True)` | Round color-picker swatch widget. |
| `show_aligned(anchor, anchor_point, flyout_point, *, position=None, offset=5, animation="none"\|"slide", animation_duration_ms=None, animation_distance=24, easing=...)` | The general placement primitive — described below. |
| `hide()` / `show()` | Standard. `hide()` is animated when the flyout was shown with `animation="slide"`. |
| `contains_global(p)` / `anchor_contains_global(p)` | Hit-tests for the manager. |

### Placement: `show_aligned`

`show_aligned` aligns a point on the **flyout** to a point on the **anchor**.
Both `anchor_point` and `flyout_point` are strings combining a vertical token
(`top` / `center` / `bottom`) and a horizontal token (`left` / `center` /
`right`); order doesn't matter, missing axis defaults to `center`.

Default `anchor_point="bottom-center"`, `flyout_point="top-center"` → flyout
sits directly under the anchor, horizontally centered.

`offset` is the visible gap in pixels between the anchor edge and the rendered
flyout edge along the natural axis between the two points (the shadow radius is
subtracted internally so the visual gap matches what you ask for).

Legacy `position=` is still accepted: `"top"`, `"bottom"`, `"left"`, `"right"`,
plus the corner variants.

Animations:

- `"none"` — appears in place.
- `"slide"` — slides in from the opposite direction (e.g. with the default
  placement, slides down from above the final position).
  `animation_distance` controls how far it travels, `animation_duration_ms`
  the duration; both fall back to `get_flyout_timings()`.

### Subclassing checklist

When you subclass `BaseFlyout`:

1. Use `add_section` / `add_row` / `add_widget` to populate `content_layout` —
   do not reach into `self.layout()` directly.
2. Don't repaint the surface — `BaseFlyout.paintEvent` already paints the
   shadowed rounded container.
3. Use `self.theme_manager` (it's a `ThemeManager`) for colors. The container
   restyles itself on theme change automatically.
4. Call `show_aligned` (or your own thin wrapper around it) when opening.
5. If you store an extra anchor-related state, clean it up in `hide()` or
   `hideEvent`.

---

## Prebuilt flyouts

### SimpleOptionsFlyout

A scrollable list of single-line option rows. Click a row → emits
`item_selected(int)` and hides.

```python
from sli_ui_toolkit import SimpleOptionsFlyout

flyout = SimpleOptionsFlyout(parent_widget=window)
flyout.populate(["Nearest", "Bilinear", "Bicubic"], current_index=1)
flyout.item_selected.connect(lambda i: ...)
flyout.show_below(combo_anchor, exact_width_match=True)
```

| Method | Purpose |
| --- | --- |
| `populate(labels, current_index=-1)` | Set items and selection. |
| `set_max_visible_items(n)` | Cap visible rows before scrolling kicks in. |
| `set_row_height(h)` | Fixed row height in px. |
| `set_row_font(f)` | Override row font (use this to fix tiny text on dense parents). |
| `show_below(anchor, exact_width_match=True)` | Convenience over `show_aligned`. |

### IconActionFlyout

Horizontal strip of icon buttons. Use it as a contextual "more actions" panel
floating next to a target widget.

```python
from sli_ui_toolkit import IconAction, IconActionFlyout
from sli_ui_toolkit.icons import AppIcon

flyout = IconActionFlyout(parent_widget=window)
flyout.set_actions([
    IconAction(id="copy", icon=AppIcon.COPY, tooltip="Copy"),
    IconAction(id="delete", icon=AppIcon.TRASH, tooltip="Delete", destructive=True),
])
flyout.action_triggered.connect(lambda action_id: ...)
flyout.show_above(target_widget)
```

| Method | Purpose |
| --- | --- |
| `set_actions(actions)` | Replace the row of buttons. `IconAction` carries `id`, `icon`, `tooltip`, optional `enabled`, `checked`, `destructive`. |
| `action_button(action_id)` | Return the underlying `Button` for further tweaking. |
| `set_action_state(action_id, *, enabled=None, checked=None, tooltip=None)` | Mutate one action without rebuilding. |
| `schedule_auto_hide(ms)` / `cancel_auto_hide()` | Optional timeout-based dismissal — useful for transient feedback. |

### IndexedToggleFlyout

A row of buttons indexed `1..N`, each representing a "slot". Used for picking
images, presets, or any small fixed set.

| Method | Purpose |
| --- | --- |
| `set_slot_count(n)` | Resize the row. |
| `set_slots([(label, payload), ...])` | Per-slot label + opaque payload. |
| `buttons()` | Tuple of underlying `Button`s. |
| `show_for_button(anchor, ...)` | Convenience placement. |

### ColorOptionsFlyout

Color picker with a swatch grid + recent colors + an opacity slider. Inherits
the BaseFlyout shape; emits `color_selected(QColor)`.

### UnifiedFlyout (heavy)

A two-column drag-drop-capable list selector. Substantially larger surface
than the others; intended for the "swap image 1/2" UI in Improve-ImgSLI.

Quickstart for the standalone form:

```python
from sli_ui_toolkit import UnifiedFlyout

flyout = UnifiedFlyout.create_double_list(
    parent_window=window,
    anchor_left=btn_image_a,
    anchor_right=btn_image_b,
    left_items=["A.png", "B.png"],
    right_items=["C.png", "D.png"],
    current_left=0,
    current_right=1,
)
flyout.item_chosen.connect(lambda side, idx: ...)
```

For full integration you'd implement a store/controller pair conforming to its
protocols — see `unified_flyout/simple_adapter.py` for the minimal contract.

---

## Practical recipes

### "Open one, close everything else"
Don't track open state yourself. Just call your flyout's `show_*` method;
`FlyoutManager` hides whichever flyout was previously active.

### Closing on anchor movement
Resize a column, drag the window, scroll the toolbar → the anchor's screen
position changes. `FlyoutManager` snapshots the anchor rect on show and
periodically rechecks; if it has moved by more than a small threshold it
closes the flyout. You get this for free as long as your subclass returns its
anchor widget(s) from `anchor_widgets()` (BaseFlyout already does this for the
widget passed to `show_aligned`).

### Custom dismissal
Override `hide()` or `hideEvent()` to commit pending state, but **always** call
`super().hide()` (or the `BaseFlyout` hide animation will be skipped and the
manager will not get the visibility change).

### Reusing one instance
Construct once, populate per show. All prebuilt flyouts are reusable; rebuild
content via their `populate` / `set_*` methods rather than tearing the widget
down.
