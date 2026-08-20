"""Debug-log helpers for :mod:`navigation_manager` -- split out because they
are pure functions with no coupling to ``NavigationManager`` state, gated on
their own opt-in ``UI_NAV_DEBUG`` flag (same convention as
``sidebar_nav_list/debug.py``'s ``SLI_UI_NAVLIST_DEBUG``).
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QObject, Qt

# [nav] trace lines fire on every focus/key event once the host app's
# --debug is on, drowning out other subsystems' debug output. Gated on its
# own opt-in flag, off by default even under --debug -- same convention as
# sidebar_nav_list/debug.py's SLI_UI_NAVLIST_DEBUG.
logger = logging.getLogger("sli_ui_toolkit.ui.managers.navigation_manager")
if os.environ.get("UI_NAV_DEBUG", "").strip().lower() in (
    "",
    "0",
    "false",
    "no",
    "off",
):
    logger.setLevel(logging.WARNING)
else:
    logger.setLevel(logging.DEBUG)

_KEY_NAMES = {v: k.split(".")[-1] for k, v in Qt.Key.__members__.items()}


def _key_name(key: int) -> str:
    return _KEY_NAMES.get(key, f"0x{key:X}")


def widget_label(widget: QObject | None) -> str:
    """Best-effort identifying label for a debug-log line.

    Most navigable controls (toolbar ``Button``s especially) never get an
    ``objectName()`` set -- every one of them then logs as indistinguishable
    ``Button()``, which makes ``UI_NAV_DEBUG`` traces useless for telling
    *which* button focus actually landed on. Falls back through
    ``objectName()`` -> tooltip -> button text -> ``id()`` so there's always
    something to tell instances apart by, and appends the widget's global
    on-screen geometry (position + size) so a trace can be checked against
    a UI dump / where the click actually was without guessing from the
    name alone.
    """
    if widget is None:
        return "None"
    name = getattr(widget, "objectName", lambda: "")() or ""
    if not name:
        name = getattr(widget, "toolTip", lambda: "")() or ""
    if not name:
        name = getattr(widget, "_text", None) or ""
    if not name:
        name = f"id={id(widget):#x}"
    geo = ""
    map_to_global = getattr(widget, "mapToGlobal", None)
    rect = getattr(widget, "rect", None)
    if map_to_global is not None and rect is not None:
        try:
            top_left = map_to_global(rect().topLeft())
            geo = f" @({top_left.x()},{top_left.y()} {rect().width()}x{rect().height()})"
        except Exception:
            geo = ""
    return f"{type(widget).__name__}({name}){geo}"
