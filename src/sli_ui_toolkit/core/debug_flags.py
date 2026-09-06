"""Permissive ``SLI_*_DEBUG`` env-gated predicates.

Toolkit mirror of the host app's ``shared/debug_flags`` helper
(Improve-ImgSLI ``docs/dev/LOGGING.md`` "unique-prefix convention"):

* :func:`env_flag` — permissive: any non-empty value except
  ``0/false/no/off`` is true (``SLI_NAV_DEBUG=1`` or ``=yes`` etc).
* :func:`any_flag` — true when any of the given vars is set (canonical
  ``SLI_*`` name first, legacy ``UI_*``/``IMGSLI_*`` aliases after).

Subsystem debug streams gate on these at *call time* via a
``_xxx_debug_enabled()`` / ``_xxx_debug()`` pair and tag every line with
a unique bracketed prefix (``[nav-...]``, ``[flyout-nav]``, ...). They
never mutate logger levels at import time and stay off by default even
under the host's ``--debug``.
"""

from __future__ import annotations

import os

_OFF = ("", "0", "false", "no", "off")


def env_flag(name: str) -> bool:
    """Permissive flag: true unless value is empty/0/false/no/off."""
    return os.environ.get(name, "").strip().lower() not in _OFF


def any_flag(*names: str) -> bool:
    """True when any of *names* is set (per :func:`env_flag`)."""
    return any(env_flag(name) for name in names)
