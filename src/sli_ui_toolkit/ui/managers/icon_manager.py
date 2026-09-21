import os
from functools import lru_cache

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale

# Raster target for resolution-independent sources (SVG): design px at
# UiScale 1.0, resolved through scaled_px() so the cached pixmap stays
# crisp when the interface factor grows.
_SVG_RASTER_PX = 256


def _scale_key() -> float:
    try:
        return UiScale.get_instance().factor()
    except Exception:
        return 1.0


def _content_key(path_to_icon: str) -> tuple[int, int]:
    """(mtime_ns, size) so edited icon files re-raster instead of serving stale art."""
    try:
        st = os.stat(path_to_icon)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _recolor_pixmap(source_pixmap: QPixmap) -> QPixmap:
    result_pixmap = QPixmap(source_pixmap.size())
    result_pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result_pixmap)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
    )
    painter.drawPixmap(0, 0, source_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result_pixmap.rect(), QColor("white"))
    painter.end()
    return result_pixmap


@lru_cache(maxsize=128)
def _get_themed_icon_cached(
    path_to_icon: str, is_dark: bool, scale_key: float, content_key: tuple[int, int]
) -> QIcon:
    """Cached worker — never call directly, use :func:`get_themed_icon`.

    ``scale_key`` / ``content_key`` are key-only inputs (unused in the
    body): they bust the cache when the interface factor or the file
    content changes. Both themes raster through the same per-size
    pipeline (symmetric raster): the dark branch used to collapse to one
    256 px pixmap while light kept the source's native multi-resolution
    sizes, so dark icons scaled down blurrier than light ones.
    """
    del scale_key, content_key
    if not path_to_icon or not os.path.exists(path_to_icon):
        return QIcon()

    source_icon = QIcon(path_to_icon)

    if not is_dark:
        return source_icon

    sizes = [s for s in source_icon.availableSizes() if s.isValid()]
    if not sizes:
        try:
            fallback = max(1, UiScale.get_instance().scaled_px(_SVG_RASTER_PX))
        except Exception:
            fallback = _SVG_RASTER_PX
        sizes = [QSize(fallback, fallback)]

    result = QIcon()
    for size in sizes:
        source_pixmap = source_icon.pixmap(size)
        if source_pixmap.isNull():
            continue
        result.addPixmap(_recolor_pixmap(source_pixmap))
    if result.isNull():
        return source_icon
    return result


def get_themed_icon(path_to_icon: str, is_dark: bool) -> QIcon:
    return _get_themed_icon_cached(
        path_to_icon, is_dark, _scale_key(), _content_key(path_to_icon)
    )


def clear_icon_cache() -> None:
    """Drop all cached themed icons (palette swap, icon pack reload, tests)."""
    _get_themed_icon_cached.cache_clear()


def get_icon_by_path(icon_path: str) -> QIcon:
    theme_manager = ThemeManager.get_instance()
    return get_themed_icon(icon_path, theme_manager.is_dark())
