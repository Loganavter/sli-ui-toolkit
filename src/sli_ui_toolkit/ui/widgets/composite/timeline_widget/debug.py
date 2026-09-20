"""Env-gated timeline traces (``SLI_TIMELINE_DEBUG``).

Canonical var ``SLI_TIMELINE_DEBUG`` first, legacy ``IMGSLI_TIMELINE_DEBUG`` /
``IMGSLI_VIDEO_EDITOR_DEBUG`` aliases after (permissive
:func:`~sli_ui_toolkit.core.debug_flags.any_flag`: any non-empty value except
``0/false/no/off``).

Two thin wrappers share one gate/helper so widget logic and paint paths stay
greppable independently, plus a gutter wrapper with a monotonic tick for
zoom-vs-overlay ordering analysis:

* :func:`_timeline_debug` — ``[timeline-debug]`` for ``widget.py`` state /
  geometry sites.
* :func:`_timeline_paint_debug` — ``[timeline-paint]`` for ``render.py``
  paint sites.
* :func:`gutter_debug` — ``[timeline-gutter]`` for gutter/overlay sites
  (zoom commit band, sticky overlay, gutter drag, host scroll). Each line
  carries ``tick=N`` from :func:`_next_tick` so a lag between the zoom
  commit, the synchronous band repaint, and the async full paint can be
  read off the log order.
"""

from __future__ import annotations

import logging
from typing import Any

from sli_ui_toolkit.core.debug_flags import any_flag

_TIMELINE_DEBUG_VARS = (
    "SLI_TIMELINE_DEBUG",
    "IMGSLI_TIMELINE_DEBUG",
    "IMGSLI_VIDEO_EDITOR_DEBUG",
)

_timeline_logger = logging.getLogger("sli_ui_toolkit.timeline")


def _timeline_debug_enabled() -> bool:
    return any_flag(*_TIMELINE_DEBUG_VARS)


def _emit(prefix: str, message: str, *args: Any) -> None:
    """Shared gate + logger for the timeline trace wrappers below."""
    if _timeline_debug_enabled():
        _timeline_logger.debug(prefix + " " + message, *args)


def _timeline_debug(message: str, *args: Any) -> None:
    _emit("[timeline-debug]", message, *args)


def _timeline_paint_debug(message: str, *args: Any) -> None:
    _emit("[timeline-paint]", message, *args)


_tick = 0


def _next_tick() -> int:
    """Monotonic sequence for gutter-trace ordering (debug only)."""
    global _tick
    _tick += 1
    return _tick


def gutter_debug(message: str, *args: Any) -> None:
    _emit("[timeline-gutter]", message, *args)
