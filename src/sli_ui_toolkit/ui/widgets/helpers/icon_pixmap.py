from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.ui.managers.ui_scale import UiScale

_PIXMAP_CACHE_MAX = 512
_pixmap_cache: OrderedDict[tuple, QPixmap] = OrderedDict()


def painter_dpr(painter) -> float:
    """Device pixel ratio of the device *painter* is drawing on (1.0 if unknown).

    Needed by callers that rasterize an icon themselves: the ratio has to be
    applied ONCE, to the pixmap they hand the painter, because ``QPainter``
    already scales every command by the paint device's ratio. A caller that
    multiplies its geometry by the ratio *and* paints through a ratio-tagged
    pixmap scales twice (the class the 2026-10-28 icon fix was cleaning up).
    """
    try:
        device = painter.device()
        ratio = float(device.devicePixelRatioF())
    except Exception:
        return 1.0
    return ratio if ratio > 0.0 else 1.0


def widget_dpr(widget) -> float:
    """Device pixel ratio of *widget* (1.0 when it is unknown/None)."""
    try:
        ratio = float(widget.devicePixelRatioF())
    except Exception:
        return 1.0
    return ratio if ratio > 0.0 else 1.0


def normalized_icon_pixmap(
    icon_value, size: int | QSize, *, dpr: float | None = None
) -> QPixmap:
    """Return a cached pixmap of ``icon_value`` at the requested LOGICAL size.

    ``dpr`` renders the icon at ``size * dpr`` device pixels and tags the result
    with that ratio, so a painter on a HiDPI device shows it at exactly ``size``
    logical px and rasterizes it at full resolution. Omitted/``None`` keeps the
    historical device-pixel behaviour (ratio 1.0).

    The icon is rendered straight from the source at the requested target size;
    the caller is responsible for designing icons (SVG viewBox, padding)
    appropriately for the intended display size. There is no content-aware
    cropping or rescaling. ``QIcon.pixmap`` never upscales beyond the source and
    aspect-fits it, so a non-square target may come back smaller — that is Qt's
    contract, not this helper's.

    Non-``QIcon`` values (including :func:`sli_ui_toolkit.icons.lazy_icon`
    handles and zero-arg callables) are resolved through :func:`resolve_icon`
    *before* computing the cache key, so the cache keys on the resolved
    ``QIcon.cacheKey()``. Lazy providers must return a stable (cached) ``QIcon``
    per theme so repeated paints hit the same cache entry instead of churning
    the pixmap cache on every paint.

    The cache key carries the ``UiScale`` factor and the ratio: two keys that
    differ in either must never serve each other's pixmaps.
    """
    if isinstance(size, QSize):
        target_w = max(1, int(size.width()))
        target_h = max(1, int(size.height()))
    else:
        target_w = target_h = max(1, int(size))

    icon = icon_value if isinstance(icon_value, QIcon) else resolve_icon(icon_value)
    ratio = max(1.0, float(dpr)) if dpr else 1.0
    cache_key = (
        int(icon.cacheKey()),
        target_w,
        target_h,
        UiScale.get_instance().factor(),
        ratio,
    )
    cached = _pixmap_cache.get(cache_key)
    if cached is not None:
        _pixmap_cache.move_to_end(cache_key)
        return cached

    if ratio != 1.0:
        device_w = max(1, int(round(target_w * ratio)))
        device_h = max(1, int(round(target_h * ratio)))
        pixmap = icon.pixmap(QSize(device_w, device_h))
        pixmap.setDevicePixelRatio(ratio)
    else:
        pixmap = icon.pixmap(QSize(target_w, target_h))
    return _cache_pixmap(cache_key, pixmap)


def _cache_pixmap(cache_key: tuple, pixmap: QPixmap) -> QPixmap:
    _pixmap_cache[cache_key] = pixmap
    _pixmap_cache.move_to_end(cache_key)
    while len(_pixmap_cache) > _PIXMAP_CACHE_MAX:
        _pixmap_cache.popitem(last=False)
    return pixmap
