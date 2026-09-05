# Logging Convention

The toolkit's shared logging convention. Host-agnostic: the implementation
lives in `sli_ui_toolkit.core.logging` and `sli_ui_toolkit.core.debug_flags`,
and every host app gets the same behavior through one call.

- Convention implementation: [`core/logging.py`](../../src/sli_ui_toolkit/core/logging.py),
  [`core/debug_flags.py`](../../src/sli_ui_toolkit/core/debug_flags.py)
- Host-side setup reference: [../user/CONFIGURATION.md](../user/CONFIGURATION.md) §5

## stdlib `logging` exclusively

Committed code uses Python's stdlib `logging` — **never `print()`**.
One configured pipeline (level filter, console + file handlers, consistent
format) means output can be silenced or amplified without touching source.

## Logger trees and `setup_logging`

Library code always uses `logging.getLogger(__name__)`, per normal library
practice. Every record therefore lives under the `"sli_ui_toolkit"` tree.

A host app bridges that tree into its own output with one call, first at
startup so early warnings are captured:

```python
from sli_ui_toolkit import setup_logging

setup_logging("MyApp", debug_enabled=False, debug_env_var="MYAPP_DEBUG")
```

`setup_logging(app_name, ...)` attaches the **same handlers** (stderr stream
+ file, uniform formatter) to **both** the logger literally named
`app_name` and the toolkit's `"sli_ui_toolkit"` logger. The two trees are
siblings, so no line is emitted twice. A dotted host submodule
(`"MyApp.xxx"`) propagates up to the host logger; `sli_ui_toolkit.*`
modules propagate up to the toolkit logger.

**If skipped:** toolkit records still go through `logging` but have no
handler attached anywhere — they are silently dropped. `setup_simple_logging(app_name, level)`
is a lighter alternative for simple scripts (root logger + stderr only, no
file handler).

## Level model

- The **host tree** is host-controlled: `debug_enabled`, optionally
  overridden at call time by `debug_env_var` (env set → `DEBUG`).
- A `<DEBUG_VAR>_SUPPRESS_DEBUG` override always wins: `setup_logging`
  derives it from `debug_env_var` by replacing `_DEBUG` with
  `_SUPPRESS_DEBUG`; when set, the level is forced back to `INFO`.
- The **toolkit tree stays `INFO` under host `--debug`**. It reaches
  `DEBUG` only through the permissive `SLI_TOOLKIT_DEBUG` env gate
  (any non-empty value except `0`/`false`/`no`/`off`). Noisy subsystem
  traces must never ride the global debug switch.
- Central `setLevel` lives **only** in `setup_logging` (plus
  `setup_simple_logging` for its own root-logger wiring). No other module
  may set levels.

## Unique-prefix env-gated streams

A subsystem with its own conditionally-enabled debug stream follows this
recipe — a `_xxx_debug_enabled()` / `_xxx_debug()` pair over
`core.debug_flags`, checked at **call time**, every line tagged with a
unique bracketed prefix, **off by default even under host `--debug`**:

```python
from sli_ui_toolkit.core.debug_flags import any_flag

def _xxx_debug_enabled() -> bool:
    return any_flag("SLI_XXX_DEBUG")

def _xxx_debug(message: str, *args) -> None:
    if _xxx_debug_enabled():
        logger.debug("[xxx-debug] " + message, *args)
```

Permissive semantics (`env_flag` / `any_flag`): any non-empty value except
`0`/`false`/`no`/`off` counts as set (`=1`, `=yes`, … all work). Document
each var at its use site so a dev can enable just that stream. Grep the
prefix in the log file instead of remembering which module logged what.

Current streams (canonical name first, legacy aliases after):

| Canonical var | Legacy aliases | Prefix | Site |
|---|---|---|---|
| `SLI_TOOLKIT_DEBUG` | — | (toolkit-wide `DEBUG` gate, not a prefix stream) | `core/logging.py:setup_logging` |
| `SLI_FLYOUT_DEBUG` | `IMGSLI_FLYOUT_DEBUG`, `FLYOUT_DEBUG` | `[flyout-nav]` / `[flyout-fade]` / `[flyout-placement]` | `ui/widgets/composite/base_flyout/debug.py` (`FLYOUT_DEBUG_VARS`) |
| `SLI_NAV_DEBUG` | `UI_NAV_DEBUG` | `[nav-*]` | `ui/managers/navigation_debug.py` (`NAV_DEBUG_VARS`), `ui/widgets/buttons/events.py`, `ui/widgets/buttons/layers/focus.py`, `ui/widgets/composite/help_document/canvas.py` |
| `SLI_UI_NAVLIST_DEBUG` | — | `[navlist]` | `ui/widgets/composite/sidebar_nav_list/debug.py` |
| `SLI_UI_COLORS_DEBUG` | — | `[colors-source-debug]` | `ui/inspector/rendering.py` |
| `SLI_SCROLLBAR_DEBUG` | `IMGSLI_SCROLLBAR_DEBUG` | `[scrollbar]` | `ui/widgets/atomic/minimalist_scrollbar.py` |
| `SLI_RESIZE_DEBUG` | — | `[resize-debug]` | `ui/windows/frameless/resize_filter.py` |
| `SLI_TIMELINE_DEBUG` | `IMGSLI_TIMELINE_DEBUG`, `IMGSLI_VIDEO_EDITOR_DEBUG` | `[timeline-debug]` / `[timeline-paint]` | `ui/widgets/composite/timeline_widget/debug.py` |
| `SLI_DND_DEBUG` | `IMGSLI_DND_DEBUG`, `IMGSLI_IMAGE_COMPARE_DEBUG`, `IMGSLI_IC_DEBUG` | `[dnd-overlay]` | `ui/widgets/overlays/drag_drop_overlay.py` |
| `SLI_TEXTVIEW_DEBUG` | — | (paint/state detail, raw `os.getenv` check) | `ui/widgets/composite/text_view/` — legacy strict `== "1"` check; migrate to `any_flag` when touched |

## Never mutate logger levels at import time

The main historical violation class: calling `setLevel`, adding handlers,
or otherwise reconfiguring logging as a side effect of importing a module.
Module import must be side-effect free — gating happens per call inside the
`_xxx_debug()` helper, levels are set centrally in `setup_logging`, and a
stream is silenced by unsetting its env var, never by import-order luck.

## Temporary collaborative diagnostics

When a behavior can't be predicted from source alone, temporary diagnostics
are still `logger` with a unique prefix — not `print()`:

1. Add boundary probes: `logger.warning("[xxx-debug] enter: visible=%s anchor=%s", ...)`.
   Use `warning` (not `debug`) when the other party isn't running a debug
   build, so no flag-flipping is needed.
2. For "who called this?", log a stack: `logger.warning("[xxx] stack:\n%s",
   "".join(traceback.format_stack(limit=12)))` — through the same pipeline,
   so it lands in the log file.
3. Reproduce, then `grep '\[xxx-debug\]' <app>/log.txt`.
4. **Remove the probes after the fix.** Never commit diagnostic noise.

## Naming: canonical `SLI_*` first, aliases documented at use site

New vars are canonical `SLI_*`. A legacy alias survives only where a host
app already reads that name for the same trace (one env var enabling both
sides), and it is documented next to the canonical name at the use site —
canonical first in the `any_flag(...)` argument list. Never invent a new
non-`SLI_` name.

## File behavior truth

The file handler is `logging.FileHandler(log_path, mode="w")` — the log
file is **overwritten on every app start**, not rotated or appended.
Per-OS location comes from `get_log_directory(app_name)`; capture sessions
worth keeping before restarting.

Log line format:

```
2026-06-26 11:31:45,313 - [DEBUG] - (rhi_renderer.py:54) - [xxx-debug] render begin ...
```

Follow live with `tail -f <data-dir>/<AppName>/log.txt`, filter with
`grep '\[xxx-debug\]' <data-dir>/<AppName>/log.txt`.
