# Console, Logging & Notifications API

Widgets for showing live process output, app log messages, and transient
toast notifications.

## Console & Logging

| Widget | Description |
|--------|-------------|
| `LogConsoleWidget` / `LogConsoleEntry` | Read-only themed console for app log messages. |
| `ProcessConsoleWidget` | `QProcess`-driven console for live command output with stdin input. |

Both consoles cap their scrollback with a single `max_entries` constructor
kwarg (also settable at runtime via `set_max_entries`); there is no other
layout config.

```python
from sli_ui_toolkit.widgets import LogConsoleWidget, ProcessConsoleWidget

console = LogConsoleWidget(max_entries=500)  # default: 1000; oldest entries drop first
console.append_message("Ready", level="status", color="#9E9E9E", bold=True)
console.set_max_entries(200)

process = ProcessConsoleWidget(max_entries=5000)  # default: 2000
process.start_shell()  # or start_process(program, args, workdir=..., env=...)
process.send_input("ls -la")
```

`LogConsoleWidget.append_message(text, *, level="info", color=None, bold=False, italic=False, metadata=None)`
accepts `level` in `{"info", "error", "status"}`, `color` as a hex string or
`QColor`, and free-form `metadata`.

## Notifications

| Widget | Description |
|--------|-------------|
| `ToastManager` / `ToastNotification` / `ToastAction` / `ToastProgressBar` | In-window transient toasts. `show_toast(content, actions=...)` accepts strings, custom content widgets, `ToastAction` entries, action specs, or action widgets. Progress uses painted `ToastProgressBar` (accent fill, rounded track). |

`ToastManager(parent_window, image_label=None)` requires an in-window
parent; `image_label` (optional) anchors toast position and drives the
auto-computed max width (`42%` of `image_label`'s width, else `35%` of
`parent_window`'s, else a `360px` fallback — there is no width constructor
param). `spacing` (default `10`) is a plain public attribute, not a
constructor kwarg.

```python
from sli_ui_toolkit.widgets import ToastAction, ToastManager

toasts = ToastManager(main_window, image_label=canvas)
toasts.spacing = 12  # px gap between stacked toasts

toast_id = toasts.show_toast(
    "Export complete",
    duration=4000,                                          # ms; 0 disables auto-hide
    actions=[ToastAction("Undo", callback=undo_export, dismiss=True)],
    progress=None,                                           # 0-100 shows a ToastProgressBar instead
    success=True,
)
toasts.update_toast(toast_id, "90%", success=False, progress=90)
```

`actions` also accepts plain `dict`/`tuple` specs or a raw `QWidget`, not
only `ToastAction` instances.

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
