"""Frameless-window mode: install/toggle API, edge-resize hit testing.

Split by concern per ``docs/dev/ARCHITECTURE.md``'s folder-split pattern
(facade + concern modules, mirroring ``base_flyout/``):

- ``geometry.py`` — pure edge hit-testing math, default ``RESIZE_MARGIN``/
  ``QWIDGETSIZE_MAX``.
- ``platform_win.py`` — Windows-only native-frame DWM/ctypes plumbing.
- ``resize_filter.py`` — ``_ResizeFilter``, the manual-resize drag state
  machine and override-cursor coordinator.
- ``lifecycle.py`` — ``apply_frameless``/``remove_frameless``/
  ``set_frameless_runtime`` and resize-filter install/teardown.

``RESIZE_MARGIN`` is re-exported here (not just from ``geometry``) because
``window_chrome.py`` reconfigures it per-window via
``frameless.RESIZE_MARGIN = ...`` on this package object — ``resize_filter``
reads the live value back off this same namespace at filter-install time.
"""

from __future__ import annotations

from .geometry import (
    QWIDGETSIZE_MAX,
    RESIZE_MARGIN,
    _cursor_for_edges,
    _edges_for_pos,
    resolve_csd_band,
)
from .lifecycle import (
    _patch_outer_band_geometry,
    _set_resize_filter,
    apply_frameless,
    remove_frameless,
    set_frameless_runtime,
)
from .platform_win import _win_refresh_native_frame
from .resize_filter import _ResizeFilter, _resize_debug

__all__ = [
    "QWIDGETSIZE_MAX",
    "RESIZE_MARGIN",
    "apply_frameless",
    "remove_frameless",
    "resolve_csd_band",
    "set_frameless_runtime",
]
