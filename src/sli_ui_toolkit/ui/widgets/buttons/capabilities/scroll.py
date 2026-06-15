"""ScrollCapability — wheel-based value manipulation with in-window feedback."""

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QPoint, QSize, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPixmap
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget
from PyQt6.QtCore import Qt

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from .base import ButtonCapability


@dataclass
class ValuePopupContent:
    """Describes how the in-window value popup should look for a given value.

    All fields are optional. When ``size`` is None, the popup auto-sizes from
    ``font`` metrics and ``text``/``pixmap``. When ``font`` is None, a default
    bold font derived from the button is used. ``style`` is extra QSS appended
    to the default popup stylesheet (use to override colors, radius, etc.).
    """
    text: str = ""
    pixmap: QPixmap | None = None
    size: QSize | None = None
    font: QFont | None = None
    style: str | None = None


class ScrollCapability(ButtonCapability):
    """Enables scroll wheel value adjustment with in-window value feedback.

    Handles:
    - wheelEvent dispatch
    - scroll value increment/decrement with toggle mode (0 = "off")
    - scroll end timeout (hides value overlay, clears scrolling state)
    - value overlay display
    """

    def __init__(self, min_value: int = 0, max_value: int = 10):
        super().__init__()
        self.min_value = min_value
        self.max_value = max_value
        self._button = None
        self._scroll_end_timer: QTimer | None = None
        self._value_popup: QLabel | None = None
        self._popup_controller = None
        self._popup_formatter: Callable[[int], ValuePopupContent] | None = None
        self._popup_padding: tuple[int, int] = (8, 3)

    def attach(self, button: QWidget, region_id: str | None = None) -> None:
        super().attach(button, region_id=region_id)
        self._button = button
        self._scroll_end_timer = QTimer(button)
        self._scroll_end_timer.setSingleShot(True)
        self._scroll_end_timer.setInterval(800)
        self._scroll_end_timer.timeout.connect(self._on_scroll_ended)

        # Try to get popup controller if available
        if hasattr(button, '_popup_controller'):
            self._popup_controller = button._popup_controller

    def detach(self, button: QWidget) -> None:
        if self._scroll_end_timer:
            self._scroll_end_timer.stop()
            self._scroll_end_timer.deleteLater()
        if self._value_popup:
            self._value_popup.hide()
            self._value_popup.deleteLater()
        self._button = None

    def is_enabled(self) -> bool:
        return self._button is not None and self._button.isEnabled()

    def handle_wheel_event(self, event) -> bool:
        """Handle wheel event. Return True if consumed, False to pass through."""
        if not self.is_enabled():
            return False
        if self._region_id not in (None, "_main"):
            return self._handle_region_wheel_event(event)
        if not hasattr(self._button, '_has_scroll') or not self._button._has_scroll:
            return False

        delta = event.angleDelta().y()
        if delta == 0:
            return False

        self._button._is_scrolling = True
        if self._scroll_end_timer:
            self._scroll_end_timer.start()

        # Toggle+scroll mode: toggle between value and 0
        if hasattr(self._button, '_has_toggle') and self._button._has_toggle:
            if self._button._checked:
                # Scrolling DOWN while at 0/checked must stay at 0
                # (only scrolling UP unchecks back to a positive value).
                if delta < 0:
                    self._show_scroll_popup(0)
                    event.accept()
                    return True
                restored = self._button._saved_value if self._button._saved_value and self._button._saved_value > 0 else 1
                self._button._saved_value = None
                new_val = max(
                    self._button._scroll_min if self._button._scroll_min > 0 else 1,
                    min(self._button._scroll_max, restored),
                )
                self._button._scroll_value = new_val
                self._button._checked = False
                self._button.valueChanged.emit(new_val)
                self._button.update()
                self._show_scroll_popup(new_val)
                event.accept()
                return True

        step = 1 if delta > 0 else -1
        old_value = self._button._scroll_value
        new_val = max(self._button._scroll_min, min(self._button._scroll_max, self._button._scroll_value + step))

        # Check toggle boundary (0 = "off" state)
        if hasattr(self._button, '_has_toggle') and self._button._has_toggle:
            if old_value > 0 and new_val == 0:
                self._button._saved_value = old_value
                self._button._scroll_value = 0
                self._button._checked = True
                self._button.valueChanged.emit(0)
                self._button.update()
                self._show_scroll_popup(0)
                event.accept()
                return True

        if new_val != self._button._scroll_value:
            self._button._scroll_value = new_val
            self._button.valueChanged.emit(new_val)
            self._button.update()
        self._show_scroll_popup(new_val)
        event.accept()
        return True

    def _handle_region_wheel_event(self, event) -> bool:
        region_id = self._region_id
        ranges = getattr(self._button, "_region_scroll_ranges", {})
        values = getattr(self._button, "_region_scroll_values", {})
        if region_id not in ranges:
            return False

        delta = event.angleDelta().y()
        if delta == 0:
            return False

        from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

        states = getattr(self._button, "_region_states", {}).setdefault(region_id, set())
        states.add(ButtonState.SCROLLING)
        if self._scroll_end_timer:
            self._scroll_end_timer.start()

        min_v, max_v = ranges[region_id]
        old_value = values.get(region_id, min_v)
        step = 1 if delta > 0 else -1
        new_value = max(min_v, min(max_v, old_value + step))
        if new_value != old_value:
            values[region_id] = new_value
            if hasattr(self._button, "regionValueChanged"):
                self._button.regionValueChanged.emit(region_id, new_value)
            self._button.update()
        self._show_scroll_popup(new_value)
        event.accept()
        return True

    def _on_scroll_ended(self):
        if self._button is None:
            return
        if self._region_id not in (None, "_main"):
            from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

            states = getattr(self._button, "_region_states", {}).get(self._region_id)
            if states is not None:
                states.discard(ButtonState.SCROLLING)
        else:
            self._button._is_scrolling = False
        self._hide_scroll_popup()
        self._button.update()

    def configure_popup(
        self,
        *,
        formatter: Callable[[int], ValuePopupContent] | None = None,
        padding: tuple[int, int] | None = None,
    ) -> None:
        """Customize the value popup.

        ``formatter`` receives the current value and returns a ValuePopupContent
        describing text/pixmap/size/font/extra style. Returning ``size=None``
        triggers auto-sizing from font metrics plus ``padding``.
        """
        if formatter is not None:
            self._popup_formatter = formatter
        if padding is not None:
            self._popup_padding = (int(padding[0]), int(padding[1]))

    def _default_popup_font(self) -> QFont:
        font = QFont(self._button.font()) if self._button is not None else QFont()
        font.setBold(True)
        if font.pointSize() > 0:
            font.setPointSize(max(font.pointSize() + 1, 12))
        elif font.pixelSize() > 0:
            font.setPixelSize(max(font.pixelSize() + 1, 15))
        else:
            font.setPointSize(12)
        return font

    def _default_popup_content(self, val: int) -> ValuePopupContent:
        if val == 0:
            pixmap = resolve_icon(get_named_icon("divider_hidden")).pixmap(18, 18)
            if pixmap.isNull():
                return ValuePopupContent(text="off")
            return ValuePopupContent(pixmap=pixmap)
        return ValuePopupContent(text=str(val))

    def _resolve_popup_content(self, val: int) -> ValuePopupContent:
        formatter = self._popup_formatter or self._default_popup_content
        content = formatter(val)
        if not isinstance(content, ValuePopupContent):
            raise TypeError(
                "scroll popup formatter must return ValuePopupContent, "
                f"got {type(content).__name__}"
            )
        return content

    def _autosize(self, content: ValuePopupContent, font: QFont) -> QSize:
        pad_w, pad_h = self._popup_padding
        if content.pixmap is not None and not content.pixmap.isNull():
            pm = content.pixmap
            return QSize(pm.width() + pad_w * 2, pm.height() + pad_h * 2)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(content.text or " ")
        h = fm.height()
        return QSize(w + pad_w * 2, h + pad_h * 2)

    def _show_scroll_popup(self, val: int):
        if self._button is None or not self._button.isVisible():
            return

        content = self._resolve_popup_content(val)
        font = content.font or self._default_popup_font()
        size = content.size or self._autosize(content, font)
        if isinstance(size, tuple):
            size = QSize(int(size[0]), int(size[1]))

        popup_id = f"button:{id(self._button)}"
        if self._popup_controller is not None:
            self._popup_controller.show_popup(
                popup_id, self._button,
                text=content.text, pixmap=content.pixmap,
                size=size, position="top",
                offset=6,
                timeout_ms=self._scroll_end_timer.interval() if self._scroll_end_timer else 800,
            )
            return

        if self._value_popup is None:
            self._value_popup = QLabel(parent=self._button.window())
            self._value_popup.setObjectName("ValuePopupLabel")
            self._value_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._value_popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            shadow = QGraphicsDropShadowEffect(self._value_popup)
            shadow.setBlurRadius(10)
            shadow.setOffset(0, 2)
            self._value_popup.setGraphicsEffect(shadow)

        self._value_popup.setFont(font)

        tm = getattr(self._button, "theme_manager", None)
        if tm is not None:
            bg = tm.get_color("flyout.background")
            border = tm.get_color("flyout.border")
            text = tm.get_color("dialog.text")
            shadow = self._value_popup.graphicsEffect()
            if isinstance(shadow, QGraphicsDropShadowEffect):
                shadow.setColor(tm.get_color("shadow.color"))
            style = (
                "QLabel#ValuePopupLabel {"
                f"background-color: {bg.name(QColor.NameFormat.HexArgb)};"
                f"border: 1px solid {border.name(QColor.NameFormat.HexArgb)};"
                "border-radius: 6px;"
                f"color: {text.name(QColor.NameFormat.HexArgb)};"
                "}"
            )
            if content.style:
                style += content.style
            self._value_popup.setStyleSheet(style)

        if content.pixmap is not None and not content.pixmap.isNull():
            self._value_popup.setPixmap(content.pixmap)
            self._value_popup.setText("")
        else:
            self._value_popup.setPixmap(QPixmap())
            self._value_popup.setText(content.text)
        self._value_popup.setFixedSize(size)

        window = self._button.window()
        pos = self._button.mapToGlobal(QPoint(0, 0))
        local_pos = window.mapFromGlobal(pos) if window is not None else pos
        popup_x = local_pos.x() + (self._button.width() - self._value_popup.width()) // 2
        popup_y = local_pos.y() - self._value_popup.height() - 6
        self._value_popup.move(popup_x, popup_y)

        if not self._value_popup.isVisible():
            self._value_popup.show()
        self._value_popup.raise_()

    def _hide_scroll_popup(self):
        popup_id = f"button:{id(self._button)}"
        if self._popup_controller is not None:
            self._popup_controller.hide_popup(popup_id)
        if self._value_popup:
            self._value_popup.hide()
