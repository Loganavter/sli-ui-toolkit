from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.config import get_flyout_timings
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import register_hover_widget
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

logger = logging.getLogger(__name__)

class _SimpleRow(QWidget):
    clicked = pyqtSignal(int)

    def __init__(
        self,
        index: int,
        text: str,
        is_current: bool,
        item_height: int,
        item_font: QFont,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.index = index
        self.text = text
        self.is_current = is_current
        self._hovered = False
        self.theme_manager = ThemeManager.get_instance()
        self.setFixedHeight(item_height)
        self.setMouseTracking(True)
        register_hover_widget(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        self.label = QLabel(text)
        self.label.setFont(item_font)
        layout.addWidget(self.label)
        try:
            self.theme_manager.theme_changed.connect(self._apply_label_style)
        except Exception:
            pass
        self._apply_label_style()

    def _apply_label_style(self):
        font = QFont(self.label.font())
        font.setBold(False)
        self.label.setFont(font)
        self.label.setProperty("class", "option-label")

    def enterEvent(self, e):
        self.setHoverActive(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setHoverActive(False)
        super().leaveEvent(e)

    def hoverHitTest(self, pos) -> bool:
        point = pos.toPoint() if hasattr(pos, "toPoint") else pos
        return self.rect().contains(point)

    def setHoverActive(self, active: bool) -> None:
        active = bool(active)
        if self._hovered != active:
            self._hovered = active
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit(self.index)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = self.theme_manager
        if self.is_current or self._hovered:
            bg_color = tm.get_color("list_item.background.hover")
        else:
            bg_color = tm.get_color("list_item.background.normal")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        background_rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(background_rect, 5, 5)
        if self.is_current:
            indicator_pen = QPen(tm.get_color("accent"))
            indicator_pen.setWidth(3)
            indicator_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(indicator_pen)
            y1, y2 = self.rect().top() + 7, self.rect().bottom() - 7
            x = self.rect().left() + indicator_pen.width()
            painter.drawLine(x, y1, x, y2)

class SimpleOptionsFlyout(BaseFlyout):
    item_chosen = pyqtSignal(int)
    closed = pyqtSignal()

    MARGIN = 8
    APPEAR_EXTRA_Y = 6
    MAX_VISIBLE_ITEMS = 12
    WINDOW_MARGIN = 8

    def __init__(self, parent_widget=None):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self._options: list[str] = []
        self._current_index: int = -1
        self._item_height = 36
        self._item_font = QFont(QApplication.font(self))
        self._max_visible_items = self.MAX_VISIBLE_ITEMS
        self._move_duration_ms = get_flyout_timings().flyout_animation_duration_ms
        self._move_easing = QEasingCurve.Type.OutQuad
        self._drop_offset_px = 80
        self._anim: QPropertyAnimation | None = None
        self._anchor_widget: QWidget | None = None

        self._main_layout.setContentsMargins(
            self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN
        )

        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(4, 4, 4, 4)

        self._scroll_area = QScrollArea(self.container)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBar(MinimalistScrollBar())
        self._scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._scroll_area.viewport().setAutoFillBackground(False)
        self._scroll_area.viewport().setStyleSheet("background: transparent;")

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rows_layout.addStretch()
        self._scroll_area.setWidget(self._rows_container)
        self.content_layout.addWidget(self._scroll_area)

        self.hide()

    def set_max_visible_items(self, n: int) -> None:
        self._max_visible_items = max(1, int(n))

    def set_row_height(self, h: int):
        self._item_height = max(28, int(h))

    def set_row_font(self, f: QFont):
        self._item_font = QFont(f)

    def populate(self, labels: list[str], current_index: int = -1):
        self._options = list(labels)
        self._current_index = (
            current_index if 0 <= current_index < len(self._options) else -1
        )
        # Clear existing rows (keep trailing stretch at end of layout).
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(0)
            if w := item.widget():
                w.deleteLater()
            del item
        for i, text in enumerate(self._options):
            row = _SimpleRow(
                i,
                text,
                i == self._current_index,
                self._item_height,
                self._item_font,
                self._rows_container,
            )
            row.clicked.connect(self._on_row_clicked)
            self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)

        self._update_size()

    def _update_size(
        self,
        match_width: int = 0,
        exact_match: bool = False,
        available_height: int | None = None,
    ):
        num = len(self._options)
        spacing = self._rows_layout.spacing()
        outer_margins = self.content_layout.contentsMargins()
        margins_v = outer_margins.top() + outer_margins.bottom()

        if num == 0:
            visible = 1
            content_h = 50
        else:
            visible = min(num, self._max_visible_items)
            if available_height is not None:
                # Subtract flyout outer margins + inner row container margins
                budget = available_height - 2 * self.MARGIN - margins_v
                if budget > 0:
                    max_by_height = max(
                        1,
                        (budget + spacing) // (self._item_height + spacing),
                    )
                    visible = min(visible, int(max_by_height))
            content_h = visible * self._item_height + max(0, visible - 1) * spacing

        container_h = content_h + margins_v

        fm = QFontMetrics(self._item_font)
        max_text_width = 0
        for text in self._options:
            w = fm.horizontalAdvance(text)
            if w > max_text_width:
                max_text_width = w

        final_w = max_text_width + 50

        if exact_match and match_width > 0:
            target_container_width = max(1, match_width - (self.MARGIN * 2))
            width = max(final_w, target_container_width)
        elif match_width > 0:
            target_container_width = match_width - (self.MARGIN * 2)
            min_container_width = max(180, target_container_width)
            width = max(final_w, min_container_width)
        else:
            width = max(final_w, 180)

        self.container.setFixedSize(width, container_h)
        total_width = width + self.MARGIN * 2
        self.setFixedSize(total_width, container_h + self.MARGIN * 2)

    def show_below(self, anchor_widget: QWidget, exact_width_match: bool = True):
        if self.isVisible() and self._anchor_widget is anchor_widget:
            self._just_opened = False
            self.hide()
            return

        self._anchor_widget = anchor_widget
        self._ensure_overlay_parent(anchor_widget)
        self.flyout_manager.request_show(self)

        if self._anim:
            self._anim.stop()
            self._anim = None

        anchor_width = anchor_widget.frameGeometry().width()
        if anchor_width <= 0:
            anchor_width = anchor_widget.geometry().width()
        if anchor_width <= 0:
            anchor_width = anchor_widget.width()

        self._just_opened = True
        self._open_timestamp = time.monotonic()

        offset = self.APPEAR_EXTRA_Y - self.MARGIN
        gap = self.WINDOW_MARGIN

        if self.overlay_layer is not None and not self.isWindow():
            parent_widget = self.parentWidget()
            avail = parent_widget.rect() if parent_widget is not None else None
            anchor_rect = (
                self.overlay_layer.anchor_rect(anchor_widget)
                if hasattr(self.overlay_layer, "anchor_rect")
                else None
            )
            if avail is not None and anchor_rect is not None:
                space_below = avail.bottom() - anchor_rect.bottom() - offset - gap
                space_above = anchor_rect.top() - avail.top() - offset - gap
                budget = max(space_below, space_above)
                self._update_size(
                    match_width=anchor_width,
                    exact_match=exact_width_match,
                    available_height=budget,
                )
            else:
                self._update_size(match_width=anchor_width, exact_match=exact_width_match)

            position = "bottom"
            if avail is not None and anchor_rect is not None:
                if (anchor_rect.bottom() + offset + self.height()) > avail.bottom() - gap \
                        and (anchor_rect.top() - offset - self.height()) >= avail.top() + gap:
                    position = "top"
            rect = self._overlay_rect_relative_to_anchor(
                anchor_widget,
                self.size(),
                position=position,
                offset=offset,
            )
            final_x = rect.x()
            final_y = rect.y()
            total_width, total_height = self.width(), self.height()
        else:
            parent_widget = self.parentWidget()
            use_parent_coords = parent_widget is not None and not self.isWindow()
            anchor_top_pos = (
                anchor_widget.mapTo(parent_widget, anchor_widget.rect().topLeft())
                if use_parent_coords
                else anchor_widget.mapToGlobal(anchor_widget.rect().topLeft())
            )
            anchor_bottom_pos = (
                anchor_widget.mapTo(parent_widget, anchor_widget.rect().bottomLeft())
                if use_parent_coords
                else anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())
            )
            anchor_center_x = (
                anchor_widget.mapTo(parent_widget, anchor_widget.rect().center()).x()
                if use_parent_coords
                else anchor_widget.mapToGlobal(anchor_widget.rect().center()).x()
            )

            if use_parent_coords:
                avail = parent_widget.rect()
            else:
                try:
                    screen = anchor_widget.screen() or QGuiApplication.screenAt(anchor_bottom_pos)
                    avail = screen.availableGeometry()
                except Exception:
                    avail = QGuiApplication.primaryScreen().availableGeometry()

            space_below = avail.bottom() - anchor_bottom_pos.y() - offset - gap
            space_above = anchor_top_pos.y() - avail.top() - offset - gap
            budget = max(space_below, space_above)
            self._update_size(
                match_width=anchor_width,
                exact_match=exact_width_match,
                available_height=budget,
            )
            total_width, total_height = self.width(), self.height()

            if space_below >= total_height or space_below >= space_above:
                final_y = anchor_bottom_pos.y() + offset
            else:
                final_y = anchor_top_pos.y() - offset - total_height
            final_x = int(anchor_center_x - total_width / 2) + 2

            final_x = max(avail.left(), min(final_x, avail.right() - total_width))
            final_y = max(avail.top(), min(final_y, avail.bottom() - total_height))

        start_pos, end_pos = QPoint(final_x, final_y - self._drop_offset_px), QPoint(
            final_x, final_y
        )

        self.move(start_pos)

        self.setVisible(True)
        self.raise_()

        if not self.isVisible():
            logger.warning(
                "SimpleOptionsFlyout: Widget failed to become visible after show()"
            )
            self.show()

        QApplication.processEvents()

        if exact_width_match:
            actual_width_after = self.width()
            if actual_width_after != total_width:
                logger.warning(
                    f"SimpleOptionsFlyout.show_below: Width changed after processEvents! "
                    f"Before={total_width}, After={actual_width_after}, anchor_width={anchor_width}"
                )
                self.setFixedSize(total_width, total_height)

        anim_pos = QPropertyAnimation(self, b"pos", self)
        anim_pos.setDuration(self._move_duration_ms)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(end_pos)
        anim_pos.setEasingCurve(self._move_easing)
        anim_pos.finished.connect(self._on_animation_finished)
        self._anim = anim_pos
        anim_pos.start()

    def _on_animation_finished(self):
        if self._anim:
            anim_obj = self._anim
            self._anim = None
            anim_obj.deleteLater()

    def _on_row_clicked(self, idx: int):
        self.item_chosen.emit(idx)
        if hasattr(self, "_just_opened"):
            self._just_opened = False
        self.hide()

    def hide(self):
        super().hide()
        if self.parent_widget:
            win = self.parent_widget.window()
            if win:
                win.activateWindow()
                win.setFocus()

    def hideEvent(self, e):
        if hasattr(self, "_just_opened") and getattr(self, "_just_opened", False):
            time_since_open = time.monotonic() - getattr(self, "_open_timestamp", 0)
            if time_since_open < 0.3:
                e.ignore()
                return
            self._just_opened = False

        super().hideEvent(e)

        if self._anim:
            self._anim.stop()
            self._anim = None

        if hasattr(self, "_just_opened"):
            self._just_opened = False

        try:
            self.closed.emit()
        except Exception:
            pass
