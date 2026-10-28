"""Exemptions for ``tests/test_dpr_contract.py`` — keyed per SITE, shrink-only.

The contract enumerates the ways a HiDPI raster can be broken (see the module
docstring of ``tests/test_dpr_contract.py`` and ``docs/dev/DPR_CONTRACT.md``).
A finding is identified by ``(relative_path, function_name, rule_id)``.

Rules for this file:

* an entry must carry a reason that says *why the shape is correct here* — not
  "TODO";
* an entry must still match code: ``test_allowlist_is_shrink_only`` fails if a
  detector stops reporting the site (fix landed, or the code moved), so the
  list cannot rot into a blanket exclude;
* empty is the normal, desired state. Adding an entry is a design decision that
  belongs in a review, not a way to make a red gate quiet.
"""

from __future__ import annotations

#: ``(relative_path, function_name, rule_id) -> reason``.
ALLOWLIST: dict[tuple[str, str, str], str] = {
    (
        "src/sli_ui_toolkit/ui/widgets/buttons/content.py",
        "coerce_pixmap",
        "icon-app-ratio",
    ): (
        "by design: this rasterizes an icon-like value at 256 px ONLY as a source "
        "for PixmapContent, which re-renders it at the painter's ratio through "
        "_device_scaled(source, ..., ratio) before drawing. Rasterizing at the "
        "paint ratio here would need the painter, which this coercion does not "
        "have (it also accepts QPixmap/QImage/paths)."
    ),
    (
        "src/sli_ui_toolkit/ui/managers/icon_manager.py",
        "_get_themed_icon_cached",
        "icon-app-ratio",
    ): (
        "by design: this rasterizes an icon at its OWN native size (one pixmap per "
        "availableSize, or a 256 px fallback) only to RECOLOUR it, then adds it "
        "back to a QIcon; the consumer rasterizes again through "
        "normalized_icon_pixmap(dpr=...). Recolouring at the paint ratio would "
        "require knowing the target screen before the themed icon exists."
    ),
    (
        "tests/test_paint_cache.py",
        "test_dpr_change_busts_cache",
        "ratio-hardcoded",
    ): (
        "by design: the test SPOOFS a device ratio to prove a ratio change retires "
        "the paint cache. It passes 3.0 — a value the live run does not use — which "
        "is the PR #124 fix for the original defect (a hardcoded 2.0 is a no-op "
        "under QT_SCALE_FACTOR=2). Distinguishing 'spoof a change' from 'assume the "
        "screen' needs the live ratio, which no static scan can know, so this one "
        "site is a human judgement and is recorded here instead of guessed."
    ),
}
