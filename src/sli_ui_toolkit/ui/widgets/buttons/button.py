"""Universal composable Button widget.

Replaces a host of legacy specialised buttons (Icon/Toggle/Scrollable/LongPress/...).
Behaviour is configured via constructor kwargs or ButtonConfig. Rendering is delegated
to a single Painter pipeline (see painter.py). Interactive behaviours (scroll, long
press, menu) live as composable Capabilities (see capabilities/).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import warnings

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin, register_hover_widget
from sli_ui_toolkit.ui.widgets.style_bridge import update_widget_style

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
from .painter import Painter
from .layers._base import Layer
from .state import ButtonState, StateSet
from .variants import get_variant


_MAX_UNDERLINE_THICKNESS = 3.0


def _normalize_underline_thickness(thickness: float | None) -> float | None:
    if thickness is None:
        return None
    normalized = max(0.0, float(thickness))
    if normalized > _MAX_UNDERLINE_THICKNESS:
        warnings.warn(
            (
                "Button underline thickness is capped at "
                f"{_MAX_UNDERLINE_THICKNESS:.1f}px; got {normalized:.1f}px."
            ),
            RuntimeWarning,
            stacklevel=3,
        )
        return _MAX_UNDERLINE_THICKNESS
    return normalized


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


def _state_property(state: ButtonState):
    """Property-обёртка: bool геттер/сеттер, мутирующий StateSet и вызывающий update()."""

    def getter(self) -> bool:
        return state in self._states

    def setter(self, value: bool) -> None:
        if bool(value):
            self._states.add(state)
        else:
            self._states.discard(state)
        self.update()

    return property(getter, setter)


class Button(WheelScrollPolicyMixin, QWidget):
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

    # Аккуратные имена-алиасы, на которые опираются подклассы (CalendarDayButton) и capabilities.
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

        if variant == "primary":
            warnings.warn(
                "Button variant 'primary' is deprecated; use 'surface' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            variant = "surface"

        self.init_wheel_scroll_policy(wheel_requires_focus=wheel_requires_focus)
        self._states: set[ButtonState] = set()

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

        self._capabilities: list[ButtonCapability] = []
        self._capability_map: dict[type, ButtonCapability] = {}

        if long_press:
            self.attach_capability(LongPressCapability(delay_ms=long_press_ms))
        if self._has_scroll:
            self.attach_capability(ScrollCapability())
        if self._has_menu:
            self.attach_capability(MenuCapability(menu_items=menu))

        self._value_popup: QLabel | None = None
        self._popup_controller = None
        self._menu_items = menu

    # -------- public API: capabilities --------

    def attach_capability(self, capability: ButtonCapability) -> None:
        if type(capability) in self._capability_map:
            self.detach_capability(type(capability))
        capability.attach(self)
        self._capabilities.append(capability)
        self._capability_map[type(capability)] = capability

    def detach_capability(self, capability_type: type[ButtonCapability]) -> None:
        cap = self._capability_map.get(capability_type)
        if cap:
            cap.detach(self)
            self._capabilities.remove(cap)
            del self._capability_map[capability_type]

    def get_capability(self, capability_type: type[ButtonCapability]) -> ButtonCapability | None:
        return self._capability_map.get(capability_type)

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

    # -------- public API: content/decoration --------

    def setBadge(self, num: int | None):
        self._badge = num
        self.update()

    set_display_number = setBadge

    def setBadgeStyle(
        self,
        *,
        filled: bool | None = None,
        bordered: bool | None = None,
        background_color: QColor | None = None,
        border_color: QColor | None = None,
        text_color: QColor | None = None,
    ):
        if filled is not None:
            self.setProperty("badgeFilled", bool(filled))
        if bordered is not None:
            self.setProperty("badgeBordered", bool(bordered))
        if background_color is not None:
            self.setProperty("badgeBackgroundColor", background_color)
        if border_color is not None:
            self.setProperty("badgeBorderColor", border_color)
        if text_color is not None:
            self.setProperty("badgeTextColor", text_color)
        self.update()

    set_badge_style = setBadgeStyle

    def setUnderlineColor(self, color: QColor | list | None):
        self._underline_config_color = color
        if isinstance(color, QColor):
            self.setProperty("underlineColor", color)
        elif isinstance(color, list):
            self.setProperty("underlineColor", color)
        elif color is None:
            self.setProperty("underlineColor", None)
        self.update()

    set_underline_color = setUnderlineColor

    def setUnderlineThickness(self, thickness: float | None):
        self._underline_thickness = _normalize_underline_thickness(thickness)
        self.setProperty("underlineThicknessPx", self._underline_thickness)
        self.update()

    set_underline_thickness = setUnderlineThickness

    def set_override_bg_color(self, color: QColor | None):
        self._override_bg_color = color
        self.update()

    def set_background_color(self, color: QColor | None):
        self._custom_bg_color = color
        self.update()

    def getBackgroundColor(self) -> QColor | None:
        return self._custom_bg_color

    def setBorderColor(self, color: QColor | None) -> None:
        self._border_color_override = color
        self.update()

    set_border_color = setBorderColor

    def borderColor(self) -> QColor | None:
        return self._border_color_override

    def set_show_strike_through(self, enabled: bool):
        self._show_strike_through = enabled
        self.update()

    def set_popup_controller(self, controller):
        self._popup_controller = controller
        scroll_cap = self.get_capability(ScrollCapability)
        if scroll_cap is not None:
            scroll_cap._popup_controller = controller

    def configure_value_popup(self, *, formatter=None, padding=None) -> None:
        """Customize the scroll-wheel value popup.

        ``formatter(value) -> ValuePopupContent`` overrides text/pixmap/size/
        font/extra style per value. ``padding=(h, v)`` tweaks default autosize
        margins. No-op if the button has no scroll capability.
        """
        cap = self.get_capability(ScrollCapability)
        if cap is not None:
            cap.configure_popup(formatter=formatter, padding=padding)

    def setIcon(self, icon):
        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            self._icon_unchecked, self._icon_checked = icon[0], icon[1]
        else:
            self._icon_unchecked = self._icon_checked = icon
        self.update()

    def setText(self, text: str):
        self._text = text
        had_text = self._has_text
        self._has_text = bool(text)
        if self._has_text and not had_text:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setMinimumHeight(max(32, self.minimumHeight()))
            self.setMaximumHeight(16777215)
            self._corner_radius_px = 2
            self.setProperty("cornerRadiusPx", 2)
        elif not self._has_text and had_text:
            self.setFixedSize(36, 36)
            self._corner_radius_px = 6
            self.setProperty("cornerRadiusPx", 6)
        self.updateGeometry()
        self.update()

    def setRows(self, rows: list[ButtonRow] | None, compact: bool = False):
        self._rows = rows or []
        self._rows_compact = compact
        had_text = self._has_text
        self._has_text = bool(rows)
        if self._has_text and not had_text:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setMinimumHeight(max(32, self.minimumHeight()))
            self.setMaximumHeight(16777215)
            self._corner_radius_px = 2
            self.setProperty("cornerRadiusPx", 2)
        elif not self._has_text and had_text:
            self.setFixedSize(36, 36)
            self._corner_radius_px = 6
            self.setProperty("cornerRadiusPx", 6)
        self.updateGeometry()
        self.update()

    # -------- public API: menu --------

    def set_menu_items(self, items: list[tuple[str, Any]]):
        self._menu_items = items
        had_menu = self._has_menu
        self._has_menu = bool(items)
        cap = self.get_capability(MenuCapability)
        if self._has_menu and cap is None:
            self.attach_capability(MenuCapability(menu_items=items))
        elif cap is not None:
            cap.set_menu_items(items)
        if not self._has_menu and had_menu and cap is not None:
            self.detach_capability(MenuCapability)

    set_actions = set_menu_items
    triggered = menuTriggered

    def set_current_by_data(self, data: Any):
        cap = self.get_capability(MenuCapability)
        if cap is not None and getattr(cap, "_menu_widget", None) is not None:
            cap._menu_widget.set_current_by_data(data)

    def show_menu(self):
        cap = self.get_capability(MenuCapability)
        if cap is not None:
            cap.show_menu()

    # -------- public API: misc / style --------

    def setFlyoutOpen(self, is_open: bool):
        self._flyout_open = is_open
        if not is_open:
            from PyQt6.QtGui import QCursor
            self._hovered = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def setIconSize(self, size: QSize):
        self._icon_size_px = max(1, size.width())
        self.update()

    def set_footer_mode(self, is_footer: bool):
        self._is_footer = is_footer
        self.update()

    def set_bottom_extension(self, factor: float):
        """Compat: no-op (handled inside paint if needed)."""
        pass

    def sizeHint(self):
        if self._has_text:
            fm = self.fontMetrics()
            text_w = fm.horizontalAdvance(self._text) if self._text else 0
            icon_w = self._icon_size_px + 6 if self._icon_unchecked else 0
            w = text_w + icon_w + 24
            h = max(32, fm.height() + 16)
            return QSize(w, h)
        return QSize(36, 36)

    def minimumSizeHint(self):
        return self.sizeHint()

    def getVariant(self) -> str:
        return self._variant

    def setVariant(self, variant: str):
        self._variant = str(variant or "default")
        self.setProperty("variant", self._variant)
        update_widget_style(self)

    def getDensity(self) -> str:
        return self._density

    def setDensity(self, density: str):
        self._density = str(density or "normal")
        self.setProperty("density", self._density)
        update_widget_style(self, update_geometry=True)

    def getIconSizePx(self) -> int:
        return int(self._icon_size_px)

    def setIconSizePx(self, size_px: int):
        size_px = max(1, int(size_px))
        if self._icon_size_px != size_px:
            self._icon_size_px = size_px
            self.setProperty("iconSizePx", size_px)
            update_widget_style(self, update_geometry=True)

    def getCornerRadiusPx(self) -> int:
        return int(self._corner_radius_px)

    def setCornerRadiusPx(self, radius_px: int):
        radius_px = max(0, int(radius_px))
        if self._corner_radius_px != radius_px:
            self._corner_radius_px = radius_px
            self.setProperty("cornerRadiusPx", self._corner_radius_px)
            update_widget_style(self)

    def getForegroundColor(self):
        return self._foreground_color

    def setForegroundColor(self, color):
        self._foreground_color = color
        self.setProperty("foregroundColor", color)
        update_widget_style(self)

    def getAccentColor(self):
        return self._accent_color

    def setAccentColor(self, color):
        self._accent_color = color
        self.setProperty("accentColor", color)
        update_widget_style(self)

    def setShowUnderline(self, show: bool):
        if self._show_underline != show:
            self._show_underline = show
            self.setProperty("showUnderline", show)
            self.update()

    # -------- events --------

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            self._handle_property_change(name)
        return super().event(event)

    def enterEvent(self, event):
        if not self._flyout_open:
            self.setHoverActive(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._flyout_open:
            self.setHoverActive(False)
            self._pressed = False
            if self._has_scroll:
                scroll_cap = self.get_capability(ScrollCapability)
                if scroll_cap:
                    scroll_cap._hide_scroll_popup()
        super().leaveEvent(event)

    def hoverHitTest(self, pos) -> bool:
        return self.rect().contains(pos.toPoint() if hasattr(pos, "toPoint") else pos)

    def setHoverActive(self, active: bool) -> None:
        if self._flyout_open:
            return
        active = bool(active)
        if self._hovered != active:
            self._hovered = active
        if not active and self._pressed:
            self._pressed = False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            if self._has_scroll:
                self._is_scrolling = False
                scroll_cap = self.get_capability(ScrollCapability)
                if scroll_cap:
                    scroll_cap._hide_scroll_popup()
            lp_cap = self.get_capability(LongPressCapability)
            if lp_cap:
                lp_cap.on_press_start()
            self.pressed.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            lp_cap = self.get_capability(LongPressCapability)
            if lp_cap:
                lp_cap.on_press_end()
            self._pressed = False
            self.released.emit()

            lp_triggered = lp_cap.was_long_pressed() if lp_cap else False
            if self.rect().contains(event.pos()) and not lp_triggered:
                if self._has_menu:
                    menu_cap = self.get_capability(MenuCapability)
                    if menu_cap:
                        menu_cap.show_menu()
                elif self._has_toggle and self._has_scroll:
                    self._do_toggle_scroll_click()
                elif self._has_toggle:
                    self.setChecked(not self._checked)
                self.clicked.emit()
                if sip.isdeleted(self):
                    return
                self.shortClicked.emit()
                if sip.isdeleted(self):
                    return

        elif event.button() == Qt.MouseButton.RightButton:
            if self.rect().contains(event.pos()):
                self.rightClicked.emit()
                if sip.isdeleted(self):
                    return

        elif event.button() == Qt.MouseButton.MiddleButton:
            if self.rect().contains(event.pos()):
                self.middleClicked.emit()
                if sip.isdeleted(self):
                    return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.isAutoRepeat():
                self._activate_via_keyboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def _activate_via_keyboard(self):
        self.pressed.emit()
        if sip.isdeleted(self):
            return
        self.released.emit()
        if sip.isdeleted(self):
            return
        if self._has_menu:
            menu_cap = self.get_capability(MenuCapability)
            if menu_cap:
                menu_cap.show_menu()
        elif self._has_toggle and self._has_scroll:
            self._do_toggle_scroll_click()
        elif self._has_toggle:
            self.setChecked(not self._checked)
        self.clicked.emit()
        if sip.isdeleted(self):
            return
        self.shortClicked.emit()

    def wheelEvent(self, event: QWheelEvent):
        scroll_cap = self.get_capability(ScrollCapability)
        if scroll_cap and not self.shouldHandleWheelEvent(event):
            return
        if scroll_cap and scroll_cap.handle_wheel_event(event):
            return
        return super().wheelEvent(event)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if enabled:
            self._states.discard(ButtonState.DISABLED)
        else:
            self._states.add(ButtonState.DISABLED)
            scroll_cap = self.get_capability(ScrollCapability)
            if scroll_cap:
                scroll_cap._hide_scroll_popup()
        self.update()

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

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._painter.paint(self._make_context(painter))
        finally:
            painter.end()

    # -------- private --------

    def _handle_property_change(self, name: str):
        needs_geometry = False
        if name == "variant":
            self._variant = str(self.property("variant") or self._variant)
        elif name == "density":
            self._density = str(self.property("density") or self._density)
            needs_geometry = True
        elif name == "iconSizePx":
            self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
            needs_geometry = True
        elif name == "cornerRadiusPx":
            raw_radius = self.property("cornerRadiusPx")
            if raw_radius is not None:
                self._corner_radius_px = max(0, int(raw_radius))
        elif name in {"foregroundColor", "textColor"}:
            self._foreground_color = self.property(name) or self._foreground_color
        elif name == "backgroundColor":
            self._background_color = self.property("backgroundColor") or self._background_color
        elif name == "accentColor":
            self._accent_color = self.property("accentColor") or self._accent_color
        elif name == "underlineColor":
            self._underline_config_color = self.property("underlineColor")
        elif name == "showUnderline":
            self._show_underline = bool(self.property("showUnderline"))
        elif name == "underlineThicknessPx":
            value = self.property("underlineThicknessPx")
            self._underline_thickness = _normalize_underline_thickness(value)
        else:
            return
        update_widget_style(self, update_geometry=needs_geometry)

    def _is_strike_through(self) -> bool:
        return self._show_strike_through and self._checked

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
