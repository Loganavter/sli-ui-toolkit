# sli-ui-toolkit Docs

This folder is split by document role.

## Reading Order

1. [../README.md](../README.md)
   Start here if you are integrating the toolkit into an app.
2. [API_CATALOG.md](API_CATALOG.md)
   Use this as the public widget and helper reference.
3. [ARCHITECTURE.md](ARCHITECTURE.md)
   Read this when changing internals or adding new subsystems.
4. [DESIGN_LANGUAGE.md](DESIGN_LANGUAGE.md)
   Read this when implementing or restyling custom-painted widgets.
5. [ROADMAP.md](ROADMAP.md)
   Read this when planning toolkit maturity work.
6. [BUTTON_API.md](BUTTON_API.md)
   Use this when working with the composable `Button` widget.
7. [BUTTON_ARCHITECTURE.md](BUTTON_ARCHITECTURE.md)
   Read this when changing button internals.
8. [FLYOUT_SYSTEM.md](FLYOUT_SYSTEM.md)
   Read this when using or extending flyouts (BaseFlyout, prebuilt composites, FlyoutManager, scroll-button value popup).

## Document Roles

- `README.md`
  Integration-oriented entry point. Shows import layers, bootstrap hooks, and the shortest path to first usage.
- `API_CATALOG.md`
  Public reference. Prefer this over code spelunking when you need to know what is exportable and how it is intended to be used.
- `ARCHITECTURE.md`
  Internal structure and subsystem boundaries. Not a full API manual.
- `DESIGN_LANGUAGE.md`
  Visual and interaction conventions for custom controls.
- `ROADMAP.md`
  Planned quality, API stability, packaging, and documentation improvements.
- `BUTTON_API.md`
  Button-specific public API reference.
- `BUTTON_ARCHITECTURE.md`
  Button subsystem internals and layering.
- `FLYOUT_SYSTEM.md`
  Flyout subsystem: BaseFlyout, the FlyoutManager singleton, the prebuilt composites, and the scrollable-button value popup.

## Rules

- Add new public widget usage details to `API_CATALOG.md`.
- Add new subsystem diagrams or layering notes to `ARCHITECTURE.md`.
- Add visual tokens, geometry rules, or interaction conventions to `DESIGN_LANGUAGE.md`.
- Keep `README.md` short. If a section starts reading like reference material, move it into `docs/`.
