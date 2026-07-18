"""Layout output model for help document body painting and hit-testing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap, QTextLayout

AssetResolver = Callable[[str], str | Path | QPixmap | None]


@dataclass(frozen=True, slots=True)
class LinkHitBox:
    rect: QRectF
    href: str


@dataclass(frozen=True, slots=True)
class TextFragment:
    rect: QRectF
    global_start: int
    global_end: int
    layout: QTextLayout
    links: tuple[LinkHitBox, ...]


@dataclass(frozen=True, slots=True)
class PixmapFragment:
    rect: QRectF
    pixmap: QPixmap | None
    alt: str
    source_path: str = ""


@dataclass(frozen=True, slots=True)
class LayoutResult:
    width: float
    height: float
    text_fragments: tuple[TextFragment, ...]
    pixmaps: tuple[PixmapFragment, ...]
    anchors: dict[str, float]
