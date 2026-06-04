"""InstancesCounterButton — single-capsule +/- counter with internal painting.

Rendered as a single rounded widget; in split mode (count > 1) a thin divider
separates a top "+" region (addClicked) from a bottom "−" region (removeClicked).
No nested QPushButtons or QSS — fully self-contained paintEvent.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import WheelScrollPolicyMixin
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap


class InstancesCounterButton(WheelScrollPolicyMixin, QWidget):
    addClicked = pyqtSignal()
    removeClicked = pyqtSignal()
    wheelScrolled = pyqtSignal(int)
    countChanged = pyqtSignal(int)

    _OUTER_SIZE = 36
    _CORNER_RADIUS = 6

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        wheel_requires_focus: bool = False,
    ) -> None:
        super().__init__(parent)
        self.init_wheel_scroll_policy(wheel_requires_focus=wheel_requires_focus)
        self._count = 1
        self._can_remove = False
        self.setFixedSize(self._OUTER_SIZE, self._OUTER_SIZE)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)

        self._hover_top = False
        self._hover_bottom = False
        self._hover_whole = False
        self._pressed_region: str | None = None

        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self.update)

    # ---------- public API ----------

    def set_count(self, count: int) -> None:
        count = max(1, int(count))
        if self._count != count:
            self._count = count
            self.update()
            self.countChanged.emit(count)

    set_magnifier_count = set_count

    def set_can_remove(self, can_remove: bool) -> None:
        can_remove = bool(can_remove)
        if self._can_remove != can_remove:
            self._can_remove = can_remove
            self.update()

    def count(self) -> int:
        return self._count

    magnifier_count = count

    def popup_targets(self) -> tuple[QWidget, ...]:
        return (self,)

    # ---------- region geometry ----------

    def _split_mode(self) -> bool:
        return self._count > 1

    def _top_rect(self) -> QRect:
        h = self.height() // 2
        return QRect(0, 0, self.width(), h)

    def _bottom_rect(self) -> QRect:
        h = self.height() // 2
        return QRect(0, h, self.width(), self.height() - h)

    # ---------- events ----------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._update_hover_from_pos(event.position().toPoint() if hasattr(event, "position") else None)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_top = False
        self._hover_bottom = False
        self._hover_whole = False
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._update_hover_from_pos(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed_region = self._region_at(event.position().toPoint())
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            region = self._region_at(event.position().toPoint())
            if region is not None and region == self._pressed_region:
                if region == "whole" or region == "top":
                    self.addClicked.emit()
                elif region == "bottom" and self._can_remove:
                    self.removeClicked.emit()
            self._pressed_region = None
            self.update()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if not self.shouldHandleWheelEvent(event):
            return
        delta = int(event.angleDelta().y())
        if delta:
            self.wheelScrolled.emit(delta)
            event.accept()
            return
        super().wheelEvent(event)

    def _region_at(self, pos) -> str | None:
        if not self.rect().contains(pos):
            return None
        if not self._split_mode():
            return "whole"
        return "top" if self._top_rect().contains(pos) else "bottom"

    def _update_hover_from_pos(self, pos) -> None:
        if pos is None or not self.rect().contains(pos):
            self._hover_top = self._hover_bottom = self._hover_whole = False
        elif not self._split_mode():
            self._hover_whole = True
            self._hover_top = self._hover_bottom = False
        else:
            self._hover_whole = False
            self._hover_top = self._top_rect().contains(pos)
            self._hover_bottom = not self._hover_top
        self.update()

    # ---------- paint ----------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = self._theme_manager

        bg_normal = QColor(tm.get_color("button.toggle.background.normal"))
        bg_hover = QColor(tm.get_color("button.toggle.background.hover"))
        bg_pressed = QColor(tm.get_color("button.toggle.background.pressed"))
        divider_color = QColor(tm.try_get_color("separator.color")
                               or tm.get_color("dialog.border"))
        icon_color = QColor(tm.get_color("dialog.text"))
        disabled_alpha = 90

        rect_f = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # Whole capsule background (uses hover/pressed for single mode).
        if not self._split_mode():
            if self._pressed_region == "whole":
                bg = bg_pressed
            elif self._hover_whole:
                bg = bg_hover
            else:
                bg = bg_normal
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(rect_f, self._CORNER_RADIUS, self._CORNER_RADIUS)
            self._draw_icon_centered(painter, self.rect(), "add_circle", icon_color, size=20)
            painter.end()
            return

        # Split mode: paint base capsule then overlay hover/pressed per half.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_normal)
        painter.drawRoundedRect(rect_f, self._CORNER_RADIUS, self._CORNER_RADIUS)

        top_rect = self._top_rect()
        bottom_rect = self._bottom_rect()

        def overlay(region_rect: QRect, region_name: str, *, enabled: bool) -> None:
            if not enabled:
                return
            if self._pressed_region == region_name:
                fill = bg_pressed
            elif (region_name == "top" and self._hover_top) or \
                 (region_name == "bottom" and self._hover_bottom):
                fill = bg_hover
            else:
                return
            painter.save()
            painter.setClipRect(region_rect)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect_f, self._CORNER_RADIUS, self._CORNER_RADIUS)
            painter.restore()

        overlay(top_rect, "top", enabled=True)
        overlay(bottom_rect, "bottom", enabled=self._can_remove)

        # Divider
        painter.setPen(QPen(divider_color, 1.0))
        y = top_rect.bottom()
        painter.drawLine(2, y, self.width() - 2, y)

        # Icons (dim bottom if remove disabled)
        top_color = QColor(icon_color)
        bottom_color = QColor(icon_color)
        if not self._can_remove:
            bottom_color.setAlpha(disabled_alpha)
        self._draw_icon_centered(painter, top_rect, "add", top_color, size=14)
        self._draw_icon_centered(painter, bottom_rect, "remove", bottom_color, size=14)
        painter.end()

    def _draw_icon_centered(
        self, painter: QPainter, rect: QRect, name: str, color: QColor, *, size: int,
    ) -> None:
        pixmap = normalized_icon_pixmap(name, size)
        if pixmap.isNull():
            painter.setPen(QPen(color))
            font = painter.font()
            font.setPixelSize(int(size * 0.9))
            font.setBold(True)
            painter.setFont(font)
            glyph = "+" if name in ("add", "add_circle") else "−"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)
            return
        x = rect.x() + (rect.width() - pixmap.width()) // 2
        y = rect.y() + (rect.height() - pixmap.height()) // 2
        painter.setOpacity(color.alphaF())
        painter.drawPixmap(x, y, pixmap)
        painter.setOpacity(1.0)
