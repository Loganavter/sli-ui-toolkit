# sli-ui-toolkit Roadmap

Forward-looking work for a mature standalone PySide6 UI toolkit. Completed
releases are recorded in [CHANGELOG.md](../../CHANGELOG.md).

## Principles (ongoing)

- Stable public imports: `sli_ui_toolkit`, `.widgets`, `.theme`, `.icons`,
  `.i18n`, `.style`, `.managers`.
- Keep host behavior out of the package (icons, translations, business rules,
  app resource layouts).
- Prefer small public aggregation modules over deep internal import paths.
- SemVer: patch for docs/fixes; minor for additions; major for intentional breaks.
- Ship `pyproject.toml`, `_version.py`, and `CHANGELOG.md` together; keep CI
  (offscreen pytest + build/twine) green.

## Open / opportunistic

- Fold remaining hand-written `theme_changed.connect(self.update)` toolkit
  widgets onto `ThemedWidget` when those files are touched for other reasons.
- Remove deprecated aliases scheduled for `0.3.0` (`"primary"` variant,
  old button class name lookups) when cutting that release.
- Grow demo coverage and API catalog entries when new widgets land.
- Keep design-token docs and contrast harness aligned when palettes change.

## Documentation

- Root `README.md` — short integration guide.
- `docs/user/API_CATALOG.md` — public widget/helper source of truth.
- `docs/dev/ARCHITECTURE.md` — boundaries and layering.
- `docs/dev/DESIGN_LANGUAGE.md` — visual and interaction rules.
