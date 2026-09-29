# Overlays API

`sli_ui_toolkit.ui.widgets.overlays` — in-window modal surfaces, drag/drop
zone painters, and rubber-band selection, all built on one base class.

| Widget | Description |
|--------|-------------|
| `TopLevelInWindowOverlay` | Modal full-window in-window overlay that can host arbitrary `QWidget` content. Children can be placed by `OverlaySlot` around an anchor or with explicit overlay-local geometry. Emits `dismissed()`. |
| `OverlaySlot` / `OverlayItem` | Slot enum and item metadata used by `TopLevelInWindowOverlay`. |
| `DragDropOverlay` | Transparent drag/drop zone painter built on `TopLevelInWindowOverlay`; keeps pointer transparency and the existing `set_overlay_state(...)` API. |
| `MarqueeState` | Wayland-safe drag tracker (app event filter; no `grabMouse`). Content-local rects only — no overlay widget. Host supplies hit-testing via `on_update` / `on_finish` and paints the band itself. |
| `paint_marquee_band(painter, rect, accent)` / `marquee_dirty_rect(old, new)` | Band look (fill a48 + 1px border a200) + region-limited repaint helper for host `paintEvent`s. |

Drag ghosts for list pickers built on `ListPanel` are **host-owned** (Improve-ImgSLI
`ui/widgets/drag_ghost_widget.py` + `DragAndDropService`). The toolkit
`ToolkitDragDropService` coordinates drop targets without painting a ghost;
apps inject their service via `configure_toolkit(dragdrop_service_getter=...)`
— see [CONFIGURATION.md](CONFIGURATION.md).

`TopLevelInWindowOverlay(parent, *, anchor=None, close_on_background=True, close_on_escape=True, close_on_deactivate=True, default_distance=96)`
requires an in-window `parent` (raises otherwise). `DragDropOverlay` is a
thin subclass that hardcodes all three `close_on_*` flags to `False`
(painter-only, dismissed by its owner, not by background/escape/deactivate)
— only `parent` is meaningful on its own constructor.

```python
from sli_ui_toolkit.widgets import DragDropOverlay, MarqueeState, TopLevelInWindowOverlay

overlay = TopLevelInWindowOverlay(
    window,
    close_on_background=False,  # keep open on outside click
    default_distance=64,        # px offset used by OverlaySlot placement
)

drop = DragDropOverlay(window)
drop.set_overlay_state(True, target_rect, horizontal=False, text1="Drop here", text2="")

state = MarqueeState(
    content_widget,
    min_drag_px=3,               # tiny drags finish as an empty rect
    on_update=lambda rect: ...,  # content-local rect while dragging
    on_finish=lambda rect: ...,
)
```

`MarqueeState.set_accent(color)` pins the band color (default `#0078D4`); the
host passes it to `paint_marquee_band` in its own `paintEvent`.

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
