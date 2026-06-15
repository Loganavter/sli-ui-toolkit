"""Button input event handlers — mixin.

Содержит обработчики mouse/key/wheel/focus/enter/leave + setHoverActive /
hoverHitTest (контракт HoverCoordinator) + setEnabled.

Опирается на инстансные атрибуты Button: _states, _flyout_open, _hovered,
_pressed, _is_scrolling, _has_*, _ripple, _defer_click, и на capabilities
(LongPress/Scroll/Menu) через get_capability.
"""

from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QMouseEvent, QWheelEvent

from .capabilities import LongPressCapability, MenuCapability, ScrollCapability
from .state import ButtonState


class _ButtonEvents:
    """Mixin: input event handlers + click signal flow."""

    # -------- hover (with HoverCoordinator contract) --------

    def enterEvent(self, event):
        if not self._flyout_open:
            self.setHoverActive(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._flyout_open:
            self.setHoverActive(False)
            self._set_region_state(self._pressed_region, ButtonState.PRESSED, False)
            self._pressed_region = None
            if self._has_scroll:
                scroll_cap = self.get_capability(ScrollCapability)
                if scroll_cap:
                    scroll_cap._hide_scroll_popup()
        super().leaveEvent(event)

    def hoverHitTest(self, pos) -> bool:
        return self._region_at(pos) is not None

    def setHoverActive(self, active: bool) -> None:
        if self._flyout_open:
            return
        active = bool(active)
        if not active:
            for states in self._region_states.values():
                states.discard(ButtonState.HOVERED)
                states.discard(ButtonState.PRESSED)
            self._hovered_region = None
            self._pressed_region = None
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        self._update_hover_region(event.position())
        super().mouseMoveEvent(event)

    # -------- mouse --------

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            region_id = self._region_at(event.position())
            self._pressed_region = region_id
            if region_id is not None:
                self._set_region_state(region_id, ButtonState.PRESSED, True)
            if self.isEnabled() and region_id is not None:
                color_from, color_to = self._resolve_ripple_colors()
                ripple = self.region_ripple(region_id) or self._ripple
                ripple.trigger(
                    event.position(),
                    color_from=color_from,
                    color_to=color_to,
                )
            if self._has_scroll:
                self._is_scrolling = False
                scroll_cap = self.get_capability(ScrollCapability)
                if scroll_cap:
                    scroll_cap._hide_scroll_popup()
            lp_cap = self.get_capability(LongPressCapability, region_id=region_id)
            if lp_cap:
                lp_cap.on_press_start()
            if region_id is not None:
                self.regionPressed.emit(region_id)
                if region_id == "_main":
                    self.pressed.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            region_id = self._pressed_region
            lp_cap = self.get_capability(LongPressCapability, region_id=region_id)
            if lp_cap:
                lp_cap.on_press_end()
            if region_id is not None:
                self._set_region_state(region_id, ButtonState.PRESSED, False)
                self.regionReleased.emit(region_id)
                if region_id == "_main":
                    self.released.emit()

            lp_triggered = lp_cap.was_long_pressed() if lp_cap else False
            release_region = self._region_at(event.position())
            if release_region is not None and release_region == region_id and not lp_triggered:
                region = self._region_by_id(region_id)
                has_menu = bool(region.menu) if region is not None else self._has_menu
                has_toggle = bool(region.toggle) if region is not None else self._has_toggle
                if has_menu:
                    menu_cap = self.get_capability(MenuCapability, region_id=region_id)
                    if menu_cap:
                        menu_cap.show_menu()
                elif region_id == "_main" and self._has_toggle and self._has_scroll:
                    self._do_toggle_scroll_click()
                elif has_toggle:
                    checked = ButtonState.CHECKED not in self._region_states[region_id]
                    self._set_region_state(region_id, ButtonState.CHECKED, checked)
                    self.regionToggled.emit(region_id, checked)
                    if region_id == "_main":
                        self.toggled.emit(checked)
                if self._defer_click and region_id == "_main":
                    QTimer.singleShot(0, self._emit_click_signals)
                else:
                    self.regionClicked.emit(region_id)
                    if region_id == "_main":
                        self._emit_click_signals()
                        if sip.isdeleted(self):
                            return
            self._pressed_region = None

        elif event.button() == Qt.MouseButton.RightButton:
            if self._region_at(event.position()) is not None:
                self.rightClicked.emit()
                if sip.isdeleted(self):
                    return

        elif event.button() == Qt.MouseButton.MiddleButton:
            if self._region_at(event.position()) is not None:
                self.middleClicked.emit()
                if sip.isdeleted(self):
                    return

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        region_id = self._region_at(event.position())
        scroll_cap = self.get_capability(ScrollCapability, region_id=region_id)
        if scroll_cap is None:
            scroll_cap = self.get_capability(ScrollCapability)
        if scroll_cap and not self.shouldHandleWheelEvent(event):
            return
        if scroll_cap and scroll_cap.handle_wheel_event(event):
            return
        return super().wheelEvent(event)

    # -------- keyboard --------

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

    # -------- click flow --------

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
        if self._defer_click:
            QTimer.singleShot(0, self._emit_click_signals)
        else:
            self._emit_click_signals()

    def _emit_click_signals(self) -> None:
        if sip.isdeleted(self):
            return
        self.clicked.emit()
        if sip.isdeleted(self):
            return
        self.shortClicked.emit()

    # -------- enabled state --------

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if enabled:
            region_enabled = {region.id: region.enabled for region in self._regions}
            for region_id, states in self._region_states.items():
                if region_enabled.get(region_id, True):
                    states.discard(ButtonState.DISABLED)
                else:
                    states.add(ButtonState.DISABLED)
        else:
            for states in self._region_states.values():
                states.add(ButtonState.DISABLED)
            scroll_cap = self.get_capability(ScrollCapability)
            if scroll_cap:
                scroll_cap._hide_scroll_popup()
        self.update()

    # -------- region helpers --------

    def _region_by_id(self, region_id: str | None):
        if region_id is None:
            return None
        for region in self._regions:
            if region.id == region_id:
                return region
        return None

    def _region_at(self, pos) -> str | None:
        raw_point = pos.toPoint() if hasattr(pos, "toPoint") else pos
        point = QPointF(raw_point)
        if not QRectF(self.rect()).contains(point):
            return None
        if not self._region_rects:
            self._recompute_region_rects()
        for region in reversed(self._regions):
            rect = self._region_rects.get(region.id)
            if rect is None or not rect.contains(point):
                continue
            if ButtonState.DISABLED in self._region_states.get(region.id, set()):
                return None
            return region.id
        return None

    def _set_region_state(
        self,
        region_id: str | None,
        state: ButtonState,
        active: bool,
    ) -> None:
        if region_id is None:
            return
        states = self._region_states.setdefault(region_id, set())
        if active:
            states.add(state)
        else:
            states.discard(state)
        self.update()

    def _update_hover_region(self, pos) -> None:
        region_id = self._region_at(pos)
        if region_id == self._hovered_region:
            return
        if self._hovered_region is not None:
            self._set_region_state(self._hovered_region, ButtonState.HOVERED, False)
        self._hovered_region = region_id
        if region_id is not None:
            self._set_region_state(region_id, ButtonState.HOVERED, True)
