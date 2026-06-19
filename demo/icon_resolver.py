"""Demo icon resolver — synthesises simple monochrome pixmaps for named icons.

The toolkit ships without bundled icon assets; this module provides a tiny
in-process resolver so demo widgets that look up icons by name (add/remove/
divider_hidden/...) get something visible.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from sli_ui_toolkit.theme import ThemeManager


_GLYPHS: dict[str, str] = {
    "add": "+",
    "add_circle": "+",
    "remove": "−",
    "delete": "×",
    "close": "×",
    "check": "✓",
    "chevron_down": "▾",
    "chevron_up": "▴",
    "chevron_left": "◂",
    "chevron_right": "▸",
    "divider_hidden": "∅",
    "line_weight": "≡",
    "info": "i",
    "warning": "!",
    "error": "!",
    "settings": "⚙",
    "folder": "▣",
    "file": "▭",
    "edit": "✎",
    "save": "▤",
    "search": "⌕",
    "menu": "≡",
    "more": "⋯",
    "play": "▶",
    "pause": "‖",
    "stop": "■",
}


def _foreground() -> QColor:
    try:
        return QColor(ThemeManager.get_instance().get_color("dialog.text"))
    except Exception:
        return QColor("#1f1f1f")


def _build_pixmap(glyph: str, size: int = 32) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = _foreground()
        painter.setPen(QPen(color))
        font = painter.font()
        font.setPixelSize(int(size * 0.7))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    finally:
        painter.end()
    return pixmap


def demo_icon_resolver(icon: object) -> QIcon:
    """Resolve a named icon (or arbitrary value) into a glyph QIcon."""
    name = None
    if isinstance(icon, str):
        name = icon
    else:
        value = getattr(icon, "value", None)
        if isinstance(value, str):
            name = value
        elif isinstance(value, (int, float)):
            name = str(value)

    glyph = _GLYPHS.get(name or "", "•")
    qicon = QIcon()
    for size in (16, 20, 24, 32, 48):
        qicon.addPixmap(_build_pixmap(glyph, size))
    return qicon
