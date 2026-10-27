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
