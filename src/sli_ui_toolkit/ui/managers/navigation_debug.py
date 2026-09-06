"""Debug-log helpers for :mod:`navigation_manager` -- split out because they
are pure functions with no coupling to ``NavigationManager`` state.

Gating follows the host app's ``docs/dev/LOGGING.md`` unique-prefix
convention (same as ``sidebar_nav_list/debug.py``): call-time
:func:`nav_debug_enabled` check on ``SLI_NAV_DEBUG`` (legacy alias
``UI_NAV_DEBUG``, shared with the host's ``events/router.py``), ``[nav-*]``
prefix on every line, off by default even under the host's ``--debug``.
Never mutates logger levels at import time.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt

from sli_ui_toolkit.core.debug_flags import any_flag

logger = logging.getLogger("sli_ui_toolkit.ui.managers.navigation_manager")

# Canonical toolkit name first; ``UI_NAV_DEBUG`` is the legacy alias also
# read by the host app (Improve-ImgSLI ``src/events/router.py``), kept so
# one env var enables both sides of the same trace.
NAV_DEBUG_VARS = ("SLI_NAV_DEBUG", "UI_NAV_DEBUG")


def nav_debug_enabled() -> bool:
    """True when navigation tracing was opted in via env."""
    return any_flag(*NAV_DEBUG_VARS)


def nav_debug(message: str, *args) -> None:
    """Env-gated navigation trace line (already carries its ``[nav-*]`` prefix)."""
    if nav_debug_enabled():
        logger.debug(message, *args)

# int() keys: Qt.Key members hash equal to their int value, so int-keyed
# lookup by raw key code behaves identically while satisfying mypy.
_KEY_NAMES: dict[int, str] = {int(v): k.split(".")[-1] for k, v in Qt.Key.__members__.items()}


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
