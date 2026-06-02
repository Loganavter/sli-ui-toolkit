"""
Universal composable Button widget.

Replaces: IconButton, LongPressIconButton, SimpleIconButton, ToggleIconButton,
NumberedToggleIconButton, ScrollableIconButton, ToggleScrollableIconButton,
UnifiedIconButton, CustomButton, ToolButtonWithMenu.

Usage:
    btn = Button(icon="settings")
    btn = Button(icon=("eye_open", "eye_closed"), toggle=True)
    btn = Button(icon="line_weight", scrollable=(0, 10), show_underline=True)
    btn = Button(icon="magnifier", toggle=True, badge=1)
    btn = Button(icon="paste", long_press=True)
    btn = Button(icon="export", text="Export")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons._painter import ButtonPainter
from sli_ui_toolkit.ui.widgets.buttons.painting.painter import ButtonPainterV2
from sli_ui_toolkit.ui.widgets.buttons.painting.context import ButtonDrawContext
from sli_ui_toolkit.ui.widgets.buttons.states import ButtonState, StateSet
from sli_ui_toolkit.ui.widgets.style_bridge import update_widget_style
from .capabilities import ScrollCapability, LongPressCapability, MenuCapability, ButtonCapability
from .config import TextContent, RowsContent, IconContent, IconTextContent, ButtonContent

@dataclass
class ButtonRow:
    """Row of text with size, weight, color, and height ratio."""
    text: str
    size: int = 12
    weight: str = "normal"  # "normal" or "bold"
    color: QColor | None = None
    ratio: float = 0.5  # fraction of button height for this row
    h_align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignHCenter  # horizontal alignment
    strikethrough: bool = False
    italic: bool = False

@dataclass
class ButtonConfig:
    """Declarative button configuration."""

    icon: Any = None
    text: str = ""
    rows: list[ButtonRow] | None = None
    toggle: bool = False
    scrollable: tuple[int, int] | None = None
    long_press: bool = False
    long_press_ms: int = 600
    badge: int | None = None
    show_underline: bool = False
    menu: list[tuple[str, Any]] | None = None
    size: tuple[int, int] = (36, 36)
    icon_size: int = 22
    corner_radius: int | None = None
    variant: str = "default"
    density: str = "normal"

class Button(QWidget):
    """Universal composable button widget.

    All behavior is configured via constructor parameters or ButtonConfig.
    """

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
        menu: list[tuple[str, Any]] | None = None,
        size: tuple[int, int] = (36, 36),
        icon_size: int = 22,
        corner_radius: int | None = None,
        variant: str = "default",
        density: str = "normal",
        background_color: QColor | None = None,
        config: ButtonConfig | None = None,
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
            menu = config.menu
            size = config.size
            icon_size = config.icon_size
            corner_radius = config.corner_radius
            variant = config.variant
            density = config.density

        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            self._icon_unchecked = icon[0]
            self._icon_checked = icon[1]
        else:
            self._icon_unchecked = icon
            self._icon_checked = icon

        self._has_toggle = toggle
        self._has_scroll = scrollable is not None
        self._has_long_press = long_press
        self._has_menu = menu is not None
        self._has_text = bool(text)
        self._text = text
        self._rows = rows or []
        self._rows_compact = False

        self._checked = False
        self._hovered = False
        self._pressed = False
        self._is_scrolling = False

        self._variant = variant
        self._density = density
        self._icon_size_px = icon_size
        if corner_radius is None:
            corner_radius = 2 if self._has_text else 6
        self._corner_radius_px = corner_radius

        self.setProperty("variant", variant)
        self.setProperty("density", density)
        self.setProperty("iconSizePx", icon_size)
        self.setProperty("cornerRadiusPx", corner_radius)
        self._foreground_color: QColor | None = None
        self._background_color: QColor | None = None
        self._custom_bg_color: QColor | None = background_color
        self._accent_color: QColor | None = None
        self._underline_color: QColor | None = None
        self._show_underline = show_underline
        self._show_strike_through = False
        self._is_footer = False
        self._custom_color: QColor | list | None = None
        self._override_bg_color: QColor | None = None

        if self._has_scroll:
            self._scroll_min, self._scroll_max = scrollable
            self._scroll_value = max(self._scroll_min, 1)
        else:
            self._scroll_min = 0
            self._scroll_max = 0
            self._scroll_value = 0

        self._badge = badge

        self._saved_value: int | None = None

        self._flyout_open: bool = False

        w, h = size
        if self._has_text and w == 36 and h == 36:

            self.setMinimumHeight(32)
        elif w > 0 and h > 0:
            self.setFixedSize(w, h)
        elif h > 0:
            self.setFixedHeight(h)
        elif w > 0:
            self.setFixedWidth(w)
        self.setMouseTracking(True)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

        # Initialize new painter (supports both old and new rendering paths)
        self._painter_v2 = ButtonPainterV2(self.theme_manager)
        self._use_painter_v2 = True  # Use new painter v2 by default

        # Initialize capabilities instead of inline timers/state
        self._capabilities: list[ButtonCapability] = []
        self._capability_map: dict[type, ButtonCapability] = {}

        if self._has_long_press:
            lp_cap = LongPressCapability(delay_ms=long_press_ms)
            self.attach_capability(lp_cap)

        if self._has_scroll:
            scroll_cap = ScrollCapability()
            self.attach_capability(scroll_cap)

        if self._has_menu:
            menu_cap = MenuCapability(menu_items=menu)
            self.attach_capability(menu_cap)

        # Keep for backwards compatibility with external code that may set these directly
        self._value_popup: QLabel | None = None
        self._popup_controller = None
        self._menu_widget = None
        self._menu_items = menu

    def setChecked(self, checked: bool, emit: bool = True, emit_signal: bool = None):
        """Set toggle state. emit_signal is a backward-compat alias for emit."""
        if emit_signal is not None:
            emit = emit_signal
        if not self._has_toggle:
            return
        if self._checked != checked:
            self._checked = checked
            self.update()
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

    def attach_capability(self, capability: ButtonCapability) -> None:
        """Attach a capability (scroll, long_press, menu, etc.) to this button."""
        if type(capability) in self._capability_map:
            self.detach_capability(type(capability))
        capability.attach(self)
        self._capabilities.append(capability)
        self._capability_map[type(capability)] = capability

    def detach_capability(self, capability_type: type[ButtonCapability]) -> None:
        """Detach a capability by type."""
        cap = self._capability_map.get(capability_type)
        if cap:
            cap.detach(self)
            self._capabilities.remove(cap)
            del self._capability_map[capability_type]

    def get_capability(self, capability_type: type[ButtonCapability]) -> ButtonCapability | None:
        """Get an attached capability by type, or None if not attached."""
        return self._capability_map.get(capability_type)

    # Backwards compatibility properties for old timer access patterns
    @property
    def _lp_timer(self) -> QTimer | None:
        """Deprecated: access via LongPressCapability.attach()."""
        lp_cap = self.get_capability(LongPressCapability)
        return lp_cap._lp_timer if lp_cap else None

    @property
    def _lp_triggered(self) -> bool:
        """Deprecated: access via LongPressCapability.was_long_pressed()."""
        lp_cap = self.get_capability(LongPressCapability)
        return lp_cap._lp_triggered if lp_cap else False

    @_lp_triggered.setter
    def _lp_triggered(self, value: bool) -> None:
        lp_cap = self.get_capability(LongPressCapability)
        if lp_cap:
            lp_cap._lp_triggered = value

    @property
    def _scroll_end_timer(self) -> QTimer | None:
        """Deprecated: access via ScrollCapability.attach()."""
        scroll_cap = self.get_capability(ScrollCapability)
        return scroll_cap._scroll_end_timer if scroll_cap else None

    def _compute_states(self) -> StateSet:
        """Compute immutable state set from current bool attributes."""
        states = set()
        if self._hovered:
            states.add(ButtonState.HOVERED)
        if self._pressed:
            states.add(ButtonState.PRESSED)
        if self._checked:
            states.add(ButtonState.CHECKED)
        if not self.isEnabled():
            states.add(ButtonState.DISABLED)
        if self._is_scrolling:
            states.add(ButtonState.SCROLLING)
        if hasattr(self, '_focused') and self._focused:
            states.add(ButtonState.FOCUSED)
        return frozenset(states)

    def _build_content(self) -> ButtonContent:
        """Build ButtonContent from current configuration."""
        if self._rows:
            return RowsContent(rows=self._rows, compact=self._rows_compact)
        elif self._has_text and self._text:
            return TextContent(text=self._text)
        elif self._icon_unchecked or self._icon_checked:
            # For now, treat as icon-only; icon_text support comes later
            return IconContent(
                icon_unchecked=self._icon_unchecked,
                icon_checked=self._icon_checked,
                icon_size_px=self._icon_size_px,
            )
        return None

    def use_painter_v2(self, enabled: bool = True) -> None:
        """Enable/disable new ButtonPainterV2 (for migration testing).

        By default, uses legacy ButtonPainter for compatibility.
        Call this to test the new architecture.
        """
        self._use_painter_v2 = enabled
        self.update()

    def setBadge(self, num: int | None):
        self._badge = num
        self.update()

    set_display_number = setBadge

    def set_color(self, color: QColor | list | None):
        self._custom_color = color
        if isinstance(color, QColor):
            self._underline_color = color
            self.setProperty("underlineColor", color)
        self.update()

    def set_override_bg_color(self, color: QColor | None):
        self._override_bg_color = color
        self.update()

    def set_background_color(self, color: QColor | None):
        self._custom_bg_color = color
        self.update()

    def getBackgroundColor(self) -> QColor | None:
        return self._custom_bg_color

    def set_show_strike_through(self, enabled: bool):
        self._show_strike_through = enabled
        self.update()

    def set_popup_controller(self, controller):
        self._popup_controller = controller

    def setIcon(self, icon):
        if isinstance(icon, (tuple, list)) and len(icon) >= 2:
            self._icon_unchecked = icon[0]
            self._icon_checked = icon[1]
        else:
            self._icon_unchecked = icon
            self._icon_checked = icon
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
        """Set multi-line text content with individual row styling."""
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

    def set_menu_items(self, items: list[tuple[str, Any]]):
        self._menu_items = items
        self._has_menu = items is not None and len(items) > 0
        if self._has_menu and self._menu_widget is None:
            self._init_menu()
        if self._menu_widget is not None:
            self._menu_widget.set_actions(items)

    def set_current_by_data(self, data: Any):
        """Mark a menu item as current by its data value."""
        if self._menu_widget is not None:
            self._menu_widget.set_current_by_data(data)

    def show_menu(self):
        """Programmatically open the dropdown menu (if any)."""
        self._show_menu()

    set_actions = set_menu_items
    triggered = menuTriggered

    def get_saved_value(self) -> int | None:
        return self._saved_value

    def set_saved_value(self, value: int | None):
        self._saved_value = value

    def setFlyoutOpen(self, is_open: bool):
        """Suppress hover visuals while a flyout is open."""
        self._flyout_open = is_open
        if not is_open:
            from PyQt6.QtGui import QCursor
            self._hovered = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def setIconSize(self, size: QSize):
        """Compat with QAbstractButton.setIconSize."""
        self._icon_size_px = max(1, size.width())
        self.update()

    def set_footer_mode(self, is_footer: bool):
        """Footer mode: flat top, rounded bottom corners."""
        self._is_footer = is_footer
        self._corner_radius_px = 8 if is_footer else 6
        self.update()

    def set_bottom_extension(self, factor: float):
        """CustomButton compat: ignored (handled by paint if needed)."""
        pass

    def sizeHint(self):
        from PyQt6.QtCore import QSize as _QSize
        if self._has_text:
            fm = self.fontMetrics()
            text_w = fm.horizontalAdvance(self._text) if self._text else 0
            icon_w = self._icon_size_px + 6 if self._icon_unchecked else 0
            w = text_w + icon_w + 24
            h = max(32, fm.height() + 16)
            return _QSize(w, h)
        return _QSize(36, 36)

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

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            self._handle_property_change(name)
        return super().event(event)

    def enterEvent(self, event):
        if not self._flyout_open:
            self._hovered = True
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._flyout_open:
            self._hovered = False
            self._pressed = False
            if self._has_scroll:
                scroll_cap = self.get_capability(ScrollCapability)
                if scroll_cap:
                    scroll_cap._hide_scroll_popup()
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True

            # Clear scroll state
            if self._has_scroll:
                self._is_scrolling = False
                scroll_cap = self.get_capability(ScrollCapability)
                if scroll_cap:
                    scroll_cap._hide_scroll_popup()

            # Start long-press detection via capability
            lp_cap = self.get_capability(LongPressCapability)
            if lp_cap:
                lp_cap.on_press_start()

            self.pressed.emit()
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            lp_cap = self.get_capability(LongPressCapability)
            if lp_cap:
                lp_cap.on_press_end()

            self._pressed = False
            self.released.emit()
            self.update()

            # Check if this was a long-press event
            lp_triggered = lp_cap.was_long_pressed() if lp_cap else False

            if self.rect().contains(event.pos()) and not lp_triggered:
                if self._has_menu:
                    menu_cap = self.get_capability(MenuCapability)
                    if menu_cap:
                        menu_cap.show_menu()
                    else:
                        self._show_menu()  # fallback to old method
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

    def wheelEvent(self, event: QWheelEvent):
        # Dispatch to ScrollCapability if attached
        scroll_cap = self.get_capability(ScrollCapability)
        if scroll_cap and scroll_cap.handle_wheel_event(event):
            return

        return super().wheelEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)

        # Try new painter v2 if enabled (ready for gradual migration)
        if self._use_painter_v2:
            try:
                ctx = ButtonDrawContext(
                    widget=self,
                    painter=painter,
                    rect=QRectF(self.rect()),
                    states=self._compute_states(),
                    variant=self._variant,
                    corner_radius=self._corner_radius_px,
                    content=self._build_content(),
                    override_bg_color=self._override_bg_color,
                    custom_bg_color=self._custom_bg_color,
                    badge_text=str(self._badge) if self._badge is not None else None,
                    show_underline=self._show_underline,
                    underline_color=self._custom_color,
                    show_strike_through=self._is_strike_through(),
                    is_footer=self._is_footer,
                )
                self._painter_v2.paint(ctx)
                painter.end()
                return
            except Exception:
                # Fall back to old painter if v2 fails
                painter.end()
                painter = QPainter(self)

        # Use old painter (current default, CalendarDayButton-compatible)
        ButtonPainter.paint(
            widget=self,
            painter=painter,
            icon_unchecked=self._icon_unchecked,
            icon_checked=self._icon_checked,
            text=self._text,
            rows=self._rows if self._rows else None,
            rows_compact=self._rows_compact,
            is_checked=self._checked,
            is_pressed=self._pressed,
            is_hovered=self._hovered,
            is_scrolling=self._is_scrolling,
            badge_text=str(self._badge) if self._badge is not None else None,
            scroll_value=self._scroll_value if self._has_scroll else None,
            scroll_value_always_visible=self._has_scroll and not self._has_toggle,
            underline_color=self._custom_color,
            show_underline=self._show_underline,
            icon_size=self._icon_size_px,
            show_strike_through=self._is_strike_through(),
            override_bg_color=self._override_bg_color,
            custom_bg_color=self._custom_bg_color,
            is_footer=self._is_footer,
        )
        painter.end()

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
            self._corner_radius_px = max(0, int(self.property("cornerRadiusPx") or self._corner_radius_px))
        elif name in {"foregroundColor", "textColor"}:
            self._foreground_color = self.property(name) or self._foreground_color
        elif name == "backgroundColor":
            self._background_color = self.property("backgroundColor") or self._background_color
        elif name == "accentColor":
            self._accent_color = self.property("accentColor") or self._accent_color
        elif name == "underlineColor":
            self._underline_color = self.property("underlineColor") or self._underline_color
        elif name == "showUnderline":
            self._show_underline = bool(self.property("showUnderline"))
        else:
            return
        update_widget_style(self, update_geometry=needs_geometry)

    def _is_strike_through(self) -> bool:
        return self._show_strike_through and self._checked

    def _do_toggle_scroll_click(self):
        """Toggle+scroll combined: clicking toggles between value and 0."""
        if not self._checked:
            if self._scroll_value > 0:
                self._saved_value = self._scroll_value
            self._scroll_value = 0
            self._checked = True
            self.update()
            self.toggled.emit(True)
            self.valueChanged.emit(0)
        else:
            restored = self._saved_value if self._saved_value and self._saved_value > 0 else 1
            self._saved_value = None
            self._scroll_value = restored
            self._checked = False
            self.update()
            self.toggled.emit(False)
            self.valueChanged.emit(restored)

    # Compatibility layer - old methods delegate to capabilities
    def _on_long_press(self):
        """Deprecated: handled by LongPressCapability."""
        if self._pressed:
            self.longPressed.emit()

    def _on_scroll_ended(self):
        """Deprecated: handled by ScrollCapability."""
        self._is_scrolling = False
        self.update()

    def _show_scroll_popup(self, val: int):
        """Deprecated: handled by ScrollCapability."""
        scroll_cap = self.get_capability(ScrollCapability)
        if scroll_cap:
            scroll_cap._show_scroll_popup(val)

    def _hide_scroll_popup(self):
        """Deprecated: handled by ScrollCapability."""
        scroll_cap = self.get_capability(ScrollCapability)
        if scroll_cap:
            scroll_cap._hide_scroll_popup()

    def _init_menu(self):
        from sli_ui_toolkit.ui.widgets.buttons._dropdown_menu import DropdownMenu

        self._menu_widget = DropdownMenu(self)
        self._menu_widget.item_selected.connect(self._on_menu_item)
        if self._menu_items:
            self._menu_widget.set_actions(self._menu_items)

    def _show_menu(self):
        if self._menu_widget is None:
            return
        if self._menu_widget.isVisible():
            self._menu_widget.hide()
            return
        self._menu_widget.show_for_anchor(self)

    def _on_menu_item(self, action):
        data = action.data()
        self.menuTriggered.emit(data)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if not enabled:
            self._hide_scroll_popup()
        self.update()
