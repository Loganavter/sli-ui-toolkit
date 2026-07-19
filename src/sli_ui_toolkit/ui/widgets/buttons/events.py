"""Button input event handlers — mixin.

Содержит обработчики mouse/key/wheel/focus/enter/leave + setHoverActive /
hoverHitTest (контракт HoverCoordinator) + setEnabled.

Опирается на инстансные атрибуты Button: _states, _flyout_open, _hovered,
_pressed, _has_*, _ripple, _defer_click_ms, и на capabilities (LongPress/Menu/...)
через get_capability. Wheel-события диспатчатся duck-typed любой capability,
у которой есть handle_wheel_event — так app-level capabilities (см.
attach_capability) получают wheel-события без хардкода конкретного типа.
"""

from __future__ import annotations

import shiboken6 as sip
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QMouseEvent, QWheelEvent

from .capabilities import LongPressCapability
from .state import ButtonState


class _ButtonEvents:
    """Mixin: input event handlers + click signal flow."""

    # -------- hover (with HoverCoordinator contract) --------

    def enterEvent(self, event):
        if not self._flyout_open:
            # enterEvent alone used to only flip a boolean; without seeding
            # the region from the cursor, the first paint could miss HOVERED
            # until the next mouseMove.
            pos = event.position() if hasattr(event, "position") else None
            if pos is not None:
                self._update_hover_region(pos)
            else:
                self.setHoverActive(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._flyout_open:
            self.setHoverActive(False)
            self._set_region_state(self._pressed_region, ButtonState.PRESSED, False)
            self._pressed_region = None
        super().leaveEvent(event)

    def hoverHitTest(self, pos) -> bool:
        # Region gaps (split.gap between different click targets) are still
        # "over this button". Returning False here makes HoverCoordinator call
        # setHoverActive(False) for one mouse pixel and flicker the shared wash.
        if self._region_at(pos) is not None:
            return True
        return QRectF(self.rect()).contains(QPointF(pos))

    def setHoverActive(self, active: bool) -> None:
        if self._flyout_open:
            return
        active = bool(active)
        if not active:
            # HoverCoordinator calls this with False for every registered
            # button in the app on every single mouse-move, not just the one
            # under the cursor. Without this guard, an already-inactive
            # button still ran the full region-state clear and queued a
            # repaint (self.update()) on every mouse pixel moved anywhere in
            # the window — the actual cost was in the needless paintEvent
            # storm, not the coordinator loop itself.
            if self._hovered_region is None and self._pressed_region is None:
                return
            for region in self._regions:
                self._controller.set_state(region.id, ButtonState.HOVERED, False)
                self._controller.set_state(region.id, ButtonState.PRESSED, False)
            self._hovered_region = None
            self._pressed_region = None
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        self._update_hover_region(event.position())
        super().mouseMoveEvent(event)

    # -------- mouse --------

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            region_id = self._region_at(event.position())
            if self.isEnabled() and region_id is not None:
                color_from, color_to = self._resolve_ripple_colors()
                ripple = self.region_ripple(region_id) or self._ripple
                ripple.trigger(
                    event.position(),
                    color_from=color_from,
                    color_to=color_to,
                )
        if event.button() == Qt.MouseButton.LeftButton:
            region_id = self._region_at(event.position())
            self._pressed_region = region_id
            if region_id is not None:
                self._set_region_state(region_id, ButtonState.PRESSED, True)
            lp_cap = self.get_capability(LongPressCapability, region_id=region_id)
            if lp_cap:
                lp_cap.on_press_start()
            if region_id is not None:
                self.regionPressed.emit(region_id)
                if region_id == "_main":
                    self.pressed.emit()
                # Accept so nested Buttons (e.g. rating +/- on RatingListItem)
                # do not propagate to the parent row and trigger itemSelected.
                event.accept()
                return
        elif event.button() == Qt.MouseButton.RightButton:
            if self._region_at(event.position()) is not None:
                event.accept()
                return
        elif event.button() == Qt.MouseButton.MiddleButton:
            if self._region_at(event.position()) is not None:
                event.accept()
                return
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
            same_target = release_region is not None and (
                release_region == region_id
                or release_region in self._linked_region_ids(region_id or "")
            )
            handled = region_id is not None
            if same_target and not lp_triggered:
                region = self._region_by_id(region_id)
                has_toggle = bool(region.toggle) if region is not None else self._has_toggle
                if has_toggle:
                    checked = ButtonState.CHECKED not in self._controller.states(region_id)
                    self._set_region_state(region_id, ButtonState.CHECKED, checked)
                    self.regionToggled.emit(region_id, checked)
                    linked = self._linked_region_ids(region_id)
                    if region_id == "_main" or "_main" in linked:
                        self._checked = checked
                        self.toggled.emit(checked)
                if self._defer_click_ms is not None:
                    clicked_region = region_id
                    QTimer.singleShot(
                        self._defer_click_ms,
                        lambda rid=clicked_region: self._emit_deferred_region_click(rid),
                    )
                else:
                    self._dispatch_region_behavior(region_id, "click")
                    self.regionClicked.emit(region_id)
                    if region_id == "_main":
                        self._emit_click_signals()
                        if not sip.isValid(self):
                            return
            self._pressed_region = None
            if handled:
                event.accept()
                return

        elif event.button() == Qt.MouseButton.RightButton:
            if self._region_at(event.position()) is not None:
                self.rightClicked.emit()
                if not sip.isValid(self):
                    return
                event.accept()
                return

        elif event.button() == Qt.MouseButton.MiddleButton:
            if self._region_at(event.position()) is not None:
                self.middleClicked.emit()
                if not sip.isValid(self):
                    return
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        region_id = self._region_at(event.position()) or "_main"
        caps = [
            cap
            for (_cap_type, cap_region), cap in self._capability_map.items()
            if cap_region == region_id
        ]
        if region_id != "_main":
            caps += [
                cap
                for (_cap_type, cap_region), cap in self._capability_map.items()
                if cap_region == "_main"
            ]
        if caps and not self.shouldHandleWheelEvent(event):
            return
        for cap in caps:
            if cap.handle_wheel_event(event):
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

    def click(self) -> None:
        """Programmatic activation (QAbstractButton.click parity).

        Used by host shortcut binders and tests. Prefer this over emitting
        ``clicked`` alone so toggles and ``defer_click`` stay consistent with
        keyboard Space/Enter.
        """
        if not self.isEnabled():
            return
        self._activate_via_keyboard()

    def _activate_via_keyboard(self):
        self.pressed.emit()
        if not sip.isValid(self):
            return
        self.released.emit()
        if not sip.isValid(self):
            return
        if self._has_toggle:
            self.setChecked(not self._checked)
        if self._defer_click_ms is not None:
            QTimer.singleShot(self._defer_click_ms, self._emit_click_signals)
        else:
            self._emit_click_signals()

    def _emit_deferred_region_click(self, region_id: str | None) -> None:
        """Emit region/main click signals after ``defer_click`` delay."""
        if not sip.isValid(self):
            return
        if region_id is None:
            return
        self._dispatch_region_behavior(region_id, "click")
        if not sip.isValid(self):
            return
        self.regionClicked.emit(region_id)
        if not sip.isValid(self):
            return
        if region_id == "_main" or "_main" in self._linked_region_ids(region_id):
            self._emit_click_signals()

    def _emit_click_signals(self) -> None:
        if not sip.isValid(self):
            return
        if getattr(self, "_suppress_next_click", False):
            self._suppress_next_click = False
            # If a host also armed ``_suppress_next_context_menu`` for the
            # same gesture, clear it here — otherwise the next click is eaten
            # by context-menu builders that never saw this suppressed emit.
            if getattr(self, "_suppress_next_context_menu", False):
                self._suppress_next_context_menu = False
            return
        self.clicked.emit()
        if not sip.isValid(self):
            return
        self.shortClicked.emit()

    # -------- enabled state --------

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if enabled:
            region_enabled = {region.id: region.enabled for region in self._regions}
            for region_id in self._controller.runtime:
                if region_enabled.get(region_id, True):
                    self._controller.set_state(region_id, ButtonState.DISABLED, False)
                else:
                    self._controller.set_state(region_id, ButtonState.DISABLED, True)
        else:
            for region_id in self._controller.runtime:
                self._controller.set_state(region_id, ButtonState.DISABLED, True)
        self._sync_region_aliases()
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
        return self._controller.region_at(pos)

    def _set_region_state(
        self,
        region_id: str | None,
        state: ButtonState,
        active: bool,
        *,
        schedule_update: bool = True,
    ) -> None:
        if region_id is None:
            return
        targets = [region_id]
        if state in (ButtonState.HOVERED, ButtonState.PRESSED, ButtonState.CHECKED):
            targets = self._linked_region_ids(region_id)
        for target_id in targets:
            self._controller.set_state(target_id, state, active)
        self._sync_region_aliases()
        if schedule_update:
            self.update()

    def _linked_region_ids(self, region_id: str | None) -> list[str]:
        if not region_id:
            return []
        region = self._region_by_id(region_id)
        group = getattr(region, "group", None) if region is not None else None
        if not group:
            return [region_id]
        return [
            other.id
            for other in self._regions
            if getattr(other, "group", None) == group
        ]

    def _update_hover_region(self, pos) -> None:
        region_id = self._region_at(pos)
        if region_id is None and self._hovered_region is not None:
            # Pointer is still inside the widget but landed in a split gap
            # (or outer inset). Clearing HOVERED here is the classic
            # shared-capsule flicker when crossing region groups.
            if QRectF(self.rect()).contains(QPointF(pos)):
                return

        if region_id == self._hovered_region:
            return

        old_id = self._hovered_region
        old_linked = set(self._linked_region_ids(old_id))
        new_linked = set(self._linked_region_ids(region_id))

        # Same group (or identical link set): HOVERED membership is unchanged —
        # only the pointer region moves. A clear→set pair would paint one frame
        # with no hover and look like a flicker of the shared capsule.
        if old_linked and old_linked == new_linked:
            self._hovered_region = region_id
            self.update()
            return

        to_clear = old_linked - new_linked
        to_set = new_linked - old_linked
        self._hovered_region = region_id
        for target_id in to_clear:
            self._controller.set_state(target_id, ButtonState.HOVERED, False)
        for target_id in to_set:
            self._controller.set_state(target_id, ButtonState.HOVERED, True)
        self._sync_region_aliases()
        self.update()
