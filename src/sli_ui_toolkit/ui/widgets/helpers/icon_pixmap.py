from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.ui.managers.ui_scale import UiScale

_PIXMAP_CACHE_MAX = 512
_pixmap_cache: OrderedDict[tuple[int, int, int, float, float], QPixmap] = OrderedDict()


def normalized_icon_pixmap(
    icon_value, size: int | QSize, *, dpr: float | None = None
) -> QPixmap:
    """Return a cached pixmap of ``icon_value`` rendered at the requested size.

    The icon is rendered straight from the source at the requested target
    size; the caller is responsible for designing icons (SVG viewBox, padding)
    appropriately for the intended display size. There is no content-aware
    cropping or rescaling.

    ``dpr`` is the ratio of the device the pixmap will be painted on, and it
    must be passed by every paint path. ``QIcon.pixmap(QSize)`` uses the
    *application* ratio, which is not the window's ratio under fractional
    display scaling: measured 2026-10-28 on KDE/Wayland at 125 %,
    ``QGuiApplication.devicePixelRatio() == 2.0`` while the window reports
    ``1.25``, so a 22 px icon came back as 44x44 @2.0 and the painter squeezed
    it into 27.5 device px (a 0.625 resample) -- thin strokes looked ragged
    while the same icons were crisp on a 100 % screen. Passing the painter's
    (or widget's) ratio rasterizes at the real device density instead.

    Non-``QIcon`` values (including :func:`sli_ui_toolkit.icons.lazy_icon`
    handles and zero-arg callables) are resolved through :func:`resolve_icon`
    *before* computing the cache key, so the cache keys on the resolved
    ``QIcon.cacheKey()``. Lazy providers must return a stable (cached) ``QIcon``
    per theme so repeated paints hit the same cache entry instead of churning
    the pixmap cache on every paint.

    The cache key includes the ratio and the current ``UiScale`` factor: two
    different ratios -- or two factors that happen to round to the same target
    px (e.g. 0.75 vs 1.0 for small icons) -- must not serve each other's
    pixmaps.
    """
    if isinstance(size, QSize):
        target_w = max(1, int(size.width()))
        target_h = max(1, int(size.height()))
    else:
        target_w = target_h = max(1, int(size))

    ratio = _resolved_ratio(dpr)
    icon = icon_value if isinstance(icon_value, QIcon) else resolve_icon(icon_value)
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

    pixmap = icon.pixmap(QSize(target_w, target_h), ratio)
    return _cache_pixmap(cache_key, pixmap)


def _resolved_ratio(dpr: float | None) -> float:
    """The paint ratio to rasterize at (never below 1.0)."""
    if dpr is not None:
        try:
            ratio = float(dpr)
        except (TypeError, ValueError):
            ratio = 1.0
    else:
        try:
            app = QGuiApplication.instance()
            # PySide types ``instance()`` as QCoreApplication; the ratio lives
            # on the QGuiApplication subclass.
            get_ratio = getattr(app, "devicePixelRatio", None)
            ratio = float(get_ratio()) if callable(get_ratio) else 1.0
        except (AttributeError, RuntimeError, TypeError):
            ratio = 1.0
    return ratio if ratio > 0.0 else 1.0


def _cache_pixmap(
    cache_key: tuple[int, int, int, float, float], pixmap: QPixmap
) -> QPixmap:
    _pixmap_cache[cache_key] = pixmap
    _pixmap_cache.move_to_end(cache_key)
    while len(_pixmap_cache) > _PIXMAP_CACHE_MAX:
        _pixmap_cache.popitem(last=False)
    return pixmap
