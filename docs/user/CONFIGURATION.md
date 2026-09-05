# Configuration Guide

`sli-ui-toolkit` ships with usable defaults (bundled icons, a light Fluent-ish
palette, English strings) so a minimal app needs no setup at all. Host apps
that want their own icons, palette, translations, logging, or interaction
timing configure the toolkit once at startup through a small set of
process-wide hooks.

This page is the single reference for all of them. It complements the
per-widget entries in [API_CATALOG.md](API_CATALOG.md).

## Rules Of Thumb

- **Configure once, at startup, before you build your first window.** Every
  hook here sets process-wide (module-level) state read by widgets when they
  are constructed or painted. Nothing here is per-widget or per-instance.
- **Order matters only where noted below.** `QApplication` must exist before
  `ThemeManager.set_theme(...)`, `install_application_tooltips(...)`, and
  anything else that touches `QApplication.instance()`. The rest can run in
  any order relative to each other.
- **Everything is optional.** Skipping a hook falls back to a documented
  default (bundled icon glyphs, the built-in Fluent palette module, English
  strings, etc.) — see the "If skipped" column below.
- **Re-configuring later is safe** for the things designed to change at
  runtime (theme, language) via their own dedicated calls
  (`ThemeManager.set_theme`, `emit_language_changed`). Re-calling
  `configure_toolkit` / `configure_icon_resolver` / `configure_i18n` after
  startup overwrites the previous process-wide values immediately — fine for
  tests or plugin reload, unusual for normal app flow.
- **Tests that call `configure_toolkit` must reset afterward.** Its state is
  module-level, so it leaks into unrelated tests otherwise. Call
  `sli_ui_toolkit.config.reset_toolkit_config()` in a fixture's teardown (this
  repo's `tests/conftest.py` does it via an autouse fixture around every
  test). It restores `configure_toolkit`'s defaults, including the ripple
  duration / click deferral / underline fade shorthands.

## Full Startup Sequence

This mirrors [`demo/main.py`](../../demo/main.py), the toolkit's own
reference integration — read it alongside this page for a complete, running
example.

```python
import sys
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.icons import configure_icon_resolver
from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.palettes import FLUENT_LIGHT, FLUENT_DARK
from sli_ui_toolkit.i18n import configure_i18n
from sli_ui_toolkit import setup_logging, install_application_tooltips

app = QApplication(sys.argv)

# 1. Logging — do this first so later setup is diagnosable.
setup_logging("MyApp", debug_enabled=False, debug_env_var="MYAPP_DEBUG")

# 2. Icons — map your app's icon enum/names/paths to QIcon.
configure_icon_resolver(my_icon_resolver, named_icons=MY_NAMED_ICONS)

# 3. Toolkit behavior — flyout timing, overlay placement, button feedback.
configure_toolkit(
    timings=FlyoutTimingConfig(
        transient_auto_hide_delay_ms=300,
        flyout_animation_duration_ms=150,
    ),
    overlay_resolver=lambda widget: getattr(widget.window(), "overlay_layer", None),
    ripple_duration_ms=280,
)

# 4. Theme — register your palette(s) and pick a starting theme.
theme_manager = ThemeManager.get_instance()
theme_manager.register_palettes(light_palette=FLUENT_LIGHT, dark_palette=FLUENT_DARK)
theme_manager.set_theme("light", app)

# 5. Translations — point at your JSON translation directory.
configure_i18n(i18n_root="my_app/translations")

# 6. Tooltips — install the toolkit's own hover tooltip behavior app-wide.
install_application_tooltips(app)

# ... build and show your windows, then app.exec()
```

None of these calls are required to run the toolkit — omit any step you
don't need. Sections below cover each one, plus a few more specialized hooks.

---

## 1. Icons — `configure_icon_resolver`

```python
from sli_ui_toolkit.icons import configure_icon_resolver

configure_icon_resolver(resolver=None, *, named_icons=None)
```

| Param | Type | Meaning |
|---|---|---|
| `resolver` | `Callable[[Any], QIcon] \| None` | Turns an app-defined icon value (enum member, path, custom token) into a `QIcon`. Called for any icon value the toolkit can't resolve on its own. |
| `named_icons` | `dict[str, Any] \| None` | Maps string names (e.g. used by `Button(icon="save")`) to the values passed to `resolver`. |

**If skipped:** string icon names resolve through the toolkit's own bundled
glyph set (`sli_ui_toolkit.ui.services.icon_service.get_icon_by_name`); app-
specific icon enums/paths won't resolve and widgets render without an icon.

**Call again to reconfigure:** yes, safe — overwrites the resolver and name
map immediately; existing widgets pick up the change next time they resolve
an icon (e.g. next paint/update), not retroactively for icons already
resolved to a cached `QIcon`.

---

## 2. Toolkit Behavior — `configure_toolkit`

```python
from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit

configure_toolkit(
    *,
    timings=None,
    overlay_resolver=None,
    rating_gesture_factory=None,
    dragdrop_service_getter=None,
    context_menu_surface=None,
    ripple_duration_ms=None,
    default_defer_click=None,
    default_underline_fade=None,
    ui_scale_factor=None,
)
```

Every keyword is independently optional — pass only the ones you want to
change; unset keywords leave the current process-wide value untouched
(this call merges, it does not reset).

| Param | Type | Meaning | If skipped |
|---|---|---|---|
| `timings` | `FlyoutTimingConfig` | See table below. | Built-in defaults (180/160/180/150 ms, 24px drop offset, `"none"` animation). |
| `overlay_resolver` | `Callable[[QWidget \| None], QWidget \| None]` | Given a widget, returns the in-window overlay layer to paint flyouts/toasts into (for apps using `sli_ui_toolkit.ui.in_window_surface`). | Flyouts fall back to top-level popup windows. |
| `rating_gesture_factory` | `Callable[..., object]` | Factory for the drag-rating gesture helper used by rating list items. | Rating items use the toolkit's built-in gesture handling. |
| `dragdrop_service_getter` | `Callable[[], object \| None]` | Supplies a custom drag-drop service singleton. | `ToolkitDragDropService.get_instance()` (built-in). |
| `context_menu_surface` | `"in_window" \| "popup"` | Process-wide default surface for `ContextMenu` when a call site doesn't specify one explicitly. | `"in_window"`. |
| `ripple_duration_ms` | `int` | Shorthand for `set_ripple_duration_ms(...)` (button press ripple duration). | `280`. |
| `default_defer_click` | `bool \| int \| str` | Shorthand for `set_default_defer_click(...)`. | `False` (clicked fires immediately). |
| `default_underline_fade` | `bool` | Shorthand for `set_default_underline_fade(...)`. | `True`. |
| `ui_scale_factor` | `float` | Interface scale factor: multiplies fonts, icons, tokens, and widget geometry (logical px, independent of the OS/Qt display scale). Applied live via `UiScale` — subscribed widgets relayout/repaint on the spot. Clamped to the `UiScale` safety range 0.5–2.5 (the Improve-ImgSLI settings UI exposes the full range via "Interface Scale"). | `1.0` (no scaling). |

### `FlyoutTimingConfig` fields

| Field | Default | Meaning |
|---|---|---|
| `transient_auto_hide_delay_ms` | `180` | Delay before a transient (non-pinned) flyout auto-hides after losing hover/focus. |
| `flyout_animation_duration_ms` | `160` | Show/hide slide-fade duration for most flyouts. |
| `text_settings_flyout_animation_duration_ms` | `180` | Slide-fade duration for text/settings-style flyouts specifically. |
| `dropdown_drop_offset_px` | `24` | Vertical drop offset for dropdown-style flyouts from their anchor. |
| `flyout_fade_out_duration_ms` | `150` | Duration of the fade-out when a flyout shown with `animation="fade"`/`"slide-fade"` is hidden. |
| `default_flyout_animation` | `"none"` | Process-wide default for `BaseFlyout.show_aligned(..., animation=...)` when a caller omits it. Set e.g. `"slide-fade"` to animate every default flyout in the app from one place. Explicit per-call `animation=` always wins. |

Ripple duration, click deferral, and underline fade can also be set directly
without going through `configure_toolkit`, via
`sli_ui_toolkit.ui.widgets.buttons.feedback.set_ripple_duration_ms` /
`set_default_defer_click` / `set_default_underline_fade` — useful if you only
need one of the three and don't want to import `FlyoutTimingConfig` for it.

---

## 3. Theme — `ThemeManager`

Theming is not a `configure_*` function — it's a singleton manager, because
theme also changes at runtime (light/dark toggle), not just at startup.

```python
from sli_ui_toolkit.theme import ThemeManager

theme_manager = ThemeManager.get_instance()
theme_manager.register_palettes(light_palette=..., dark_palette=None)
theme_manager.register_qss_path("path/to/native_widgets.qss")  # optional
theme_manager.set_theme("light", app)  # requires QApplication to exist
```

| Call | When | Effect |
|---|---|---|
| `register_palettes(light_palette, dark_palette=None)` | Startup, before `set_theme`. | Registers your color token dicts (`{"accent": QColor(...), "button.default.background": QColor(...), ...}`). Omitting `dark_palette` reuses `light_palette` for dark mode. |
| `register_qss_path(path)` | Startup, any time before/after `register_palettes`. | Loads a Qt stylesheet template applied on top of the palette; call again to add more paths (cumulative). |
| `set_theme(name, app=None, *, await_ripples=True)` | Startup (to pick the initial theme) and any time later (to switch). | Applies `"light"`/`"dark"` process-wide and emits `theme_changed`. Deferred briefly if a button ripple is mid-animation so the switch doesn't freeze it (`await_ripples=True`, the default). |
| `set_color(key, color)` | Runtime, for one-off overrides. | Patches a single token in the *currently active* palette and re-applies immediately. |

**If skipped:** `ThemeManager` starts with empty palettes — colors resolve to
black (`get_color`) or `None` (`try_get_color`). Always call
`register_palettes` before showing any themed widget.

`sli_ui_toolkit.palettes` ships `FLUENT_LIGHT` / `FLUENT_DARK` as a ready-to-
use starting point — copy and adjust the dict rather than starting from
scratch; see [DESIGN_LANGUAGE.md](../dev/DESIGN_LANGUAGE.md) for what each
token key means.

Qt's own native widgets (`QListWidget`, tooltips drawn by Qt itself, etc.)
are **not** themed by `ThemeManager` — see `_native_qss` in
[`demo/main.py`](../../demo/main.py) for the pattern of building a small QSS
string from `try_get_color(...)` lookups and re-applying it on
`theme_changed`.

---

## 4. Translations — `configure_i18n`

```python
from sli_ui_toolkit.i18n import configure_i18n

configure_i18n(
    *,
    i18n_root=None,
    translator=None,
    language_provider=None,
    events=None,
)
```

| Param | Type | Meaning |
|---|---|---|
| `i18n_root` | `str \| Path` | Directory containing your `<lang>.json` translation files, read by `tr(key)`. |
| `translator` | `Callable[[str, str \| None], str]` | Reserved for a fully custom translation backend instead of the built-in JSON loader. |
| `language_provider` | `Callable[[], str]` | Reserved for sourcing the current language from app state instead of the toolkit's own tracked value. |
| `events` | `ToolkitTranslationEvents` | Swap in a custom event bus if you need `language_changed` routed through your own signal object. |

Switching the active language at runtime goes through
`emit_language_changed(lang_code)` — the only call that should emit
`language_changed`; widgets bound via `_bind_widget`/`tr` re-render
automatically on that signal.

**If skipped:** `tr(key)` returns lookup misses as the raw key (or your
`default=` argument), since there's no translation directory to load from.

---

## 5. Logging — `setup_logging`

```python
from sli_ui_toolkit import setup_logging

setup_logging(app_name, debug_enabled=False, debug_env_var=None)
```

Attaches stderr + file handlers to **both** the logger named
`app_name` and the toolkit's own `"sli_ui_toolkit"` logger tree, so toolkit
internals (`logging.getLogger(__name__)` in every widget module) show up in
your app's existing log output instead of being silently dropped. The file
handler overwrites on every start (`mode="w"` — no rotation). If
`debug_env_var` is set, that environment variable (checked at call time)
overrides `debug_enabled`.

Call this **before** other setup so early warnings (e.g. a missing QSS path
in `register_qss_path`) are actually captured.

**If skipped:** toolkit log records still go through Python's `logging`
module but have no handler attached anywhere in your app — they're dropped
unless you wire up handlers yourself. `setup_simple_logging(app_name, level)`
is a lighter one-call alternative for simple scripts (root logger + stderr
only, no file handler).

Full convention (logger trees, level model, env-gated debug streams):
[../dev/LOGGING.md](../dev/LOGGING.md).

---

## 6. Tooltips — `install_application_tooltips`

```python
from sli_ui_toolkit import install_application_tooltips

install_application_tooltips(app)  # after QApplication exists
```

Installs the toolkit's custom hover-tooltip event filter app-wide (replacing
Qt's native tooltip popup with the themed one). Idempotent — calling it
again on the same `QApplication` is a no-op.

Toggle tooltips on/off at runtime with `set_application_tooltips_enabled(bool)`
/ read the current state with `application_tooltips_enabled()`.

**If skipped:** widgets that rely on the toolkit's tooltip styling fall back
to Qt's default tooltip rendering (unthemed).

---

## Where Each Hook Lives

| Hook | Import from |
|---|---|
| `configure_icon_resolver` | `sli_ui_toolkit.icons` |
| `configure_toolkit`, `FlyoutTimingConfig` | `sli_ui_toolkit.config` (also re-exported from `sli_ui_toolkit`) |
| `ThemeManager` | `sli_ui_toolkit.theme` |
| `FLUENT_LIGHT`, `FLUENT_DARK` | `sli_ui_toolkit.palettes` |
| `configure_i18n`, `tr`, `emit_language_changed`, `get_current_language` | `sli_ui_toolkit.i18n` (also re-exported from `sli_ui_toolkit`) |
| `setup_logging`, `setup_simple_logging`, `get_log_directory` | `sli_ui_toolkit.core.logging` (also re-exported from `sli_ui_toolkit`) |
| `install_application_tooltips`, `set_application_tooltips_enabled` | `sli_ui_toolkit.ui.widgets.atomic.tooltips` (also re-exported from `sli_ui_toolkit`) |

Prefer the top-level `sli_ui_toolkit` re-exports listed in
[API_CATALOG.md](API_CATALOG.md#from-sli_ui_toolkit-import-) for application
code; the module-specific imports above are the same objects, useful mainly
to avoid pulling in the full `sli_ui_toolkit/__init__.py` surface in tests.
