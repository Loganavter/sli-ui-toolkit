# Overlays API

`sli_ui_toolkit.ui.widgets.overlays` — in-window modal surfaces, drag/drop
zone painters, and rubber-band selection, all built on one base class.

| Widget | Description |
|--------|-------------|
| `TopLevelInWindowOverlay` | Modal full-window in-window overlay that can host arbitrary `QWidget` content. Children can be placed by `OverlaySlot` around an anchor or with explicit overlay-local geometry. Emits `dismissed()`. |
| `OverlaySlot` / `OverlayItem` | Slot enum and item metadata used by `TopLevelInWindowOverlay`. |
| `DragDropOverlay` | Transparent drag/drop zone painter built on `TopLevelInWindowOverlay`; keeps pointer transparency and the existing `set_overlay_state(...)` API. |
| `MarqueeBandOverlay` | Pointer-transparent in-window selection rubber-band (not `QRubberBand` / not text `MarqueeDriver`). `set_band(rect)` / `set_accent(color)`. |
| `MarqueeBandGesture` | Wayland-safe drag tracker for `MarqueeBandOverlay` (app event filter; no `grabMouse`). Host supplies hit-testing via `on_update` / `on_finish` content-local rects. |
| `map_content_rect_to_window(...)` | Map a content-local rect into the host window, optionally clipped to a viewport widget. |

Drag ghosts for list pickers built on `ListPanel` are **host-owned** (Improve-ImgSLI
`ui/widgets/drag_ghost_widget.py` + `DragAndDropService`). The toolkit
`ToolkitDragDropService` coordinates drop targets without painting a ghost;
apps inject their service via `configure_toolkit(dragdrop_service_getter=...)`
— see [CONFIGURATION.md](CONFIGURATION.md).

`TopLevelInWindowOverlay(parent, *, anchor=None, close_on_background=True, close_on_escape=True, close_on_deactivate=True, default_distance=96)`
requires an in-window `parent` (raises otherwise). `DragDropOverlay` and
`MarqueeBandOverlay` are both thin subclasses that hardcode all three
`close_on_*` flags to `False` (they're painter-only, dismissed by their
owner, not by background/escape/deactivate) — only `parent` is meaningful
on their own constructors.

```python
from sli_ui_toolkit.widgets import DragDropOverlay, MarqueeBandGesture, TopLevelInWindowOverlay

overlay = TopLevelInWindowOverlay(
    window,
    close_on_background=False,  # keep open on outside click
    default_distance=64,        # px offset used by OverlaySlot placement
)

drop = DragDropOverlay(window)
drop.set_overlay_state(True, target_rect, horizontal=False, text1="Drop here", text2="")

gesture = MarqueeBandGesture(
    content_widget,
    clip_widget=viewport,       # hit-test/clip against this instead of content_widget
    min_drag_px=4,               # default: 3 — drag distance before a band starts
    on_update=lambda rect: ...,  # content-local rect while dragging
    on_finish=lambda rect: ...,
)
```

`MarqueeBandOverlay.set_accent(color)` overrides the band color (defaults
to the theme's `accent` token).

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
