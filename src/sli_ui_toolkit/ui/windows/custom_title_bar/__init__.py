"""CustomTitleBar family — the window title bar.

Folder split (the buttons/ folder is the model): ``widget.py`` is the thin
facade; zones/balance/scale live in ``zones.py``, the window-control
cluster + window attach in ``window_controls.py``, the drag surface in
``drag.py``, and fill/paint/theme hooks in ``appearance.py``.
"""

from sli_ui_toolkit.ui.windows.custom_title_bar.widget import CustomTitleBar
from sli_ui_toolkit.ui.windows.custom_title_bar.zones import (
    TitleAlign,
    TitleBarZone,
    resolve_titlebar_color,
)

__all__ = [
    "CustomTitleBar",
    "TitleAlign",
    "TitleBarZone",
    "resolve_titlebar_color",
]
