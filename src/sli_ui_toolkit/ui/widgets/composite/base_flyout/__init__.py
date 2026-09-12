"""BaseFlyout family — the in-window flyout shell.

Folder split (the buttons/ folder is the model): ``widget.py`` is the thin
facade; placement geometry is pure functions in ``geometry.py``; style,
content building, fade animation, placement, show/hide lifecycle and the
FlyoutManager contract are mixins in ``style.py`` / ``builder.py`` /
``animation.py`` / ``placement.py`` / ``lifecycle.py`` / ``contract.py``.
"""

from sli_ui_toolkit.ui.widgets.composite.base_flyout.animation import (
    resolve_flyout_animation,
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout.geometry import (
    AnimationAxis,
    aligned_flyout_rect,
    slide_start_delta,
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout.widget import BaseFlyout

__all__ = [
    "AnimationAxis",
    "BaseFlyout",
    "aligned_flyout_rect",
    "resolve_flyout_animation",
    "slide_start_delta",
]
