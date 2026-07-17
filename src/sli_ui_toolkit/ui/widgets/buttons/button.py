"""Universal composable Button widget.

Заменяет набор узкоспециализированных кнопок (Icon/Toggle/LongPress/...).
Конфигурируется kwargs'ами или `ButtonConfig`. Архитектура декомпозирована:

- `style_api._ButtonStyleApi` — публичные set/get визуальных атрибутов и
  обработка динамических Qt-properties.
- `events._ButtonEvents` — обработчики mouse/key/wheel/focus + click flow.
- `capabilities/` — composable behaviour (LongPress/...). Приложения
  могут добавлять свои capabilities через `attach_capability()` — Button не
  завязан на конкретные типы (см. `ButtonCapability.handle_wheel_event` для
  примера того, как накрафтить собственный scroll-counter на app-уровне).
- `painter.Painter` + `layers/` — рендер pipeline.

Сам класс Button содержит только: signals, state-properties, __init__,
capability API, state/value API и paint plumbing.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.deprecations import (
    BUTTON_PRIMARY_VARIANT,
    BUTTON_SET_CHECKED_EMIT_SIGNAL,
    warn_deprecated,
)
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin, register_hover_widget

from .capabilities import (
    ButtonCapability,
    LongPressCapability,
)
from .content import (
    ButtonRow,
    IconContent,
    IconTextContent,
    RowsContent,
    TextContent,
)
from .controller import ButtonController
from .context import DrawContext
from .events import _ButtonEvents
from .layers._base import Layer
from .layers.ripple import RippleEffect
from .painter import Painter
from .regions import ButtonRegion, Divider, RegionHandle, SingleRegionSplit, SplitLayout
from .specs import ButtonSpec, ShapeSpec, normalize_corner_radii
from .state import ButtonState
from .style_api import (
    _ButtonStyleApi,
    _normalize_underline_thickness,
    normalize_content_padding,
)
from .variants import get_variant


@dataclass
class ButtonConfig:
    """Декларативная конфигурация — альтернатива kwargs."""
    icon: Any = None
    text: str = ""
    rows: list[ButtonRow] | None = None
    toggle: bool = False
    long_press: bool = False
    long_press_ms: int = 600
    badge: int | None = None
    show_underline: bool = False
    underline_color: Any = None
    underline_thickness: float | None = None
    size: tuple[int, int] = (36, 36)
    icon_size: int = 22
    corner_radius: int | None = None
    corner_radii: tuple[int, int, int, int] | None = None
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
    clicked = Signal()
    pressed = Signal()
    released = Signal()
    toggled = Signal(bool)
    longPressed = Signal()
    rightClicked = Signal()
    middleClicked = Signal()
    shortClicked = Signal()
    regionClicked = Signal(str)
    regionPressed = Signal(str)
    regionReleased = Signal(str)
    regionToggled = Signal(str, bool)
    regionLongPressed = Signal(str)
    actionTriggered = Signal(str, object)

    # Имена-алиасы для подклассов (CalendarDayButton) и capabilities.
    _hovered = _state_property(ButtonState.HOVERED)
    _pressed = _state_property(ButtonState.PRESSED)
    _checked = _state_property(ButtonState.CHECKED)

    def __init__(
        self,
        icon: Any = None,
        *,
        text: str = "",
        rows: list[ButtonRow] | None = None,
        toggle: bool = False,
        long_press: bool = False,
        long_press_ms: int = 600,
        badge: int | None = None,
        show_underline: bool = False,
        underline_color: Any = None,
        underline_thickness: float | None = None,
        size: tuple[int, int] = (36, 36),
        icon_size: int = 22,
        gap: int = 6,
        content_align: Qt.AlignmentFlag = (
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        ),
        content_padding: float | tuple[float, float, float, float] = 0.0,
        corner_radius: int | None = None,
        corner_radii: tuple[int, int, int, int] | None = None,
        border_color: QColor | None = None,
        variant: str = "default",
        density: str = "normal",
        wheel_requires_focus: bool = False,
        background_color: QColor | None = None,
        defer_click: bool = False,
        regions: list[ButtonRegion] | None = None,
        split: SplitLayout | None = None,
        divider: Divider | None = None,
        spec: ButtonSpec | None = None,
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
            long_press = config.long_press
            long_press_ms = config.long_press_ms
            badge = config.badge
            show_underline = config.show_underline
            underline_color = config.underline_color
            underline_thickness = config.underline_thickness
            size = config.size
            icon_size = config.icon_size
            corner_radius = config.corner_radius
            corner_radii = config.corner_radii
            border_color = config.border_color
            variant = config.variant
            density = config.density
            wheel_requires_focus = config.wheel_requires_focus
            defer_click = config.defer_click

        if spec is not None:
            regions = spec.to_regions()
            split = spec.split
            divider = spec.divider
            size = spec.shape.size
            icon_size = spec.shape.icon_size
            corner_radius = spec.shape.corner_radius
            corner_radii = spec.shape.corner_radii
            variant = spec.variant
            density = spec.density
            wheel_requires_focus = spec.wheel_requires_focus
            defer_click = spec.defer_click
            if regions and regions[0].id == "_main":
                main = regions[0]
                icon = main.icon
                text = main.text
                rows = main.rows
                toggle = main.toggle
                long_press = main.long_press
                long_press_ms = main.long_press_ms
                badge = main.badge
                show_underline = bool(main.show_underline)
                underline_color = main.underline_color
                underline_thickness = main.underline_thickness
                background_color = main.custom_bg_color
                border_color = main.override_border_color

        if variant == "primary":
            warn_deprecated(BUTTON_PRIMARY_VARIANT, stacklevel=2)
            variant = "surface"

        self.init_wheel_scroll_policy(wheel_requires_focus=wheel_requires_focus)
        self._states: set[ButtonState] = set()
        self._region_states: dict[str, set[ButtonState]] = {"_main": self._states}
        self._regions: list[ButtonRegion] = []
        self._split: SplitLayout = split or SingleRegionSplit()
        self._divider: Divider | None = divider
        self._region_rects: dict[str, QRectF] = {}
        self._region_paths = {}
        self._region_ripple: dict[str, RippleEffect] = {}
        self._hovered_region: str | None = None
        self._pressed_region: str | None = None

        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            self._icon_unchecked, self._icon_checked = icon[0], icon[1]
        else:
            self._icon_unchecked = self._icon_checked = icon

        self._has_toggle = toggle
        self._has_text = bool(text)
        self._text = text
        self._rows = rows or []
        self._rows_compact = False

        self._variant = variant
        self._density = density
        self._icon_size_px = icon_size
        self._gap_px = max(0, int(gap))
        self._content_align = content_align
        self._content_padding = normalize_content_padding(content_padding)
        if corner_radius is None:
            corner_radius = 2 if self._has_text else 6
        self._corner_radius_px = corner_radius
        self._corner_radii_px: tuple[int, int, int, int] | None = (
            tuple(int(r) for r in corner_radii) if corner_radii is not None else None
        )
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
        self._bg_locked = False
        self._hover_color: QColor | None = None
        self._hover_compose: str = "replace"
        self._badge = badge
        self._flyout_open = False

        if underline_color is not None:
            self.setProperty("underlineColor", underline_color)
        if self._underline_thickness is not None:
            self.setProperty("underlineThicknessPx", self._underline_thickness)

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
        self._controller = ButtonController(self)

        if long_press:
            self.attach_capability(LongPressCapability(delay_ms=long_press_ms))

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
        if spec is not None:
            self.set_spec(spec)
        else:
            self.set_regions(regions, split=split, divider=divider)

    @classmethod
    def from_spec(
        cls,
        spec: ButtonSpec,
        *,
        parent: QWidget | None = None,
        layers: list[Layer] | None = None,
    ) -> "Button":
        return cls(spec=spec, parent=parent, layers=layers)

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
        effective_split = split if split is not None else (
            SingleRegionSplit() if len(normalized) == 1 else self._split
        )
        effective_divider = divider if (divider is not None or len(normalized) == 1) else self._divider
        self._controller.set_regions(
            normalized,
            split=effective_split,
            divider=effective_divider,
            shape=ShapeSpec(
                corner_radius=self._corner_radius_px,
                corner_radii=self._corner_radii_px,
                size=(self.width(), self.height()),
                icon_size=self._icon_size_px,
            ),
            variant=self._variant,
            density=self._density,
            defer_click=self._defer_click,
            wheel_requires_focus=getattr(self, "_wheel_requires_focus", False),
        )
        self._sync_region_aliases()
        self._detach_stale_region_capabilities(normalized)
        self._attach_region_capabilities(normalized)
        self._recompute_region_rects()
        self.update()

    def set_spec(self, spec: ButtonSpec) -> None:
        self._apply_spec_widget_properties(spec)
        self._controller.set_spec(spec)
        self._sync_region_aliases()
        self._detach_stale_region_capabilities(self._regions)
        self._attach_region_capabilities(self._regions)
        self._recompute_region_rects()
        self.update()

    def regions(self) -> list[ButtonRegion]:
        return list(self._regions)

    def region(self, region_id: str) -> RegionHandle:
        """Live read/write handle for a single region.

        Hides the split between static ``ButtonRegion`` fields (icon, text,
        colors, ...) and runtime state (checked, hovered, pressed): both are
        readable/writable as plain attributes, e.g.
        ``button.region("copy").checked = True``.
        """
        if self._region_by_id(region_id) is None:
            raise ValueError(f"unknown button region id: {region_id!r}")
        return RegionHandle(self, region_id)

    def update_region(self, region_id: str, **changes: Any) -> None:
        """Replace one or more static ``ButtonRegion`` fields for ``region_id``.

        Other regions, and this region's runtime state (hover/ripple/checked),
        are preserved — ``set_regions`` reconciles by region id.
        """
        if not changes:
            return
        regions = list(self._controller.regions)
        for index, region in enumerate(regions):
            if region.id == region_id:
                regions[index] = dataclasses.replace(region, **changes)
                break
        else:
            raise ValueError(f"unknown button region id: {region_id!r}")
        self.set_regions(regions)

    def spec(self) -> ButtonSpec:
        return self._controller.spec

    def _sync_region_aliases(self) -> None:
        self._regions = self._controller.regions
        self._split = self._controller.split
        self._divider = self._controller.divider
        self._region_rects = self._controller.rects
        self._region_paths = self._controller.paths
        self._region_states = {
            region_id: runtime.states
            for region_id, runtime in self._controller.runtime.items()
        }
        self._region_ripple = {
            region_id: runtime.ripple
            for region_id, runtime in self._controller.runtime.items()
            if runtime.ripple is not None
        }
        self._states = self._region_states.setdefault("_main", self._states)
        self._ripple = self._region_ripple.get("_main", self._ripple)

    def _apply_spec_widget_properties(self, spec: ButtonSpec) -> None:
        self._variant = spec.variant
        self._density = spec.density
        self._defer_click = bool(spec.defer_click)
        self.set_wheel_requires_focus(spec.wheel_requires_focus)
        self.setProperty("variant", self._variant)
        self.setProperty("density", self._density)
        self._icon_size_px = int(spec.shape.icon_size)
        self.setProperty("iconSizePx", self._icon_size_px)
        if spec.shape.corner_radius is not None:
            self._corner_radius_px = int(spec.shape.corner_radius)
            self.setProperty("cornerRadiusPx", self._corner_radius_px)
        if spec.shape.corner_radii is not None:
            self._corner_radii_px = tuple(int(r) for r in spec.shape.corner_radii)
        else:
            self._corner_radii_px = None
        w, h = spec.shape.size
        if w > 0 and h > 0:
            self.setFixedSize(int(w), int(h))
        elif h > 0:
            self.setFixedHeight(int(h))
        elif w > 0:
            self.setFixedWidth(int(w))

    def _detach_stale_region_capabilities(self, regions: list[ButtonRegion]) -> None:
        """Detach capabilities left over from regions that no longer exist.

        `set_regions`/`set_spec` are meant to be callable repeatedly as app
        state reshapes the button (e.g. 2 regions collapsing into 1).
        Capabilities are keyed by region id in `_capability_map`, so without
        this pass a region's capability (and its QTimer) would leak forever
        once that region id stops appearing in the new region set.
        """
        live_ids = {region.id for region in regions}
        for capability_type, region_id in list(self._capability_map.keys()):
            if region_id not in live_ids:
                self.detach_capability(capability_type, region_id=region_id)

    def _attach_region_capabilities(self, regions: list[ButtonRegion]) -> None:
        for region in regions:
            if region.long_press and self.get_capability(LongPressCapability, region.id) is None:
                self.attach_capability(
                    LongPressCapability(delay_ms=region.long_press_ms),
                    region_id=region.id,
                )

    # -------- public API: state/value --------

    def setChecked(self, checked: bool, emit: bool = True, emit_signal: bool | None = None):
        """emit_signal — backwards-compat alias for emit."""
        if emit_signal is not None:
            warn_deprecated(BUTTON_SET_CHECKED_EMIT_SIGNAL, stacklevel=2)
            emit = emit_signal
        if not self._has_toggle:
            return
        self.setRegionChecked("_main", checked, emit=emit)

    def isChecked(self) -> bool:
        return self._checked

    def setRegionChecked(self, region_id: str, checked: bool, *, emit: bool = True) -> None:
        """Programmatically set the CHECKED state of any region (not just `"_main"`).

        Generalizes `setChecked` — same effect a user click would have on a
        `toggle=True` region. When the region belongs to a ``group=``, CHECKED
        mirrors to every sibling in that group (same as HOVERED/PRESSED).
        """
        checked = bool(checked)
        linked = self._linked_region_ids(region_id)
        if all(
            (ButtonState.CHECKED in self._controller.states(rid)) == checked
            for rid in linked
        ):
            return
        self._set_region_state(region_id, ButtonState.CHECKED, checked)
        if "_main" in linked:
            self._checked = checked
        if emit:
            self.regionToggled.emit(region_id, checked)
            if region_id == "_main" or "_main" in linked:
                self.toggled.emit(checked)

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
            corner_radii=normalize_corner_radii(
                self._corner_radius_px,
                self._corner_radii_px,
                fallback=max(0, int(self._corner_radius_px)),
            ),
            content=self._build_content(),
            override_bg_color=self._override_bg_color,
            custom_bg_color=self._custom_bg_color,
            override_border_color=self._border_color_override,
            hover_color=getattr(self, "_hover_color", None),
            hover_compose=getattr(self, "_hover_compose", "replace"),
            bg_locked=bool(getattr(self, "_bg_locked", False)),
            hovered_region_id=getattr(self, "_hovered_region", None),
            badge_text=str(self._badge) if self._badge is not None else None,
            show_underline=self._show_underline,
            underline_color=self._underline_config_color,
            underline_thickness=self._underline_thickness,
            show_strike_through=self._is_strike_through(),
            is_footer=self._is_footer,
            icon_size_px=self._icon_size_px,
            content_padding=self._content_padding,
            gap_px=self._gap_px,
            content_align=self._content_align,
        )

    def iter_regions(self, ctx: DrawContext):
        if not self._controller.rects:
            self._controller.recompute_rects()
            self._sync_region_aliases()
        ordered_regions = sorted(
            enumerate(self._controller.regions),
            key=lambda item: (item[1].z_index, item[0]),
        )
        for _index, region in ordered_regions:
            rect = self._controller.rects.get(region.id)
            if rect is None:
                continue
            states = frozenset(self._controller.states(region.id))
            yield ctx.scoped_to(
                region_id=region.id,
                rect=rect,
                path=self._controller.paths.get(region.id),
                fill_path=self._controller.fill_paths.get(region.id),
                states=states,
                content=self._build_region_content(region),
                variant=get_variant(region.variant or self._variant),
                override_bg_color=region.override_bg_color,
                custom_bg_color=region.custom_bg_color,
                override_border_color=region.override_border_color,
                hover_color=(
                    region.hover_color
                    if region.hover_color is not None
                    else getattr(self, "_hover_color", None)
                ),
                hover_compose=region.hover_compose or getattr(self, "_hover_compose", "replace"),
                bg_locked=bool(region.bg_locked) or bool(getattr(self, "_bg_locked", False)),
                group=region.group,
                icon_size_px=region.icon_size_px,
                corner_radii=(
                    tuple(int(r) for r in region.corner_radii)
                    if region.corner_radii is not None
                    else None
                ),
                clip_content=not bool(getattr(region, "group", None)),
                ripple_rect=self._controller.ripple_rect(region.id),
            )

    def region_states(self, region_id: str) -> frozenset[ButtonState]:
        return frozenset(self._controller.states(region_id))

    def region_ripple(self, region_id: str) -> RippleEffect | None:
        return self._controller.ripple(region_id)

    def _dispatch_region_behavior(
        self,
        region_id: str | None,
        kind: str,
        data: Any = None,
    ) -> None:
        if region_id is None:
            return
        for behavior in self._controller.behaviors(region_id, kind):
            if behavior.action is None:
                continue
            payload = data if data is not None else behavior.data
            if behavior.callback is not None:
                behavior.callback(behavior.action, payload)
            self.actionTriggered.emit(behavior.action, payload)

    def _recompute_region_rects(self) -> None:
        self._controller.recompute_rects()
        self._region_rects = self._controller.rects
        self._region_paths = self._controller.paths

    def resizeEvent(self, event):
        self._recompute_region_rects()
        super().resizeEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._cancel_transient_effects()

    def _cancel_transient_effects(self) -> None:
        """A layout reflow can reposition this button out from under the
        cursor without Qt sending enter/leave events (those only fire on
        actual pointer movement). Left alone, hover glow and an in-flight
        ripple would keep animating at the button's new location even
        though the pointer never actually entered it there."""
        changed = False
        for ripple in list(self._region_ripple.values()):
            if ripple is not None and ripple.is_active():
                ripple.cancel()
                changed = True
        under_cursor = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if not under_cursor:
            for states in list(self._region_states.values()):
                if ButtonState.HOVERED in states or ButtonState.PRESSED in states:
                    states.discard(ButtonState.HOVERED)
                    states.discard(ButtonState.PRESSED)
                    changed = True
        if changed:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._painter.paint(self._make_context(painter))
        finally:
            painter.end()


# Backwards-compat: ButtonRow re-exported from button module.
__all__ = ["Button", "ButtonConfig", "ButtonRow"]
