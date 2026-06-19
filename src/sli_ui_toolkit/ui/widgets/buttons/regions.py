"""Region layout primitives for multi-area toolkit buttons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from PySide6.QtCore import QLineF, QRectF
from PySide6.QtGui import QColor, QCursor, QPainterPath

from .content import ButtonRow


RectFn = Callable[[QRectF], QRectF]
PathFn = Callable[[QRectF], QPainterPath]


@dataclass
class ButtonRegion:
    id: str
    weight: float = 1.0
    icon: Any = None
    text: str = ""
    rows: list[ButtonRow] | None = None
    toggle: bool = False
    long_press: bool = False
    long_press_ms: int = 600
    scrollable: tuple[int, int] | None = None
    menu: list[tuple[str, Any]] | None = None
    badge: int | str | None = None
    variant: str | None = None
    custom_bg_color: QColor | None = None
    override_bg_color: QColor | None = None
    override_border_color: QColor | None = None
    show_underline: bool | None = None
    underline_color: Any = None
    underline_thickness: float | None = None
    icon_size_px: int | None = None
    show_strike_through: bool = False
    enabled: bool = True
    cursor: QCursor | None = None
    rect_fn: RectFn | None = None
    path_fn: PathFn | None = None
    z_index: int = 0


class SplitLayout(Protocol):
    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        ...

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        ...


class SingleRegionSplit:
    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        return [QRectF(rect) for _region in regions]

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return []


class HorizontalSplit:
    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        total = sum(max(0.0, region.weight) for region in regions) or len(regions) or 1
        x = rect.left()
        out: list[QRectF] = []
        for index, region in enumerate(regions):
            if index == len(regions) - 1:
                w = rect.right() - x + 1.0
            else:
                w = rect.width() * (max(0.0, region.weight) / total)
            out.append(QRectF(x, rect.top(), w, rect.height()))
            x += w
        return out

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return [
            QLineF(rect.right(), rect.top(), rect.right(), rect.bottom())
            for rect in rects[:-1]
        ]


class VerticalSplit:
    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        total = sum(max(0.0, region.weight) for region in regions) or len(regions) or 1
        y = rect.top()
        out: list[QRectF] = []
        for index, region in enumerate(regions):
            if index == len(regions) - 1:
                h = rect.bottom() - y + 1.0
            else:
                h = rect.height() * (max(0.0, region.weight) / total)
            out.append(QRectF(rect.left(), y, rect.width(), h))
            y += h
        return out

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return [
            QLineF(rect.left(), rect.bottom(), rect.right(), rect.bottom())
            for rect in rects[:-1]
        ]


class GridSplit:
    def __init__(self, rows: int, cols: int) -> None:
        self.rows = max(1, int(rows))
        self.cols = max(1, int(cols))

    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        cell_w = rect.width() / self.cols
        cell_h = rect.height() / self.rows
        out: list[QRectF] = []
        for index, _region in enumerate(regions):
            row = index // self.cols
            col = index % self.cols
            if row >= self.rows:
                break
            out.append(QRectF(
                rect.left() + col * cell_w,
                rect.top() + row * cell_h,
                cell_w,
                cell_h,
            ))
        return out

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return []


class CustomSplit:
    def __init__(self, rect_fns: list[RectFn]) -> None:
        self.rect_fns = list(rect_fns)

    def compute(self, rect: QRectF, regions: list[ButtonRegion]) -> list[QRectF]:
        out: list[QRectF] = []
        for index, region in enumerate(regions):
            fn = region.rect_fn or (
                self.rect_fns[index] if index < len(self.rect_fns) else None
            )
            out.append(QRectF(fn(rect) if fn is not None else rect))
        return out

    def dividers(self, rects: list[QRectF]) -> list[QLineF]:
        return []


@dataclass
class Divider:
    color_token: str = "separator.color"
    fallback_token: str = "dialog.border"
    thickness: float = 1.0
    margin: float = 2.0
