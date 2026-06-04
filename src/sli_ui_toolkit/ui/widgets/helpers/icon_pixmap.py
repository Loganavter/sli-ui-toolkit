from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap

from sli_ui_toolkit.icons import resolve_icon


def normalized_icon_pixmap(icon_value, size: int | QSize) -> QPixmap:
    if isinstance(size, QSize):
        target_w = max(1, int(size.width()))
        target_h = max(1, int(size.height()))
    else:
        target_w = target_h = max(1, int(size))

    icon = icon_value if isinstance(icon_value, QIcon) else resolve_icon(icon_value)
    scale = 4
    source_w = target_w * scale
    source_h = target_h * scale
    pixmap = icon.pixmap(QSize(source_w, source_h))
    if pixmap.isNull():
        return pixmap

    bbox = _alpha_bbox(pixmap)
    if bbox is None:
        return icon.pixmap(QSize(target_w, target_h))

    left, top, right, bottom = bbox
    content_w = right - left + 1
    content_h = bottom - top + 1
    if content_w <= 0 or content_h <= 0:
        return icon.pixmap(QSize(target_w, target_h))

    target_content_w = target_w - 2
    target_content_h = target_h - 2
    source_content_limit_w = target_content_w * scale
    source_content_limit_h = target_content_h * scale
    if content_w >= source_content_limit_w and content_h >= source_content_limit_h:
        return icon.pixmap(QSize(target_w, target_h))

    cropped = pixmap.copy(left, top, content_w, content_h)
    max_w = max(1, target_content_w)
    max_h = max(1, target_content_h)
    scaled = cropped.scaled(
        max_w,
        max_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    result = QPixmap(target_w, target_h)
    result.fill(Qt.GlobalColor.transparent)
    from PyQt6.QtGui import QPainter

    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        x = (target_w - scaled.width()) // 2
        y = (target_h - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
    finally:
        painter.end()
    return result


def _alpha_bbox(pixmap: QPixmap) -> tuple[int, int, int, int] | None:
    image = pixmap.toImage()
    width = image.width()
    height = image.height()
    left = width
    top = height
    right = -1
    bottom = -1

    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 0:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if right < left or bottom < top:
        return None
    return left, top, right, bottom
