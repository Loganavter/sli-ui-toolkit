# SLI UI Toolkit

[![PyPI](https://img.shields.io/pypi/v/sli-ui-toolkit)](https://pypi.org/project/sli-ui-toolkit/)
[![CI](https://github.com/Loganavter/sli-ui-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Loganavter/sli-ui-toolkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Reusable PySide6 widgets and UI infrastructure for compact desktop tools.

SLI stands for **Shared Lightweight Interface**. Host-specific icons,
translations, resources, and business logic stay outside the library.

## What Is Included

- custom-painted compact controls: buttons, inputs, switches, sliders, labels;
- a unified `Button` system with icons, text, toggle, scroll, menu, long-press,
  ripple, and multi-region split layouts;
- reusable composite widgets: flyouts, dialog shells, markdown help, timelines,
  toasts, lists, charts;
- theme-aware painting through `ThemeManager` tokens;
- app-injected hooks for icons, i18n, overlay placement, and timing.

## Install

For development from this repository:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For use as a dependency:

```bash
python -m pip install sli-ui-toolkit
```

## Run The Demo

From the repository root:

```bash
python -m demo
```

The demo opens a PyQt window with widget pages for buttons, inputs, lists,
dialogs, flyouts, charts, feedback, and miscellaneous primitives.

If you run on a headless machine, set Qt's platform first:

```bash
QT_QPA_PLATFORM=offscreen python -m demo
```

## Run Tests

```bash
pytest tests/
```

The test suite uses `pytest-qt` and defaults to offscreen Qt through
`tests/conftest.py`.

## Basic Use

Most application code should import from `sli_ui_toolkit.widgets`.

```python
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, ComboBox

app = QApplication([])

theme = ThemeManager.get_instance()
theme.set_theme("light", app)

window = QWidget()
layout = QVBoxLayout(window)

save = Button("save", text="Save", variant="surface")
mode = ComboBox()
mode.addItems(["Fast", "Balanced", "Quality"])

layout.addWidget(save)
layout.addWidget(mode)
window.show()

app.exec()
```

## App Configuration Hooks

Hosts can inject app-specific behavior at startup:

- `configure_icon_resolver(...)`
  Supplies icon lookup for app icon enums, names, or resources.
- `configure_toolkit(...)`
  Supplies overlay placement and timing defaults for flyouts and popups.
- `ThemeManager.get_instance().register_palettes(...)` / `.set_theme(...)`
  Registers color tokens and picks the active light/dark theme.
- `configure_i18n(...)`
  Supplies translation roots and language handling.
- `setup_logging(...)`
  Routes toolkit log records into the host app's own logger/handlers.
- `install_application_tooltips(app)`
  Installs the toolkit's themed hover-tooltip behavior app-wide.

Minimal apps can use bundled toolkit icons, the built-in palette, and English
strings, and skip all of these hooks. Larger host apps should configure them
once during startup — see
**[Configuration Guide](docs/user/CONFIGURATION.md)** for the full startup
sequence, every parameter, and what happens if a hook is skipped.

## Public Import Layers

- `sli_ui_toolkit`
  Bootstrap/configuration helpers and common primitives.
- `sli_ui_toolkit.widgets`
  Main public widget catalog. Prefer this for application UI.
- `sli_ui_toolkit.theme`
  `ThemeManager`.
- `sli_ui_toolkit.icons`
  Icon resolver configuration.
- `sli_ui_toolkit.i18n`
  Translation manager and helpers.
- `sli_ui_toolkit.managers`
  Flyout and timer helpers.
- `sli_ui_toolkit.services`
  Utility services such as prewarm helpers.

Everything under `sli_ui_toolkit.ui...` is implementation detail first. Use it
inside toolkit internals, or only when no public export exists yet.

## Documentation

- [User docs](docs/user/README.md)
- [Configuration guide](docs/user/CONFIGURATION.md)
- [Full public API](docs/user/API_CATALOG.md)
- [Button API](docs/user/BUTTON_API.md)
- [Developer docs](docs/dev/README.md)
- [Architecture](docs/dev/ARCHITECTURE.md)
- [Design language](docs/dev/DESIGN_LANGUAGE.md)
- [Docs index](docs/README.md)

## Development Notes

- Keep host-app behavior outside the toolkit. Pass behavior through callbacks,
  signals, configuration hooks, or plain data objects.
- Resolve colors and sizes through `ThemeManager`, widget properties, or
  documented tokens.
- Update docs when changing public widget behavior or public API.
- Run `pytest tests/` before publishing or tagging a release.

## Caveats

- `ComboBox` is custom-painted; it is not a full `QComboBox` drop-in
  replacement.
- The toolkit is designed around custom-painted controls, not QSS-skinned stock
  widgets.
- Light and dark themes are both first-class. Avoid hard-coded colors in custom
  widgets; use theme tokens.

## License

MIT — see [LICENSE](LICENSE) for details.
