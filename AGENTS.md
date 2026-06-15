# sli-ui-toolkit Agent Guide

This repository contains the shared PyQt6 UI toolkit used by Improve-ImgSLI and Tkonverter. SLI stands for **Shared Lightweight Interface**.

## What This Library Is

`sli-ui-toolkit` is effectively an extracted slice of two existing applications, not a neutral toolkit designed from scratch. Some APIs, widget families, and naming choices still reflect Improve-ImgSLI and Tkonverter history. The name keeps that history, but the current expansion is Shared Lightweight Interface.

The goal is still to keep it reusable for any PyQt application:

- host-specific resources, icons, translations, and business logic stay outside the library;
- application behavior is injected through configuration hooks, callbacks, signals, or plain data objects;
- shared widgets, managers, theme-aware primitives, and reusable UI infrastructure stay here.

## First Read

Read these files before changing code:

1. [README.md](README.md)
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
3. [docs/API_CATALOG.md](docs/API_CATALOG.md)
4. [docs/DESIGN_LANGUAGE.md](docs/DESIGN_LANGUAGE.md)
5. [CHANGELOG.md](CHANGELOG.md)

## Hard Rules

- Do not push without explicit user approval.
- Do not push library changes without changing the package version.
- Do not change the package version without updating [CHANGELOG.md](CHANGELOG.md) in the same change.
- Version changes must update every version source consistently:
  - [pyproject.toml](pyproject.toml)
  - [src/sli_ui_toolkit/_version.py](src/sli_ui_toolkit/_version.py)
  - [CHANGELOG.md](CHANGELOG.md)
- Before bumping or releasing, compare local tags, the current package version,
  and [CHANGELOG.md](CHANGELOG.md). Do not leave missing release sections for
  already-tagged versions; add concise catch-up entries if older releases were
  tagged without changelog sections.
- Do not add Improve-ImgSLI-specific or Tkonverter-specific logic to the toolkit.
- Do not add fallback imports from host applications.
- Do not bias the design toward the dark theme. Light and dark themes are both first-class and must resolve through `ThemeManager` tokens.

## Project Shape

- `src/sli_ui_toolkit/` — package source.
- `src/sli_ui_toolkit/ui/widgets/atomic/` — small custom-painted controls.
- `src/sli_ui_toolkit/ui/widgets/buttons/` — unified button system.
- `src/sli_ui_toolkit/ui/widgets/comboboxes/` — combo box family.
- `src/sli_ui_toolkit/ui/widgets/composite/` — reusable multi-widget assemblies.
- `src/sli_ui_toolkit/ui/managers/` — theme, icon, and flyout managers.
- `docs/` — architecture, API, and design documentation.

## Good Defaults

- Prefer public imports through `sli_ui_toolkit.widgets` for host app examples.
- Keep reusable widgets app-agnostic and pass app behavior in explicitly.
- Read colors and sizes through `ThemeManager`, widget properties, or documented tokens.
- Use focused patches and avoid unrelated refactors.
- Update docs when changing public widget behavior or API.
