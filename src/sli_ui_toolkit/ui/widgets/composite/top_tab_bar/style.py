"""How a host wants its tab selection to look.

The tab strip used to be one design: folder-shaped tabs joined to the pane, an accent underline, and the pane's own
chrome. A host that wants something else - flat buttons standing apart from the content, a plate instead of an outline,
a different radius or spacing - had to fork the widget.

`TabStyle` is that surface: the numbers and tokens the strip and each tab paint with, with the current look as the
default. `flat=True` drops the folder outline and the join cover, so a selected tab is a plain plate over the content -
"buttons, not tabs" - and `gap` opens the distance between the strip and the pane.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt


@dataclass(frozen=True)
class TabStyle:
    """Paint settings for a tab strip (defaults = the toolkit's folder-tab look)."""

    #: Pixels of empty space between the strip and the content.
    gap: int = 0
    #: `True` = flat buttons: no folder outline, no join cover, no accent underline. A selected tab is a plate.
    flat: bool = False
    #: `False` = the pane draws no stroke (a host that wants no box around the content at all).
    border: bool = True
    #: Corner radius of a tab; `None` keeps the strip's own default.
    radius: int | None = None
    #: Horizontal text padding inside a tab; `None` keeps `TAB_H_PAD`.
    padding: int | None = None
    #: Gap between neighbouring tabs; `None` keeps `TAB_SPACING`.
    spacing: int | None = None
    #: Floor for a tab's width, so a label is not elided away; `None` keeps `TAB_MIN_WIDTH`.
    min_width: int | None = None
    #: Token for a selected tab's plate (only painted when `flat`).
    selected_token: str = "accent"
    #: Token for a tab's text.
    text_token: str = "dialog.text"
    #: When the overflow bar is shown - Qt's own policy, not a rule of this widget's invention:
    #: `AsNeeded` (only while the tabs do not fit), `AlwaysOff`, `AlwaysOn` (shown disabled when they fit).
    scroll_policy: Qt.ScrollBarPolicy = field(default=Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    #: `True` reserves the bar's row under the tabs ALWAYS - the way a normal scrollbar occupies its space - so showing
    #: the bar on hover cannot reflow the strip. `False` (the toolkit default) keeps a stock `QTabWidget`'s geometry.
    reserve_scroll_row: bool = False

    def tab_radius(self, default: int) -> int:
        return default if self.radius is None else max(0, int(self.radius))

    def tab_padding(self, default: int) -> int:
        return default if self.padding is None else max(0, int(self.padding))

    def tab_spacing(self, default: int) -> int:
        return default if self.spacing is None else max(0, int(self.spacing))

    def tab_min_width(self, default: int) -> int:
        return default if self.min_width is None else max(1, int(self.min_width))
