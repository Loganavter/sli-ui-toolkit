"""Env-gated timeline traces (``SLI_TIMELINE_DEBUG``).

Canonical var ``SLI_TIMELINE_DEBUG`` first, legacy ``IMGSLI_TIMELINE_DEBUG`` /
``IMGSLI_VIDEO_EDITOR_DEBUG`` aliases after (permissive
:func:`~sli_ui_toolkit.core.debug_flags.any_flag`: any non-empty value except
``0/false/no/off``).

Two thin wrappers share one gate/helper so widget logic and paint paths stay
greppable independently:

* :func:`_timeline_debug` — ``[timeline-debug]`` for ``widget.py`` state /
  geometry sites.
* :func:`_timeline_paint_debug` — ``[timeline-paint]`` for ``render.py``
  paint sites.
"""

from __future__ import annotations

import logging

from sli_ui_toolkit.core.debug_flags import any_flag

_TIMELINE_DEBUG_VARS = (
    "SLI_TIMELINE_DEBUG",
    "IMGSLI_TIMELINE_DEBUG",
    "IMGSLI_VIDEO_EDITOR_DEBUG",
)

_timeline_logger = logging.getLogger("sli_ui_toolkit.timeline")


def _timeline_debug_enabled() -> bool:
    return any_flag(*_TIMELINE_DEBUG_VARS)


def _timeline_debug(message: str, *args) -> None:
    if _timeline_debug_enabled():
        _timeline_logger.debug("[timeline-debug] " + message, *args)


def _timeline_paint_debug(message: str, *args) -> None:
    if _timeline_debug_enabled():
        _timeline_logger.debug("[timeline-paint] " + message, *args)
