from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QTabBar, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px



class _AdaptiveTabBar(QWidget):
    _RADIUS = 8.0
    _MIN_WIDTH = 10
    _WIDTH_SCALE = 1.15
    _SIDE_PADDING = 12
    _HORIZONTAL_INSET = 2
    _TEXT_SAFETY = 6
    _CLOSE_GAP = 2
    _CLOSE_RIGHT_MARGIN = 2
    _TEXT_FADE = 26
    _SELECTED_SHADOW_OFFSET = 0.5
    _SELECTED_SHADOW_SPREAD = 1
    _TEXT_HEIGHT_PADDING = 16

    currentChanged = Signal(int)
    tabContextMenuRequested = Signal(int, QPoint)
    tabCloseRequested = Signal(int)

    def __init__(self, *, close_button_width: int, parent=None):
        super().__init__(parent)
        self._close_button_width = int(close_button_width)
        self._visual_tab_height = 36
        self._hover_index = -1
        self._current_index = -1
        self._focused_index = -1
        self._scroll_offset = 0
        self._keyboard_focus = False
        # Each entry: {"text": str, "data": Any, "tooltip": str, "buttons": {QTabBar.ButtonPosition: QWidget|None}}
        self._tabs: list[dict] = []
        self._rects: list[QRect] = []
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Text is painted natively with widget.font(); pin the scaled UI face
        # and re-resolve on font_changed / scale_changed — otherwise tab text
        # and width math stay at the design size while the strip grows.
        apply_ui_font(self)
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

    def _on_scale_changed(self, _factor: float) -> None:
        # The close slots bake their size from the button at creation;
        # re-fit them BEFORE the relayout positions them, so the buttons
        # stay inside their tabs at the new factor.
        self._resync_close_slots()
        self._relayout()
        self.updateGeometry()
        self.update()

    def _resync_close_slots(self) -> None:
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            resync = getattr(slot, "resync", None)
            if callable(resync):
                resync()

    def set_visual_tab_height(self, height: int) -> None:
        self._visual_tab_height = max(1, int(height))
        self.updateGeometry()
        self.update()

    # -- tab collection management (QTabBar-compatible surface) --------

    def addTab(self, text: str) -> int:  # noqa: N802
        return self.insertTab(len(self._tabs), text)

    def insertTab(self, index: int, text: str) -> int:  # noqa: N802
        index = max(0, min(int(index), len(self._tabs)))
        self._tabs.insert(index, {"text": text, "data": None, "tooltip": "", "buttons": {}})
        self._rects.insert(index, QRect())
        previous_current = self._current_index
        if self._current_index == -1:
            self._current_index = index
        elif index <= self._current_index:
            self._current_index += 1
        self._relayout()
        self.updateGeometry()
        self.update()
        if self._current_index != previous_current:
            self.currentChanged.emit(self._current_index)
        return index

    def removeTab(self, index: int) -> None:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return
        entry = self._tabs.pop(index)
        self._rects.pop(index)
        for widget in entry["buttons"].values():
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        previous_current = self._current_index
        if not self._tabs:
            self._current_index = -1
        elif index < self._current_index:
            self._current_index -= 1
        elif index == self._current_index:
            self._current_index = min(index, len(self._tabs) - 1)
        self._relayout()
        self.updateGeometry()
        self.update()
        if self._current_index != previous_current:
            self.currentChanged.emit(self._current_index)

    def count(self) -> int:
        return len(self._tabs)

    def currentIndex(self) -> int:  # noqa: N802
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if index == self._current_index or not (0 <= index < len(self._tabs)):
            return
        self._current_index = index
        # Keep keyboard focus in sync with selection when selection
        # changes programmatically or via mouse.
        self._focused_index = index
        self._ensure_visible(index)
        self._position_tab_buttons()
        self.update()
        self.currentChanged.emit(index)

    def _focusedTab(self) -> int:
        if 0 <= self._focused_index < len(self._tabs):
            return self._focused_index
        return self._current_index

    def _move_focus(self, delta: int) -> None:
        count = len(self._tabs)
        if count == 0:
            return
        base = self._focusedTab()
        if base < 0:
            base = self._current_index if self._current_index >= 0 else 0
        new = (base + delta) % count
        if new == self._focused_index:
            return
        self._focused_index = new
        self._ensure_visible(new)
        self._position_tab_buttons()
        self.update()

    def _activate_focused(self) -> bool:
        idx = self._focusedTab()
        if 0 <= idx < len(self._tabs) and idx != self._current_index:
            self.setCurrentIndex(idx)
            return True
        return False

    def tabText(self, index: int) -> str:  # noqa: N802
        return self._tabs[index]["text"]

    def setTabText(self, index: int, text: str) -> None:  # noqa: N802
        self._tabs[index]["text"] = text
        self._relayout()
        self.updateGeometry()
        self.update()

    def tabData(self, index: int) -> Any:  # noqa: N802
        return self._tabs[index]["data"]

    def setTabData(self, index: int, data: Any) -> None:  # noqa: N802
        self._tabs[index]["data"] = data

    def tabToolTip(self, index: int) -> str:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return ""
        return self._tabs[index]["tooltip"]

    def setTabToolTip(self, index: int, text: str) -> None:  # noqa: N802
        self._tabs[index]["tooltip"] = text

    def tabButton(self, index: int, position) -> QWidget | None:  # noqa: N802
        if not (0 <= index < len(self._tabs)):
            return None
        return self._tabs[index]["buttons"].get(position)

    def setTabButton(self, index: int, position, widget: QWidget | None) -> None:  # noqa: N802
        existing = self._tabs[index]["buttons"].get(position)
        if existing is not None and existing is not widget:
            existing.hide()
            existing.setParent(None)
            existing.deleteLater()
        self._tabs[index]["buttons"][position] = widget
        if widget is not None:
            widget.setParent(self)
            widget.show()
        self._position_tab_buttons()

    def tabAt(self, pos: QPoint) -> int:  # noqa: N802
        for index, rect in enumerate(self._visual_rects()):
            if rect.contains(pos):
                return index
        return -1

    def tabRect(self, index: int) -> QRect:  # noqa: N802
        if not (0 <= index < len(self._rects)):
            return QRect()
        return self._rects[index].translated(-self._scroll_offset, 0)

    # -- sizing ----------------------------------------------------------

    def standard_tab_width(self, index: int) -> int:
        text_width = QFontMetrics(self.font()).horizontalAdvance(self._tabs[index]["text"])
        natural = (
            text_width
            + scaled_px(self._SIDE_PADDING) * 2
            + scaled_px(self._HORIZONTAL_INSET)
            + scaled_px(self._TEXT_SAFETY)
        )
        return max(scaled_px(self._MIN_WIDTH), round(natural * self._WIDTH_SCALE))

    def _tab_width(self, index: int) -> int:
        return self.standard_tab_width(index) + self._close_button_width + scaled_px(self._CLOSE_GAP)

    def full_tabs_width(self) -> int:
        return sum(self._tab_width(index) for index in range(len(self._tabs)))

    def _tab_height(self) -> int:
        native = QFontMetrics(self.font()).height() + scaled_px(self._TEXT_HEIGHT_PADDING)
        return max(native, self._visual_tab_height)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.full_tabs_width(), self._tab_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._MIN_WIDTH, self._tab_height())

    # -- layout / scrolling ----------------------------------------------

    def _relayout(self) -> None:
        x = 0
        for index in range(len(self._tabs)):
            width = self._tab_width(index)
            self._rects[index] = QRect(x, 0, width, self._tab_height())
            x += width
        self._clamp_scroll_offset()
        self._position_tab_buttons()

    def _max_scroll_offset(self) -> int:
        total = self._rects[-1].right() + 1 if self._rects else 0
        return max(0, total - self.width())

    def _clamp_scroll_offset(self) -> None:
        self._scroll_offset = max(0, min(self._scroll_offset, self._max_scroll_offset()))

    def _visual_rects(self) -> list[QRect]:
        return [rect.translated(-self._scroll_offset, 0) for rect in self._rects]

    def _ensure_visible(self, index: int) -> None:
        if not (0 <= index < len(self._rects)):
            return
        rect = self._rects[index]
        if rect.left() - self._scroll_offset < 0:
            self._scroll_offset = rect.left()
        elif rect.right() - self._scroll_offset > self.width():
            self._scroll_offset = rect.right() - self.width()
        self._clamp_scroll_offset()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._max_scroll_offset() <= 0:
            super().wheelEvent(event)
            return
        delta = event.pixelDelta()
        dx = delta.x()
        dy = delta.y()
        if dx == 0 and dy == 0:
            angle = event.angleDelta()
            dx = angle.x()
            dy = angle.y()
        step = -(dx if dx != 0 else dy) / 120 * 40
        if step == 0:
            super().wheelEvent(event)
            return
        self._scroll_offset += round(step)
        self._clamp_scroll_offset()
        self._position_tab_buttons()
        self.update()
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = self._palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(event.rect())
        painter.fillRect(self.rect(), QColor(palette["strip"]))
        for index in range(len(self._tabs)):
            if index != self._current_index:
                self._paint_visible_tab(painter, index, event.rect(), palette)
        if self._current_index >= 0:
            self._paint_visible_tab(painter, self._current_index, event.rect(), palette)

    def _paint_visible_tab(self, painter, index, exposed_rect, palette) -> None:
        rect = self.tabRect(index)
        if rect.isValid() and rect.intersects(exposed_rect):
            self._paint_tab(painter, index, rect, palette)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.tabAt(event.position().toPoint())
            if index >= 0:
                self.setCurrentIndex(index)
                self._focused_index = index
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        import logging
        _log = logging.getLogger(__name__)
        key = event.key()
        _log.debug("[TAB-BAR] key=%s count=%s current=%s", key, len(self._tabs), self._current_index)
        count = len(self._tabs)
        if count == 0:
            return super().keyPressEvent(event)
        current = self._current_index if self._current_index >= 0 else 0
        if key == Qt.Key.Key_Down:
            # Hand off to the next focusable widget in the app layout
            # (typically the content area below the tab strip).
            if self.focusNextChild():
                event.accept()
                return
        if key == Qt.Key.Key_Up:
            if self.focusPreviousChild():
                event.accept()
                return
        if key == Qt.Key.Key_Left:
            # Move keyboard focus, don't activate yet — Enter confirms.
            if self._focusedTab() == 0:
                strip = self.parentWidget()
                if strip is not None:
                    add_btn = getattr(strip, "add_button", None)
                    if add_btn is not None and add_btn.isVisible():
                        add_btn.setFocus(Qt.FocusReason.OtherFocusReason)
                        event.accept()
                        return
            self._move_focus(-1)
            event.accept()
        elif key == Qt.Key.Key_Right:
            if self._focusedTab() == count - 1:
                strip = self.parentWidget()
                if strip is not None:
                    add_btn = getattr(strip, "add_button", None)
                    if add_btn is not None and add_btn.isVisible():
                        add_btn.setFocus(Qt.FocusReason.OtherFocusReason)
                        event.accept()
                        return
            self._move_focus(1)
            event.accept()
        elif key == Qt.Key.Key_Home:
            if count:
                self._focused_index = 0
                self._ensure_visible(0)
                self.update()
            event.accept()
        elif key == Qt.Key.Key_End:
            if count:
                self._focused_index = count - 1
                self._ensure_visible(count - 1)
                self.update()
            event.accept()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._activate_focused():
                event.accept()
                return
            super().keyPressEvent(event)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            target = self._focusedTab()
            if 0 <= target < count:
                self.tabCloseRequested.emit(target)
                event.accept()
        else:
            super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            pos = event.position().toPoint()
            index = self.tabAt(pos)
            if index >= 0 and not self._close_slot_contains(index, pos):
                if hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                else:
                    global_pos = self.mapToGlobal(pos)
                self.tabContextMenuRequested.emit(index, global_pos)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def _close_slot_contains(self, index: int, pos: QPoint) -> bool:
        slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if slot is None or not slot.isVisible():
            return False
        return slot.geometry().contains(pos)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._set_hover_index(self.tabAt(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def set_hover_from_global(self, global_pos) -> None:
        local_pos = self.mapFromGlobal(global_pos)
        hover_index = self.tabAt(local_pos) if self.rect().contains(local_pos) else -1
        self._set_hover_index(hover_index)

    def _set_hover_index(self, index: int) -> None:
        if index != self._hover_index:
            self._hover_index = index
            self.update()
            self._update_close_slots()

    def _update_close_slots(self) -> None:
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if slot is not None:
                slot.update()
                button = getattr(slot, "button", None)
                if button is not None:
                    button.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover_index != -1:
            self._hover_index = -1
            self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):  # noqa: N802
        # Ring modality resolved centrally via NavigationManager (4.2.4):
        # input device is the source of truth, reason is only a hint.
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import (
                resolve_keyboard_focus,
            )

            self._keyboard_focus = resolve_keyboard_focus(event.reason())
        except Exception:
            # degraded, no manager
            self._keyboard_focus = event.reason() not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
                Qt.FocusReason.PopupFocusReason,
            )
        if self._focused_index < 0 or not (0 <= self._focused_index < len(self._tabs)):
            self._focused_index = self._current_index
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):  # noqa: N802
        self._keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._clamp_scroll_offset()
        # Keep the current tab (and its close button) in view when the bar
        # shrinks — plain clamping can leave it scrolled past the edge.
        if self._current_index >= 0:
            self._ensure_visible(self._current_index)
        self._position_tab_buttons()

    def _position_tab_buttons(self) -> None:
        for index in range(len(self._tabs)):
            slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
            if slot is None:
                continue
            tab_rect = self._painted_tab_rect(self.tabRect(index))
            x = tab_rect.right() - slot.width() - scaled_px(self._CLOSE_RIGHT_MARGIN) + 1
            y = tab_rect.center().y() - slot.height() // 2
            slot.move(x, y)

    def _painted_tab_rect(self, rect: QRect) -> QRect:
        height = min(rect.height(), self._visual_tab_height)
        top = rect.top() + max(0, (rect.height() - height) // 2)
        return QRect(rect.left() + 1, top, max(0, rect.width() - 2), height)

    def _paint_tab(self, painter: QPainter, index: int, rect: QRect, palette: dict[str, str]) -> None:
        selected = index == self.currentIndex()
        hovered = not selected and index == self._hover_index
        focused = (index == self._focusedTab() and self._keyboard_focus and self.hasFocus())
        tab_rect = self._painted_tab_rect(rect)
        if selected:
            self._paint_selected_shadow(painter, tab_rect)
            self._paint_selected_background(painter, tab_rect, palette)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["hover"]))
            painter.drawRoundedRect(tab_rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))
        # Focus ring: same style as Button's FocusLayer — accent-colored
        # QPainterPath rounded rect on the FULL tab area (including close
        # button slot) so the ring covers all child widgets.
        if focused:
            from PySide6.QtGui import QPainterPath

            factor = UiScale.get_instance().factor()
            design_radius = self._RADIUS / factor if factor > 0 else self._RADIUS
            thickness = max(1.0, 2.0 * factor)
            inset = thickness * 0.5
            ring = QRectF(rect).adjusted(inset, inset, -inset, -inset)
            if ring.width() > 0 and ring.height() > 0:
                path = QPainterPath()
                path.addRoundedRect(ring, design_radius, design_radius)
                accent_raw = palette.get("accent")
                if accent_raw is None:
                    from sli_ui_toolkit.theme import ThemeManager as _TM

                    tm2 = _TM.get_instance()
                    accent_c = tm2.try_get_color("accent")
                    accent_raw = accent_c.name() if accent_c is not None and accent_c.isValid() else tm2.get_color("accent").name()
                color = QColor(accent_raw)
                color.setAlpha(220)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(color, thickness))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
                painter.restore()

        text_right = tab_rect.right() - scaled_px(self._SIDE_PADDING)
        close_slot = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
        has_close = close_slot is not None and close_slot.isVisible()
        if has_close and close_slot is not None:
            text_right = min(text_right, close_slot.geometry().left() - scaled_px(self._CLOSE_GAP))
        text_rect = QRect(
            tab_rect.left() + scaled_px(self._SIDE_PADDING),
            tab_rect.top(),
            max(0, text_right - tab_rect.left() - scaled_px(self._SIDE_PADDING) + 1),
            tab_rect.height(),
        )
        if text_rect.width() <= 0:
            return
        metrics = QFontMetrics(self.font())
        raw_text = self.tabText(index)
        needs_fade = has_close and metrics.horizontalAdvance(raw_text) > text_rect.width()
        text = raw_text if needs_fade else metrics.elidedText(
            raw_text, Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.setPen(QColor(palette["text"]))
        painter.save()
        painter.setClipRect(text_rect)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()
        if needs_fade:
            fade = QLinearGradient(text_rect.right() - scaled_px(self._TEXT_FADE), 0, text_rect.right() + 1, 0)
            fade.setColorAt(0.0, QColor(0, 0, 0, 0))
            fade.setColorAt(1.0, QColor(palette["background"]))
            painter.fillRect(
                QRect(
                    text_rect.right() - scaled_px(self._TEXT_FADE),
                    tab_rect.top(),
                    scaled_px(self._TEXT_FADE) + 1,
                    tab_rect.height(),
                ),
                fade,
            )

    def close_slot_background_color(self, slot: QWidget) -> QColor | None:
        for index in range(self.count()):
            if self.tabButton(index, QTabBar.ButtonPosition.RightSide) is not slot:
                continue
            if index == self.currentIndex():
                return QColor(self._palette()["background"])
            if index == self._hover_index:
                return QColor(self._palette()["hover"])
            return QColor(self._palette()["strip"])
        return None

    def _paint_selected_background(self, painter, rect, palette) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette["background"]))
        painter.drawRoundedRect(rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))
        painter.setPen(QPen(QColor(palette["border"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))

    def _paint_selected_shadow(self, painter, rect) -> None:
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.save()
        painter.setClipRect(
            QRectF(
                rect.left() - 1,
                rect.bottom() - 1,
                rect.width() + 2,
                self._SELECTED_SHADOW_OFFSET + self._SELECTED_SHADOW_SPREAD + 3,
            )
        )
        painter.setPen(Qt.PenStyle.NoPen)
        soft_rect = QRectF(rect).adjusted(
            0,
            self._SELECTED_SHADOW_OFFSET,
            0,
            self._SELECTED_SHADOW_OFFSET + self._SELECTED_SHADOW_SPREAD,
        )
        painter.setBrush(QColor(0, 0, 0, 55))
        painter.drawRoundedRect(soft_rect, scaled_px(self._RADIUS), scaled_px(self._RADIUS))
        core_rect = QRectF(rect).adjusted(
            1,
            self._SELECTED_SHADOW_OFFSET - 1,
            -1,
            self._SELECTED_SHADOW_OFFSET,
        )
        painter.setBrush(QColor(0, 0, 0, 125))
        painter.drawRoundedRect(core_rect, scaled_px(self._RADIUS) - 1, scaled_px(self._RADIUS) - 1)
        painter.restore()

    def _palette(self) -> dict[str, str]:
        theme = ThemeManager.get_instance()

        def color(token: str, fallback_token: str | None = None) -> str:
            value = theme.try_get_color(token)
            if value is not None and value.isValid():
                return value.name()
            # Fallback through palette defaults (theme-aware) instead of hard light hex
            fb = fallback_token or token
            fallback_color = theme.try_get_color(fb)
            if fallback_color is not None and fallback_color.isValid():
                return fallback_color.name()
            return theme.get_color(token).name()

        return {
            "strip": color("button.toggle.background.normal"),
            "background": color("Window"),
            "border": color("separator.color"),
            "hover": color("button.toggle.background.hover"),
            "text": color("WindowText"),
        }
