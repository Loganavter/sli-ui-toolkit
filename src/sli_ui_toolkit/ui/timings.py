"""Central animation/transition durations (design ms).

Toolkit widgets previously inlined literals (120, 140, 150, 160 …) across
~10 files. Centralising them makes host-wide tuning and future scaling
consistent, and keeps the flyout-specific timings in
``sli_ui_toolkit.config.FlyoutTimingConfig`` as the single source for
flyout animations.

Shadow/scrim colors already use ``shadow.color`` token; this module only
holds durations.
"""

HOVER_DURATION_MS = 120
CHECKED_DURATION_MS = 150
SWITCH_PROGRESS_DURATION_MS = 160
SWITCH_HOVER_DURATION_MS = 120
SLIDER_INNER_DURATION_MS = 140
SPINBOX_SCROLL_THROTTLE_MS = 32  # not animation, but kept together
