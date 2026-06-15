# sli-ui-toolkit Roadmap

This document records planned improvements for making `sli-ui-toolkit` a more mature standalone UI toolkit.

The library started as an extracted shared slice of Improve-ImgSLI and Tkonverter. The goal is not to erase that history, but to keep moving the package toward reusable PyQt infrastructure that can serve those apps and other host applications without leaking host-specific assumptions.

## Near-Term Priorities

- ~~Define the public API contract more strictly:~~
  - ~~stable imports through `sli_ui_toolkit`, `sli_ui_toolkit.widgets`, `sli_ui_toolkit.theme`, `sli_ui_toolkit.icons`, and `sli_ui_toolkit.i18n`;~~
  - ~~internal imports under `sli_ui_toolkit.ui...` documented as implementation details unless explicitly promoted.~~ *(style-bridge symbols promoted to `sli_ui_toolkit.style` in 0.2.7)*
- ~~Add focused tests for public imports, version export, theme switching, icon resolver configuration, i18n setup, and key widget smoke paths.~~
- ~~Add a small demo app that renders the main widget families in light and dark themes.~~
- ~~Document design tokens as required, optional, and app-specific extension tokens.~~ *(token tiers section in `../user/DESIGN_LANGUAGE.md`)*
- ~~Keep compatibility re-exports documented and phase them out only through explicit deprecation notes.~~ *(legacy aliases removed in 0.2.4)*

## UI Quality Work

- ~~Verify first-class light and dark theme behavior for every custom-painted widget.~~ *(static audit of all 29 `paintEvent` modules in `THEME_AUDIT.md`; 0.2.7 fixed the two remaining theme-blind painters: `DragDropOverlay` and `PasteDirectionOverlay` now read from `ThemeManager`)*
- ~~Audit keyboard navigation and focus states across buttons, comboboxes, flyouts, dialogs, and composite widgets.~~ *(full audit in `../user/KEYBOARD.md`; 0.2.7 composite pass added `TimelineWidget` Delete/arrow/Home/End handling and re-classified `EditableListItem` to OK; `InstancesCounterButton` documented as deferred / mouse-only by design)*
- ~~Add contrast checks for default token examples and generated widget states.~~ *(WCAG AA harness in `tests/test_contrast.py`; fixed dark `Highlight`/`help.nav.selected` regressions and documented targets in `../user/DESIGN_LANGUAGE.md`)*
- ~~Keep geometry compact, but document fixed sizes, density assumptions, and extension points.~~ *(`../user/DESIGN_LANGUAGE.md` → *Control Geometry* table with source constants, *Density Assumptions*, and *Extension Points* sections)*

## Packaging And Release Work

- ~~Keep SemVer discipline:~~
  - ~~patch versions for documentation, bug fixes, and compatibility-preserving improvements;~~
  - ~~minor versions for new widgets or public API additions;~~
  - ~~major versions for intentional API breaks.~~
- ~~Update `pyproject.toml`, `src/sli_ui_toolkit/_version.py`, and `CHANGELOG.md` together on every pushed release.~~
- ~~Build and validate source/wheel artifacts before publishing broader releases.~~ *(`python -m build` + `twine check` run on every push via `.github/workflows/ci.yml`)*
- ~~Consider adding CI for import smoke tests, package build, and focused widget tests in offscreen Qt mode.~~ *(GitHub Actions runs pytest under `QT_QPA_PLATFORM=offscreen` on Python 3.10–3.13, then builds and validates artifacts)*

## Architecture Work

- ~~Continue splitting large widget families into folders with private helpers, models, painting, and interaction modules.~~
- ~~Keep host behavior injected through configuration hooks, callbacks, Qt signals, and plain data objects.~~
- ~~Avoid adding application resources, business rules, or Improve-ImgSLI/Tkonverter-specific assumptions to the package.~~ *(visual references to improve-imgsli v9 cleaned out of `src/` and `docs/`; provenance remains only in this roadmap and `ARCHITECTURE.md`)*
- ~~Prefer small public aggregation modules over exposing deep internal paths to host applications.~~

## Documentation Work

- ~~Keep `README.md` integration-focused and short.~~
- ~~Keep `../user/API_CATALOG.md` as the source of truth for public widgets and helpers.~~
- ~~Keep `ARCHITECTURE.md` focused on boundaries and layering.~~
- ~~Keep `../user/DESIGN_LANGUAGE.md` focused on visual and interaction rules, not app-specific styling.~~
