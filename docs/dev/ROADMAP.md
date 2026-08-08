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

- API consistency audit findings — see
  [API_CONSISTENCY_AUDIT.md](API_CONSISTENCY_AUDIT.md) for full detail:
  - `configure_toolkit` split into focused `configure_interaction` /
    `configure_overlay` / `configure_context_menu` / `configure_dragdrop`
    functions, kept backward compatible — defer until a real host need
    motivates it, not for taxonomy alone.
  - Retrofit `Literal[...]` onto untyped `str` constructor kwargs
    (`Button.variant`, `IconListWidget.selected_icon_mode`,
    `RatingListItem.item_type`/`.position`, text-input `alignment`, …) —
    safe, additive; do opportunistically when a widget file is touched
    anyway, not as one giant sweep.
  - Global-singleton-vs-DI tradeoff (`ThemeManager`, `config.py` module
    globals) — explicitly not planned as a blanket rewrite; only revisit
    per-widget if a real multi-context use case shows up.
  - `py.typed` was added without a mypy baseline; a stock `mypy` run finds
    562 errors (mostly internal `ui/` Optional-attribute noise, but 23 in
    the public `i18n.py`). Fix `i18n.py`'s `TranslationManager` attribute
    typing first if this gets picked up; no CI gate until the count is
    low enough to enforce.

- Flyout layer/rule system phase 5 (declarative schema for groups/layers/
  links) — deferred until phases 1–4 have real host call sites to
  generalize from. See
  [FLYOUT_LAYER_SYSTEM_PLAN.md](FLYOUT_LAYER_SYSTEM_PLAN.md).

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
