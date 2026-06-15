"""Universal composable Button widget.

Заменяет набор узкоспециализированных кнопок (Icon/Toggle/Scrollable/LongPress/...).
Конфигурируется kwargs'ами или `ButtonConfig`. Архитектура декомпозирована:

- `style_api._ButtonStyleApi` — публичные set/get визуальных атрибутов и
  обработка динамических Qt-properties.
- `events._ButtonEvents` — обработчики mouse/key/wheel/focus + click flow.
- `capabilities/` — composable behaviour (Scroll/LongPress/Menu).
- `painter.Painter` + `layers/` — рендер pipeline.

Сам класс Button содержит только: signals, state-properties, __init__,
capability API, state/value API и paint plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import warnings

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin, register_hover_widget

from .capabilities import (
    ButtonCapability,
    LongPressCapability,
    MenuCapability,
    ScrollCapability,
)
from .content import (
    ButtonRow,
    IconContent,
    IconTextContent,
    RowsContent,
    TextContent,
)
from .context import DrawContext
from .events import _ButtonEvents
from .layers._base import Layer
from .layers.ripple import RippleEffect
from .painter import Painter
from .regions import ButtonRegion, Divider, SingleRegionSplit, SplitLayout
from .state import ButtonState
from .style_api import _ButtonStyleApi, _normalize_underline_thickness
from .variants import get_variant


@dataclass
class ButtonConfig:
    """Декларативная конфигурация — альтернатива kwargs."""
    icon: Any = None
    text: str = ""
    rows: list[ButtonRow] | None = None
    toggle: bool = False
    scrollable: tuple[int, int] | None = None
    long_press: bool = False
    long_press_ms: int = 600
    badge: int | None = None
    show_underline: bool = False
    underline_color: Any = None
    underline_thickness: float | None = None
    menu: list[tuple[str, Any]] | None = None
    size: tuple[int, int] = (36, 36)
    icon_size: int = 22
    corner_radius: int | None = None
    border_color: QColor | None = None
    variant: str = "default"
    density: str = "normal"
    wheel_requires_focus: bool = False
    defer_click: bool = False


def _state_property(state: ButtonState):
    """Property-обёртка: bool геттер/сеттер, мутирующий StateSet и вызывающий update()."""

    def getter(self) -> bool:
        return state in self._region_states.get("_main", self._states)

    def setter(self, value: bool) -> None:
        states = self._region_states.get("_main", self._states)
        if value:
            states.add(state)
        else:
            states.discard(state)
        self.update()

    return property(getter, setter)


class Button(WheelScrollPolicyMixin, _ButtonStyleApi, _ButtonEvents, QWidget):
    clicked = pyqtSignal()
    pressed = pyqtSignal()
    released = pyqtSignal()
    toggled = pyqtSignal(bool)
    valueChanged = pyqtSignal(int)
    longPressed = pyqtSignal()
    rightClicked = pyqtSignal()
    middleClicked = pyqtSignal()
    menuTriggered = pyqtSignal(object)
    shortClicked = pyqtSignal()
    regionClicked = pyqtSignal(str)
    regionPressed = pyqtSignal(str)
    regionReleased = pyqtSignal(str)
    regionToggled = pyqtSignal(str, bool)
    regionValueChanged = pyqtSignal(str, int)
    regionLongPressed = pyqtSignal(str)
    regionMenuTriggered = pyqtSignal(str, object)

    triggered = menuTriggered  # backwards-compat alias

    # Имена-алиасы для подклассов (CalendarDayButton) и capabilities.
    _hovered = _state_property(ButtonState.HOVERED)
    _pressed = _state_property(ButtonState.PRESSED)
    _checked = _state_property(ButtonState.CHECKED)
    _is_scrolling = _state_property(ButtonState.SCROLLING)

    def __init__(
        self,
        icon: Any = None,
        *,
        text: str = "",
        rows: list[ButtonRow] | None = None,
        toggle: bool = False,
        scrollable: tuple[int, int] | None = None,
        long_press: bool = False,
        long_press_ms: int = 600,
        badge: int | None = None,
        show_underline: bool = False,
        underline_color: Any = None,
        underline_thickness: float | None = None,
        menu: list[tuple[str, Any]] | None = None,
        size: tuple[int, int] = (36, 36),
        icon_size: int = 22,
        corner_radius: int | None = None,
        border_color: QColor | None = None,
        variant: str = "default",
        density: str = "normal",
        wheel_requires_focus: bool = False,
        background_color: QColor | None = None,
        defer_click: bool = False,
        regions: list[ButtonRegion] | None = None,
        split: SplitLayout | None = None,
        divider: Divider | None = None,
        config: ButtonConfig | None = None,
        layers: list[Layer] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        if config is not None:
            icon = config.icon
            text = config.text
            rows = config.rows
            toggle = config.toggle
            scrollable = config.scrollable
            long_press = config.long_press
            long_press_ms = config.long_press_ms
            badge = config.badge
            show_underline = config.show_underline
            underline_color = config.underline_color
            underline_thickness = config.underline_thickness
            menu = config.menu
            size = config.size
            icon_size = config.icon_size
            corner_radius = config.corner_radius
            border_color = config.border_color
            variant = config.variant
            density = config.density
            wheel_requires_focus = config.wheel_requires_focus
            defer_click = config.defer_click

        if variant == "primary":
            warnings.warn(
                "Button variant 'primary' is deprecated; use 'surface' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            variant = "surface"

        self.init_wheel_scroll_policy(wheel_requires_focus=wheel_requires_focus)
        self._states: set[ButtonState] = set()
        self._region_states: dict[str, set[ButtonState]] = {"_main": self._states}
        self._regions: list[ButtonRegion] = []
        self._split: SplitLayout = split or SingleRegionSplit()
        self._divider: Divider | None = divider
        self._region_rects: dict[str, QRectF] = {}
        self._region_ripple: dict[str, RippleEffect] = {}
        self._region_scroll_ranges: dict[str, tuple[int, int]] = {}
        self._region_scroll_values: dict[str, int] = {}
        self._hovered_region: str | None = None
        self._pressed_region: str | None = None

        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            self._icon_unchecked, self._icon_checked = icon[0], icon[1]
        else:
            self._icon_unchecked = self._icon_checked = icon

        self._has_toggle = toggle
        self._has_scroll = scrollable is not None
        self._has_menu = menu is not None
        self._has_text = bool(text)
        self._text = text
        self._rows = rows or []
        self._rows_compact = False

        self._variant = variant
        self._density = density
        self._icon_size_px = icon_size
        if corner_radius is None:
            corner_radius = 2 if self._has_text else 6
        self._corner_radius_px = corner_radius
        self._border_color_override: QColor | None = border_color

        self.setProperty("variant", variant)
        self.setProperty("density", density)
        self.setProperty("iconSizePx", icon_size)
        self.setProperty("cornerRadiusPx", corner_radius)

        self._foreground_color: QColor | None = None
        self._background_color: QColor | None = None
        self._custom_bg_color: QColor | None = background_color
        self._accent_color: QColor | None = None
        self._show_underline = show_underline
        self._underline_thickness = _normalize_underline_thickness(underline_thickness)
        self._show_strike_through = False
        self._is_footer = False
        self._underline_config_color: QColor | list | None = underline_color
        self._override_bg_color: QColor | None = None
        self._badge = badge
        self._saved_value: int | None = None
        self._flyout_open = False

        if underline_color is not None:
            self.setProperty("underlineColor", underline_color)
        if self._underline_thickness is not None:
            self.setProperty("underlineThicknessPx", self._underline_thickness)

        if self._has_scroll:
            self._scroll_min, self._scroll_max = scrollable
            self._scroll_value = max(self._scroll_min, 1)
        else:
            self._scroll_min = self._scroll_max = self._scroll_value = 0

        w, h = size
        if self._has_text and w == 36 and h == 36:
            self.setMinimumHeight(32)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        elif w > 0 and h > 0:
            self.setFixedSize(w, h)
        elif h > 0:
            self.setFixedHeight(h)
        elif w > 0:
            self.setFixedWidth(w)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        register_hover_widget(self)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

        self._painter = Painter(self.theme_manager, layers=layers)
        self._ripple = RippleEffect(self)
        self._region_ripple["_main"] = self._ripple
        self._ripple_color_from = None
        self._ripple_color_to = None
        self._defer_click = bool(defer_click)

        self._capabilities: list[ButtonCapability] = []
        self._capability_map: dict[tuple[type, str], ButtonCapability] = {}

        if long_press:
            self.attach_capability(LongPressCapability(delay_ms=long_press_ms))
        if self._has_scroll:
            self.attach_capability(ScrollCapability())
        if self._has_menu:
            self.attach_capability(MenuCapability(menu_items=menu))

        self._value_popup = None
        self._popup_controller = None
        self._menu_items = menu

        if regions is None:
            regions = [
                ButtonRegion(
                    id="_main",
                    icon=icon,
                    text=text,
                    rows=rows,
                    toggle=toggle,
                    long_press=long_press,
                    long_press_ms=long_press_ms,
                    scrollable=scrollable,
                    menu=menu,
                    badge=badge,
                    variant=variant,
                    custom_bg_color=background_color,
                    show_underline=show_underline,
                    underline_color=underline_color,
                    underline_thickness=self._underline_thickness,
                    icon_size_px=icon_size,
                    override_border_color=border_color,
                )
            ]
        self.set_regions(regions, split=split, divider=divider)

    # -------- public API: capabilities --------

    def attach_capability(
        self,
        capability: ButtonCapability,
        region_id: str | None = None,
    ) -> None:
        key = (type(capability), region_id or "_main")
        if key in self._capability_map:
            self.detach_capability(type(capability), region_id=region_id)
        capability.attach(self, region_id=region_id or "_main")
        self._capabilities.append(capability)
        self._capability_map[key] = capability

    def detach_capability(
        self,
        capability_type: type[ButtonCapability],
        region_id: str | None = None,
    ) -> None:
        key = (capability_type, region_id or "_main")
        cap = self._capability_map.get(key)
        if cap:
            cap.detach(self)
            self._capabilities.remove(cap)
            del self._capability_map[key]

    def get_capability(
        self,
        capability_type: type[ButtonCapability],
        region_id: str | None = None,
    ) -> ButtonCapability | None:
        return self._capability_map.get((capability_type, region_id or "_main"))

    # -------- public API: regions --------

    def set_regions(
        self,
        regions: list[ButtonRegion],
        *,
        split: SplitLayout | None = None,
        divider: Divider | None = None,
    ) -> None:
        if not regions:
            regions = [ButtonRegion(id="_main")]
        seen: set[str] = set()
        normalized: list[ButtonRegion] = []
        for region in regions:
            if not region.id or region.id in seen:
                raise ValueError(f"duplicate or empty button region id: {region.id!r}")
            seen.add(region.id)
            normalized.append(region)
        self._regions = normalized
        if split is not None:
            self._split = split
        elif len(normalized) == 1:
            self._split = SingleRegionSplit()
        if divider is not None or len(normalized) == 1:
            self._divider = divider
        for region in normalized:
            states = self._region_states.setdefault(region.id, set())
            if region.id == "_main":
                self._states = states
            if region.enabled:
                states.discard(ButtonState.DISABLED)
            else:
                states.add(ButtonState.DISABLED)
            self._region_ripple.setdefault(region.id, RippleEffect(self))
            if region.scrollable is not None:
                min_v, max_v = region.scrollable
                self._region_scroll_ranges[region.id] = (int(min_v), int(max_v))
                self._region_scroll_values.setdefault(
                    region.id,
                    max(int(min_v), min(int(max_v), max(int(min_v), 1))),
                )
            else:
                self._region_scroll_ranges.pop(region.id, None)
                self._region_scroll_values.pop(region.id, None)
            if region.long_press and self.get_capability(LongPressCapability, region.id) is None:
                self.attach_capability(
                    LongPressCapability(delay_ms=region.long_press_ms),
                    region_id=region.id,
                )
            if region.scrollable and self.get_capability(ScrollCapability, region.id) is None:
                self.attach_capability(ScrollCapability(), region_id=region.id)
            if region.menu and self.get_capability(MenuCapability, region.id) is None:
                self.attach_capability(
                    MenuCapability(menu_items=region.menu),
                    region_id=region.id,
                )
        for region_id in list(self._region_states):
            if region_id not in seen:
                del self._region_states[region_id]
                self._region_ripple.pop(region_id, None)
                self._region_scroll_ranges.pop(region_id, None)
                self._region_scroll_values.pop(region_id, None)
        self._recompute_region_rects()
        self.update()

    def regions(self) -> list[ButtonRegion]:
        return list(self._regions)

    # -------- public API: state/value --------

    def setChecked(self, checked: bool, emit: bool = True, emit_signal: bool | None = None):
        """emit_signal — backwards-compat alias for emit."""
        if emit_signal is not None:
            emit = emit_signal
        if not self._has_toggle:
            return
        if self._checked != checked:
            self._checked = checked
            if emit:
                self.toggled.emit(checked)
                self.regionToggled.emit("_main", checked)

    def isChecked(self) -> bool:
        return self._checked

    def setValue(self, val: int):
        if not self._has_scroll:
            return
        val = max(self._scroll_min, min(self._scroll_max, val))
        if self._scroll_value != val:
            self._scroll_value = val
            self.update()

    def getValue(self) -> int:
        return self._scroll_value

    set_value = setValue
    get_value = getValue

    def setRange(self, min_v: int, max_v: int):
        self._scroll_min = min_v
        self._scroll_max = max_v
        self._scroll_value = max(min_v, min(max_v, self._scroll_value))

    def get_saved_value(self) -> int | None:
        return self._saved_value

    def set_saved_value(self, value: int | None):
        self._saved_value = value

    # -------- paint --------

    def _build_content(self):
        if self._rows:
            return RowsContent(rows=self._rows, compact=self._rows_compact)
        if self._has_text and self._text and self._icon_unchecked:
            return IconTextContent(icon=self._icon_unchecked, text=self._text)
        if self._has_text and self._text:
            return TextContent(text=self._text)
        if self._icon_unchecked or self._icon_checked:
            return IconContent(icon_unchecked=self._icon_unchecked,
                               icon_checked=self._icon_checked)
        return None

    def _build_region_content(self, region: ButtonRegion):
        rows = region.rows or []
        if rows:
            return RowsContent(rows=rows, compact=self._rows_compact)
        icon = region.icon
        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            icon_unchecked, icon_checked = icon[0], icon[1]
        else:
            icon_unchecked = icon_checked = icon
        if region.text and icon_unchecked:
            return IconTextContent(icon=icon_unchecked, text=region.text)
        if region.text:
            return TextContent(text=region.text)
        if icon_unchecked or icon_checked:
            return IconContent(icon_unchecked=icon_unchecked, icon_checked=icon_checked)
        return None

    def _make_context(self, qpainter: QPainter) -> DrawContext:
        return DrawContext(
            widget=self,
            painter=qpainter,
            rect=QRectF(self.rect()),
            states=frozenset(self._states),
            variant=get_variant(self._variant),
            corner_radius=max(0, int(self._corner_radius_px)),
            content=self._build_content(),
            override_bg_color=self._override_bg_color,
            custom_bg_color=self._custom_bg_color,
            override_border_color=self._border_color_override,
            badge_text=str(self._badge) if self._badge is not None else None,
            show_underline=self._show_underline,
            underline_color=self._underline_config_color,
            underline_thickness=self._underline_thickness,
            show_strike_through=self._is_strike_through(),
            is_footer=self._is_footer,
            icon_size_px=self._icon_size_px,
            scroll_value=self._scroll_value if self._has_scroll else None,
            scroll_value_always_visible=self._has_scroll and not self._has_toggle,
        )

    def iter_regions(self, ctx: DrawContext):
        if not self._region_rects:
            self._recompute_region_rects()
        for region in self._regions:
            rect = self._region_rects.get(region.id)
            if rect is None:
                continue
            states = frozenset(self._region_states.get(region.id, set()))
            yield ctx.scoped_to(
                region_id=region.id,
                rect=rect,
                states=states,
                content=self._build_region_content(region),
                variant=get_variant(region.variant or self._variant),
                override_bg_color=region.override_bg_color,
                custom_bg_color=region.custom_bg_color,
                override_border_color=region.override_border_color,
                show_underline=region.show_underline,
                underline_color=region.underline_color,
                underline_thickness=region.underline_thickness,
                icon_size_px=region.icon_size_px,
            )

    def region_states(self, region_id: str) -> frozenset[ButtonState]:
        return frozenset(self._region_states.get(region_id, set()))

    def region_ripple(self, region_id: str) -> RippleEffect | None:
        return self._region_ripple.get(region_id)

    def _recompute_region_rects(self) -> None:
        rect = QRectF(self.rect())
        rects = self._split.compute(rect, self._regions)
        self._region_rects = {
            region.id: QRectF(region.rect_fn(rect) if region.rect_fn else region_rect)
            for region, region_rect in zip(self._regions, rects)
        }

    def resizeEvent(self, event):
        self._recompute_region_rects()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._painter.paint(self._make_context(painter))
        finally:
            painter.end()

    # -------- private behaviour helpers --------

    def _do_toggle_scroll_click(self):
        if not self._checked:
            if self._scroll_value > 0:
                self._saved_value = self._scroll_value
            self._scroll_value = 0
            self._checked = True
            self.toggled.emit(True)
            self.valueChanged.emit(0)
        else:
            restored = self._saved_value if self._saved_value and self._saved_value > 0 else 1
            self._saved_value = None
            self._scroll_value = restored
            self._checked = False
            self.toggled.emit(False)
            self.valueChanged.emit(restored)


# Backwards-compat: ButtonRow re-exported from button module.
__all__ = ["Button", "ButtonConfig", "ButtonRow"]
