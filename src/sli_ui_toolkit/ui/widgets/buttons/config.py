"""Button content types — union of all possible rendering content."""

from dataclasses import dataclass
from typing import Any
from PyQt6.QtGui import QColor, QPixmap


@dataclass
class TextContent:
    """Single-line text content."""
    text: str
    size: int = 12
    weight: str = "normal"
    color: QColor | None = None


@dataclass
class RowsContent:
    """Multi-row text content with individual styling."""
    rows: list["ButtonRow"]  # list[ButtonRow] from button.py
    compact: bool = False
    row_gap: int = 2


@dataclass
class IconContent:
    """Icon-only content (standard, hover-value, or scroll-value)."""
    icon_unchecked: Any = None
    icon_checked: Any = None
    icon_size_px: int = 22


@dataclass
class IconTextContent:
    """Icon with adjacent text."""
    icon_unchecked: Any = None
    icon_checked: Any = None
    text: str = ""
    icon_size_px: int = 22
    text_size: int = 12


# Union of all content types
ButtonContent = TextContent | RowsContent | IconContent | IconTextContent | None
