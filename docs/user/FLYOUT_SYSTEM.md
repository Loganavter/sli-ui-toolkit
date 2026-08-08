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

#### Wayland: no `grabMouse` on in-window surfaces

In-window flyouts and overlays are ordinary `Qt.Widget` children of the host
window — **not** `Qt.Popup`. On Wayland, Qt prints

> This plugin supports grabbing the mouse only for popup windows

and the grab is a no-op if you call `QWidget.grabMouse()` / `releaseMouse()` from
that hierarchy (marquee drags, custom rubber-bands, drag previews, etc.).

For pointer tracking that must continue when the cursor leaves the origin
widget (or crosses a pointer-transparent overlay):

1. Prefer `WA_TransparentForMouseEvents` on the painted overlay so events keep
   hitting the content underneath, **or**
2. Install a short-lived `QApplication` event filter for the gesture; map with
   `event.globalPosition()` → target `mapFromGlobal(...)`.
3. Do **not** rely on `grabMouse()` unless the surface is a real `Qt.Popup`
   (see `ContextMenu` `surface="popup"` below).

Improve-ImgSLI’s Session Picker Recent shelf and any host list that needs
multi-select rubber-banding should use toolkit ``MarqueeBandOverlay`` +
``MarqueeBandGesture`` (public via ``sli_ui_toolkit.widgets``) instead of
``grabMouse`` or ``QRubberBand``.

```python
from sli_ui_toolkit.widgets import MarqueeBandGesture

gesture = MarqueeBandGesture(
    list_viewport_content,
    clip_widget=scroll.viewport(),
    on_update=lambda rect: preview_hits(rect),
    on_finish=lambda rect: commit_hits(rect),
)
# On empty-area left press (content-local):
gesture.set_accent(pastel_accent)
gesture.start(event.position().toPoint())
# Move/release are handled by the gesture's app filter.
```

Not the same as text ``MarqueeDriver`` / ``apply_marquee`` (scrolling labels).

### Manager

`FlyoutManager` is a singleton (`FlyoutManager.get_instance()`) that:

- tracks all live flyouts (`register_flyout` / `unregister_flyout`)
- applies a pluggable **show policy** on `request_show(f)` (default:
  exclusive — hide every other registered flyout and claim active). Hosts
  install `GroupShowPolicy` / a custom `FlyoutShowPolicy` via
  `FlyoutManager.set_show_policy(...)` so app groups can coexist without
  editing toolkit widgets. Widgets may expose an identity tag
  `flyout_group` (e.g. `ContextMenu` → `"context_menu"`, `UnifiedFlyout` →
  `"unified_list"`); the policy decides what that tag means.
- installs a global event filter that closes the active flyout on outside
  mouse press, window deactivate, and when the anchor widget moves
- snapshots anchor geometry so we can detect anchor movement reliably

Most callers never touch the manager directly — `BaseFlyout` plugs in
automatically.

#### Show policy (host-owned)

```python
from sli_ui_toolkit.managers import FlyoutManager, GroupShowPolicy

policy = GroupShowPolicy()
# Opening a context menu must not close the dual list.
policy.configure_group(
    "context_menu",
    dismisses=(),
    claim_active=False,
)
# Optional: one-off rule for a specific instance.
# policy.configure_flyout(special_flyout, dismisses=("unified_list",))

FlyoutManager.get_instance().set_show_policy(policy)
```

#### Group inheritance and coexistence

Groups can inherit another group's rules instead of repeating them, and two
groups can be declared as mutually non-dismissing without touching either
group's own `dismisses` set:

```python
policy = GroupShowPolicy()
policy.configure_group("context_menu", dismisses=(), claim_active=False)

# "submenu" has no rules of its own — it inherits context_menu's, recursively.
policy.define_group("submenu", parent="context_menu")

# A grandchild can still override one field and keep inheriting the rest.
policy.configure_group("submenu_item", parent="submenu", claim_active=True)

# Symmetric: opening either group never dismisses the other, regardless of
# what their own configured dismiss sets say.
policy.coexists_with("context_menu", "unified_list")

# coexists_with follows parent inheritance too -- submenu declares no
# coexists_with edges of its own, but inherits context_menu's:
# opening submenu never dismisses unified_list, and vice versa.
```

`configure_group`'s `dismisses` / `claim_active` / `parent` arguments are
each independently optional — passing only `parent=` sets the inheritance
link without writing default rules that would shadow the parent's.
`coexists_with` edges are looked up along the `parent` chain on *both*
sides of the pair, so a child group automatically inherits whatever
coexistence exceptions its ancestors declared — you don't need to repeat
`coexists_with` for every descendant group.

Stable toolkit ``flyout_group`` tags (identity only — hosts decide the rules):

| Widget | ``flyout_group`` |
| --- | --- |
| `ContextMenu` | `context_menu` |
| `UnifiedFlyout` | `unified_list` |
| `SimpleOptionsFlyout` | `options` |
| `IndexedToggleFlyout` | `toggle` |
| `IconActionFlyout` | `actions` |
| App `FontSettingsFlyout` | `font_settings` |

Unconfigured groups keep exclusive defaults. Pass `set_show_policy(None)` to
reset. A bare `(showing, other) -> bool` callable is also accepted.

#### Composing multiple policies

`set_show_policy` also accepts a `list`/`tuple` of policies, wrapped
internally in a `ChainShowPolicy`:

```python
from sli_ui_toolkit.managers import ExclusiveShowPolicy, FlyoutManager, GroupShowPolicy

app_specific = GroupShowPolicy()
app_specific.coexists_with("context_menu", "session_picker")

FlyoutManager.get_instance().set_show_policy([app_specific, GroupShowPolicy()])
```

- `should_dismiss` is **AND-combined**: `other` is only dismissed if *every*
  policy in the chain agrees to dismiss it, so any single policy can
  protect a pair (return `False`) and that protection wins regardless of
  what the rest of the chain says. This lets a host layer a small
  one-off `GroupShowPolicy` (or a bare callable) on top of another
  pre-configured policy without re-declaring all of its rules.
- `should_claim_active` is **priority-order**: the first policy's answer is
  used. Put the policy whose claim-active rules should win first in the
  list.
- Requires at least one policy; raises `ValueError` for an empty list.

#### Layer stack (z-order, host-owned)

`FlyoutManager.ensure_overlay_stacking` decides which visible flyouts get
raised above others when one of them opens or is re-raised (e.g. a list
refresh calling `raise_()`). Z-order is governed by a `LayerStack`: an
ordered list of layer names, with `flyout_group` tags assigned to a layer.
Flyouts in a higher layer are always raised above flyouts in a lower layer,
regardless of open order.

```python
from sli_ui_toolkit.managers import FlyoutManager, LayerStack

layers = LayerStack(order=("base", "popover", "context_menu"))
layers.assign_group("unified_list", "popover")
FlyoutManager.get_instance().set_layer_stack(layers)
```

The default `LayerStack` (installed automatically, no call needed) has
exactly two layers — `base` and `context_menu` — with `"context_menu"`
pre-assigned to the top one. This matches the toolkit's historical
hardcoded behavior exactly: hosts that never call `set_layer_stack` see no
difference. Unassigned groups default to the lowest (`base`) layer. Pass
`set_layer_stack(None)` to restore the default stack.

Two or more flyouts sharing the *same* non-base layer stack in
registration (open) order — first opened, first raised, so a later one
still ends up on top of an earlier one within that layer. This is tracked
separately from `FlyoutManager`'s internal registered-flyout set (a plain
`set`, whose iteration order is not meaningful on its own).

This is a separate axis from `GroupShowPolicy` above — layers only decide
*stacking order* among flyouts that are simultaneously visible; they don't
decide whether opening one dismisses another.

#### Linking (flyout families)

Groups and layers decide rules between *unrelated* flyouts. `link()` is for
the opposite case — a flyout that is logically part of another one (a
submenu, a color-picker opened from inside a settings flyout):

```python
FlyoutManager.get_instance().link(parent=settings_flyout, child=color_picker)
```

- Hiding `parent` — through any path (outside click, `close_all`, a
  group-policy dismiss, its anchor moving) — also hides `child`,
  recursively down a chain of links.
- Re-showing `parent` (e.g. a `pinned=True` HUD's `reposition()` call, which
  re-enters `request_show`) also calls `child.reposition()` if the child
  defines one and is currently visible — the host does not need to chain
  child repositioning by hand.
- Outside-click hit-testing needs no special handling: `FlyoutManager`
  already checks every visible *registered* flyout, not just the active
  one, so a click landing inside a linked child is "inside" for dismiss
  purposes as long as the child is a normal registered flyout — guaranteed
  for any `BaseFlyout` subclass, since it self-registers in `__init__`.
  This is a regression-tested guarantee
  (`tests/test_flyout_links.py::test_click_inside_linked_child_does_not_trigger_outside_dismiss`),
  not just an assumption about how `_contains_global` happens to be
  written.
- A child has at most one parent; calling `link()` again with a different
  parent replaces the old link. `unlink(parent, child)` removes it.
  `unregister_flyout` (called automatically when a `BaseFlyout` is
  destroyed) cleans up any links involving it.

### ContextMenu: in-window vs popup

Most flyouts stay in-window. `ContextMenu` also supports a per-instance
popup surface via ``ContextMenu(..., surface="popup")`` (or
`configure_toolkit(context_menu_surface="popup")` for a process-wide default):

| Surface | Rendering | Typical use |
| --- | --- | --- |
| `in_window` (default) | Overlay child on the host window | Button-anchored `show_aligned` / `popup_context_menu_for_anchor` |
| `popup` | Frameless `Qt.Popup` top-level (`popup_surface.py`) | Right-click `popup_at` (must stack above `UnifiedFlyout`) |

Popup menus skip OverlayLayer attach entirely (attach+detach reorders overlay
children and can shove open flyouts). They keep a QWidget parent / transient
parent so Wayland can place them at the cursor instead of screen-center. They
are not registered with `FlyoutManager`. Submenus inherit the parent menu's
surface.

On **Windows**, `bind_popup_transient_parent` does **not** call `winId()` /
`setTransientParent` when the host is translucent (`WA_TranslucentBackground`,
typical frameless CSD). That native link poisons DWM alpha for in-window
siblings of the host. Placement still uses `place_popup_at_global`.

Improve-ImgSLI opts into popup in `ContextMenuManager` (canvas / help ПКМ).
Mode-picker and title-bar menus stay in-window.

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
| `reposition()` | Replay the last `show_aligned` call (no animation). For `pinned=True` flyouts — see below. |
| `hide()` / `show()` | Standard. `hide()` is animated when the flyout was shown with `animation="slide"`. |
| `contains_global(p)` / `anchor_contains_global(p)` | Hit-tests for the manager. |
| `set_background_brush(brush)` / `background_brush()` | Override the panel fill — see "Custom surface style" below. |
| `set_border_color(color)` / `border_color()` | Override the panel's stroke color. |
| `set_shadow_color(color)` / `shadow_color()` | Tint the drop shadow. |

### Custom surface style (background / border / shadow)

Same shape as `Button`'s style API (`set_background_color`, `setBorderColor`,
`set_hover_color` in `style_api.py`): a plain setter storing an instance
override, `None` falls back to the theme token, and the setter repaints.
No QSS/dynamic-property dispatch here — `BaseFlyout` doesn't expose
Designer-style properties, these are plain attributes.

```python
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPixmap

flyout = MyFlyout(parent)

# Solid override (still theme-independent once set):
flyout.set_background_brush(QColor("#1c1c24"))

# Gradient ("glass" tint) — any QBrush/QGradient works. Use panel pixel
# coordinates (QLinearGradient's default coordinate mode) since the brush
# is painted directly on the flyout's own rect, not object-relative.
gradient = QLinearGradient(0, 0, 0, flyout.height())
gradient.setColorAt(0.0, QColor(255, 255, 255, 40))
gradient.setColorAt(1.0, QColor(255, 255, 255, 10))
flyout.set_background_brush(gradient)

# Stretch your own texture:
flyout.set_background_brush(QBrush(QPixmap("assets/noise.png")))

# Border + shadow tint:
flyout.set_border_color(QColor("#8888ff"))
flyout.set_shadow_color(QColor("#4444ff"))

# Back to theme defaults:
flyout.set_background_brush(None)
flyout.set_border_color(None)
flyout.set_shadow_color(None)
```

Notes:

- `set_background_brush` accepts a flat `QColor` (wrapped in a `QBrush`
  automatically), any `QGradient`, an existing `QBrush` (e.g. one built
  from a `QPixmap` for a repeating texture), passed through as-is.
- Texture/gradient brushes are anchored to the panel's own top-left corner
  (via `painter.setBrushOrigin`), not `(0, 0)` of the flyout widget — the
  widget is inset by `SHADOW_RADIUS` for the drop-shadow halo, so without
  this a texture would appear shifted from the visible panel.
- `set_shadow_color` only tints the RGB channels; the alpha falloff across
  the shadow's blur steps is unaffected (`draw_rounded_shadow`'s
  `alpha_max` — not currently exposed as a per-instance override, since
  nothing has needed it yet).
- **No real backdrop blur / frosted-glass**: this only changes what's
  painted *behind* the panel's own fill (solid/gradient/texture), not a
  live blur of whatever is rendered underneath it. A true "glass" effect
  needs the content behind the flyout captured and blurred every frame —
  expensive, and especially awkward over Improve-ImgSLI's QRhi canvas.
  Approximate it with a semi-transparent gradient/tint instead (see the
  gradient example above).

### Placement: `show_aligned`

`show_aligned` aligns a point on the **visible flyout panel** to a point on
the **anchor**. Both `anchor_point` and `flyout_point` are strings combining a
vertical token (`top` / `center` / `bottom`) and a horizontal token (`left` /
`center` / `right`); order doesn't matter, missing axis defaults to `center`.

`flyout_point` is measured on the opaque container **inside** the drop-shadow
halo (`SHADOW_RADIUS` on each side). Aligning the outer widget's `top-left`
would leave the panel shifted right/down by the shadow margin — that is why
`popup_context_menu_for_anchor(..., anchor_point="bottom-left",
flyout_point="top-left")` lines the menu panel up with the button, not the
shadow bitmap.

Default `anchor_point="bottom-center"`, `flyout_point="top-center"` → flyout
sits directly under the anchor, horizontally centered.

`offset` is the visible gap in pixels between the **anchor edge** and the
**outer flyout bounds** (including the drop-shadow halo). Content-point
alignment is then shifted by ``offset + SHADOW_RADIUS`` on the opening axis
so the opaque panel clears the anchor and the shadow does not paint over the
trigger button. The legacy `position=` path still subtracts `SHADOW_RADIUS`
when placing the outer widget rect.

Slide-in animation uses the same shadow inset: the start position is clamped
so the **opaque panel** does not begin inside the anchor (a raw
``final_y - dropdown_drop_offset_px`` start looks like a drop from the middle
of a short toolbar button).

If the preferred side does not fit (e.g. a dropdown near the bottom of the
window), placement **flips** to the opposite vertical side — same policy as
`place_surface_rect("bottom")` — instead of sliding the menu up over the
anchor.

Shorter `position=` forms are also accepted: `"top"`, `"bottom"`, `"left"`,
`"right"`, plus the corner variants (deprecated alias of the point API).

Animations:

- `"none"` — appears in place.
- `"slide"` — slides in from the opposite direction (e.g. with the default
  placement, slides down from above the final position).
  `animation_distance` controls how far it travels, `animation_duration_ms`
  the duration; both fall back to `get_flyout_timings()`.

### Pinned flyouts (persistent HUDs)

`BaseFlyout(parent, pinned=True)` opts a flyout out of every *passive*
auto-dismiss path in `FlyoutManager`:

- outside click / outside wheel no longer close it
- app/window deactivate no longer closes it
- its anchor moving or resizing no longer closes it (regular flyouts just
  hide when this happens — see `_close_flyouts_with_moved_anchors`)
- showing it does **not** dismiss other open flyouts and does **not** steal
  `FlyoutManager`'s "active" flyout slot, even though it still calls
  `show_aligned` internally (see below) — so repositioning it on every
  window resize can't interrupt an unrelated dropdown the user has open

It stays registered otherwise: `close_all()` still closes it, group/show
policy (`should_dismiss` when *another* flyout opens) still applies to it,
and it participates in overlay z-stacking (`ensure_overlay_stacking`).

#### Diagnosing unexpected pinned-flyout closes

Since a pinned flyout *should* rarely close, `FlyoutManager.request_hide`
logs a `DEBUG`-level message with a stack trace (`stack_info=True`) every
time one is hidden, on the `sli_ui_toolkit.ui.managers.flyout_manager`
logger. The manager can't tell an intentional app-level hide (e.g. "this
slot has no image") apart from a bug bypassing the pinned exemptions above
— both are just a `.hide()` call — so it logs instead of guessing. Enable
`DEBUG` on that logger (or the toolkit-wide `"sli_ui_toolkit"` logger, see
`configure_toolkit`/`setup_logging`) when a pinned HUD is disappearing
somewhere it shouldn't; the stack trace pinpoints the actual caller (a
one-off framework sweep like the `CustomTitleBar` Resize/Move bug fixed
below, versus your own intentional call site).

Because the manager no longer closes a pinned flyout when its anchor moves,
**the host is responsible for keeping it positioned**. Call `reposition()`
(replays the last `show_aligned(...)` call, forcing `animation="none"`) from
the same resize/move hooks that already track other anchored chrome:

```python
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

class InfoHUD(BaseFlyout):
    def __init__(self, parent, *, target_widget):
        super().__init__(parent, pinned=True)
        self._target = target_widget

    def show_on(self, target_widget):
        self.show_aligned(
            target_widget, "bottom-left", "bottom-left", offset=8
        )

# host resize/move handler:
hud.reposition()
```

`reposition()` is a no-op until the flyout has been shown once, if it is
currently hidden, or if the anchor widget was deleted.

This is meant for chrome that must always be visible while relevant (a zoom
percent chip, a resolution/filename readout) — not for anything the user
opens and expects to dismiss by clicking away, which should stay unpinned.

### Subclassing checklist

When you subclass `BaseFlyout`:

1. Use `add_section` / `add_row` / `add_widget` to populate `content_layout` —
   do not reach into `self.layout()` directly.
2. Don't repaint the surface — `BaseFlyout.paintEvent` already paints the
   shadowed rounded container. Need a different background/border/shadow?
   Use `set_background_brush` / `set_border_color` / `set_shadow_color`
   (see "Custom surface style" above) instead of overriding `paintEvent`.
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
| `row_widget(index)` | Live row button for Find Action / pulse (or `None`). |
| `set_max_visible_items(n)` | Cap visible rows before scrolling kicks in. |
| `set_row_height(h)` | Fixed row height in px. |
| `set_row_font(f)` | Override row font (use this to fix tiny text on dense parents). |
| `show_below(anchor, exact_width_match=True)` | Width at least the anchor (grows for long labels); centers under the combo. Prefer `show_aligned(..., bottom-left/top-left)` for narrow toolbar buttons. Content-only opens (`populate` + `show_aligned`) size to the longest label — no 180px floor. |

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
# create_double_list wires right-click → remove. Full hosts should connect
# item_context_menu_requested themselves and show a ContextMenu instead.
```

For full integration implement a store/controller pair conforming to its
protocols — see `unified_flyout/simple_adapter.py` for the minimal contract.
Right-click emits ``item_context_menu_requested(list_num, index)``; the host
owns the menu (copy path / properties / remove, etc.).
When constructing via `UnifiedFlyout(store, controller, main_window)` directly,
register the two list anchor widgets explicitly:

```python
flyout = UnifiedFlyout(store, controller, parent_window)
flyout.set_list_anchors(btn_image_a, btn_image_b)
```

Geometry, open-state sync, and double-mode layout all read from those anchors —
the flyout does not reach into application-specific `Ui_*` classes or widget
names.

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
