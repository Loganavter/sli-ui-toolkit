from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.ui.managers.ui_scale import UiScale

_PIXMAP_CACHE_MAX = 512
_pixmap_cache: OrderedDict[tuple[int, int, int, float], QPixmap] = OrderedDict()


def normalized_icon_pixmap(icon_value, size: int | QSize) -> QPixmap:
    """Return a cached pixmap of ``icon_value`` rendered at the requested size.

    The icon is rendered straight from the source at the requested target
    size; the caller is responsible for designing icons (SVG viewBox, padding)
    appropriately for the intended display size. There is no content-aware
    cropping or rescaling.

    The cache key includes the current ``UiScale`` factor: two different
    factors that happen to round to the same target px (e.g. 0.75 vs 1.0
    for small icons) must not serve each other's pixmaps.
    """
    if isinstance(size, QSize):
        target_w = max(1, int(size.width()))
        target_h = max(1, int(size.height()))
    else:
        target_w = target_h = max(1, int(size))

    icon = icon_value if isinstance(icon_value, QIcon) else resolve_icon(icon_value)
    cache_key = (
        int(icon.cacheKey()),
        target_w,
        target_h,
        UiScale.get_instance().factor(),
    )
    cached = _pixmap_cache.get(cache_key)
    if cached is not None:
        _pixmap_cache.move_to_end(cache_key)
        return cached

    pixmap = icon.pixmap(QSize(target_w, target_h))
    return _cache_pixmap(cache_key, pixmap)


def _cache_pixmap(cache_key: tuple[int, int, int, float], pixmap: QPixmap) -> QPixmap:
    _pixmap_cache[cache_key] = pixmap
    _pixmap_cache.move_to_end(cache_key)
    while len(_pixmap_cache) > _PIXMAP_CACHE_MAX:
        _pixmap_cache.popitem(last=False)
    return pixmap
