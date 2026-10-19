"""Seeded exemption ratchet for ``tests/test_px_scaling_contract.py``.

The contract fails on two shapes that make a UI-scale change un-followable
(the live-scale breakage class: geometry stamped once at import, or stamped
from a raw design-px literal that never consults ``UiScale``):

(a) ``scaled_px(...)`` evaluated into an **import-time constant** (module or
    class body, or a function default) — it is baked at import and can never
    follow a later ``set_factor()``;
(b) a ``setFixed*`` / ``setMinimum*`` / ``setMaximum*`` / ``resize(`` /
    ``QSize(`` call in chrome code whose geometry arguments are *all* raw
    numeric literals (or arithmetic on literals) — an obvious design-space
    value that skips the scale path.

``EXEMPTIONS`` seeds today's offender inventory so the gate is a ratchet, not
a wall: a NEW offender fails immediately (it is simply not listed), while
fixing one is a one-line deletion here. ``EXEMPTED_SITES`` pins how many
findings each exempt file still carries — without it, adding a second
offender to an already-exempt file would slip through, and a detector that
went blind would look "clean".

Every entry must carry a reason. Entries that are *intentional* are marked
"by design" (structural sentinels like 1 px hairlines, degenerate 1×1
placeholders, design-px carriers that are resolved through ``scaled_px()``
one call later); entries marked "offender" are real unscaled design px still
to be migrated.
"""

from __future__ import annotations

#: ``relative_path -> reason``. Ratchet: never grow this list without a
#: recorded reason; delete the entry once its last offender is fixed.
EXEMPTIONS: dict[str, str] = {
    "ui/widgets/composite/gpu_fill/widget.py": (
        "by design: sizeHint() QSize(1, 1) is a degenerate placeholder for a "
        "full-bleed GPU filler surface, not a design metric"
    ),
    "ui/widgets/composite/sidebar_nav_list/icons.py": (
        "by design: QSize(24, 24) is a design-px carrier — only its .height() "
        "is handed to scaled_px() at the pixmap boundary, so the literal itself "
        "must stay unscaled"
    ),
    "ui/widgets/composite/sidebar_nav_list/widget.py": (
        "by design: IconListWidget's default icon_size QSize(24, 24) is the "
        "same design-px carrier as icons.py, resolved via scaled_px() at the "
        "pixmap boundary"
    ),
    "ui/widgets/overlays/in_window_overlay.py": (
        "by design: QSize(1, 1) is the degenerate fallback for a widget with no "
        "usable size hint, not a design metric"
    ),
    "ui/widgets/text/engine/document_canvas.py": (
        "by design: _AnchorMarker is a zero-height scroll target for "
        "ensureWidgetVisible — 1 px fixed height and 1 px max width are "
        "structural hairlines, deliberately unscaled"
    ),
}

#: Findings currently attributable to each exempt file. Pinned so that adding
#: a second offender to an already-exempt file (or a detector regression that
#: stops seeing one) fails the contract instead of hiding behind the exemption.
#: Fixing a site means lowering one number here (and dropping the file from
#: ``EXEMPTIONS`` when it reaches 0).
EXEMPTED_SITES: dict[str, int] = {
    "ui/widgets/composite/gpu_fill/widget.py": 1,
    "ui/widgets/composite/sidebar_nav_list/icons.py": 2,
    "ui/widgets/composite/sidebar_nav_list/widget.py": 1,
    "ui/widgets/overlays/in_window_overlay.py": 1,
    "ui/widgets/text/engine/document_canvas.py": 2,
}
