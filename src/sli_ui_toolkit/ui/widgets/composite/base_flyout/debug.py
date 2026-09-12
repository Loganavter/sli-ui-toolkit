"""Env-gated flyout debug traces (``SLI_FLYOUT_DEBUG=1``).

Toolkit mirror of the host app's ``docs/dev/LOGGING.md`` unique-prefix
convention (same as ``navigation_debug.py``): call-time
:func:`_flyout_debug_enabled` check on ``SLI_FLYOUT_DEBUG`` (legacy aliases
``IMGSLI_FLYOUT_DEBUG``, ``FLYOUT_DEBUG``), ``[flyout-nav]`` /
``[flyout-fade]`` / ``[flyout-placement]`` prefix on every line, off by
default even under the host's ``--debug``. Never mutates logger levels at
import time.
"""

from __future__ import annotations

import logging

from sli_ui_toolkit.core.debug_flags import any_flag

logger = logging.getLogger("sli_ui_toolkit.ui.widgets.composite.base_flyout")

# Canonical toolkit name first; ``IMGSLI_FLYOUT_DEBUG`` is the legacy host-app
# alias, ``FLYOUT_DEBUG`` the short generic alias.
FLYOUT_DEBUG_VARS = ("SLI_FLYOUT_DEBUG", "IMGSLI_FLYOUT_DEBUG", "FLYOUT_DEBUG")


def _flyout_debug_enabled() -> bool:
    """True when flyout tracing was opted in via env."""
    return any_flag(*FLYOUT_DEBUG_VARS)


def _flyout_debug(message: str, *args) -> None:
    """Env-gated flyout trace line (already carries its ``[flyout-*]`` prefix)."""
    if _flyout_debug_enabled():
        logger.debug(message, *args)


__all__ = ["FLYOUT_DEBUG_VARS", "_flyout_debug", "_flyout_debug_enabled", "logger"]
