"""Region layout primitives for multi-area toolkit buttons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol

from PySide6.QtCore import QLineF, QRectF
from PySide6.QtGui import QColor, QCursor, QPainterPath

from .content import ButtonRow
from .state import ButtonState

if TYPE_CHECKING:
    from .button import Button


RectFn = Callable[[QRectF], QRectF]
PathFn = Callable[[QRectF], QPainterPath]
ActionCallback = Callable[[str, Any], None]


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
    menu: list[tuple[str, Any]] | None = None
    # Dispatched via Button.actionTriggered on a plain click, in addition to
    # regionClicked — the same mechanism ButtonSpec/RegionSpec used to offer
    # only when built through the declarative spec= path.
    action: str | None = None
    action_data: Any = None
    action_callback: ActionCallback | None = None
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
    corner_radii: tuple[int, int, int, int] | None = None
    group: str | None = None


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


_REGION_RUNTIME_STATES = {"checked": ButtonState.CHECKED}
_REGION_READONLY_STATES = {"hovered": ButtonState.HOVERED, "pressed": ButtonState.PRESSED}


class RegionHandle:
    """Single read/write handle for one region of a multi-region ``Button``.

    Hides the split between static ``ButtonRegion`` config (icon, text,
    colors, ...) and runtime ``ButtonState`` (checked, hovered, pressed, ...)
    behind plain attribute access, e.g. ``button.region("copy").checked = True``
    or ``button.region("copy").text = "Copied!"``. Callers never need to know
    which storage a given field lives in.
    """

    def __init__(self, button: "Button", region_id: str) -> None:
        object.__setattr__(self, "_button", button)
        object.__setattr__(self, "_region_id", region_id)

    @property
    def id(self) -> str:
        return self._region_id

    def _region(self) -> ButtonRegion:
        region = self._button._region_by_id(self._region_id)
        if region is None:
            raise ValueError(f"unknown button region id: {self._region_id!r}")
        return region

    def __getattr__(self, name: str) -> Any:
        if name in _REGION_RUNTIME_STATES or name in _REGION_READONLY_STATES:
            state = (_REGION_RUNTIME_STATES | _REGION_READONLY_STATES)[name]
            return state in self._button._controller.states(self._region_id)
        region = self._region()
        if hasattr(region, name):
            return getattr(region, name)
        raise AttributeError(f"ButtonRegion has no field {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _REGION_READONLY_STATES:
            raise AttributeError(f"{name!r} is read-only; it is driven by user interaction")
        if name in _REGION_RUNTIME_STATES:
            self._button.setRegionChecked(self._region_id, bool(value))
            return
        region = self._region()
        if not hasattr(region, name):
            raise AttributeError(f"ButtonRegion has no field {name!r}")
        self._button.update_region(self._region_id, **{name: value})

    def __repr__(self) -> str:
        return f"RegionHandle(id={self._region_id!r})"
