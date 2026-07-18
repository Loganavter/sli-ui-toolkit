from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
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
from sli_ui_toolkit.ui.managers.ui_font import rebase_font, ui_font
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout, slide_start_delta

logger = logging.getLogger(__name__)


class _RowBackgroundLayer(Layer):
    """Inset rounded background, list_item.* tokens, hover/current → hover color."""

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        states = ctx.effective_states
        is_active = (
            widget.is_current
            or ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
        )
        key = "list_item.background.hover" if is_active else "list_item.background.normal"
        rect = ctx.rect.toRect().adjusted(2, 2, -2, -2)
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tm.get_color(key)))
        p.drawRoundedRect(rect, 5, 5)


class _CurrentIndicatorLayer(Layer):
    """Левый accent-индикатор для current row."""

    def applies(self, ctx) -> bool:
        return bool(getattr(ctx.widget, "is_current", False))

    def draw(self, ctx, tm: ThemeManager) -> None:
        rect = ctx.rect.toRect()
        pen = QPen(tm.get_color("accent"))
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(pen)
        x = rect.left() + pen.width()
        p.drawLine(x, rect.top() + 7, x, rect.bottom() - 7)


class _SimpleRow(Button):
    rowClicked = Signal(int)

    def __init__(
        self,
        index: int,
        text: str,
        is_current: bool,
        item_height: int,
        item_font: QFont,
        parent: QWidget = None,
    ):
        super().__init__(
            text="",
            size=(0, item_height),
            corner_radius=5,
            layers=[_RowBackgroundLayer(), RippleLayer(), _CurrentIndicatorLayer()],
            parent=parent,
        )
        self.index = index
        self.text = text
        self.is_current = is_current
        self._item_height = item_height
        layout = QHBoxLayout(self)
        # Accent indicator draws inside the left pad; keep pad tight to the label.
        layout.setContentsMargins(8, 0, 8, 0)
        self.label = QLabel(text)
        self.label.setFont(item_font)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.label)
        try:
            self.theme_manager.theme_changed.connect(self._apply_label_style)
        except Exception:
            pass
        self._apply_label_style()
        self.clicked.connect(lambda: self.rowClicked.emit(self.index))

    def sizeHint(self) -> QSize:
        margins = self.layout().contentsMargins() if self.layout() is not None else None
        pad = (
            (margins.left() + margins.right())
            if margins is not None
            else 16
        )
        label_w = self.label.sizeHint().width() if self.label is not None else 0
        return QSize(max(1, label_w + pad), self._item_height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _apply_label_style(self):
        font = rebase_font(self.label.font())
        font.setBold(False)
        self.label.setFont(font)
        self.label.setProperty("class", "option-label")

class SimpleOptionsFlyout(BaseFlyout):
    item_chosen = Signal(int)
    closed = Signal()

    # Identity for host ``GroupShowPolicy`` (interp / combo pickers, etc.).
    flyout_group = "options"

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
        self._item_font = ui_font()
        self._max_visible_items = self.MAX_VISIBLE_ITEMS
        timings = get_flyout_timings()
        self._move_duration_ms = timings.flyout_animation_duration_ms
        self._move_easing = QEasingCurve.Type.OutQuad
        self._drop_offset_px = timings.dropdown_drop_offset_px
        self._anim: QPropertyAnimation | None = None
        self._anchor_widget: QWidget | None = None

        self._main_layout.setContentsMargins(
            self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN
        )

        self.content_layout.setSpacing(0)
        self.content_layout.setContentsMargins(2, 2, 2, 2)

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
        # Callers often pass QApplication.font() / widget.font() which may still
        # carry a baked system face — rebase onto UiFont.
        self._item_font = rebase_font(f)

    def row_widget(self, index: int) -> QWidget | None:
        """Return the live row button for ``index``, or ``None``."""
        if not (0 <= index < len(self._options)):
            return None
        # Trailing stretch stays at the end of ``_rows_layout``.
        if index >= max(0, self._rows_layout.count() - 1):
            return None
        item = self._rows_layout.itemAt(index)
        return item.widget() if item is not None else None

    def populate(self, labels: list[str], current_index: int = -1):
        self._options = list(labels)
        self._current_index = (
            current_index if 0 <= current_index < len(self._options) else -1
        )
        # Batch: каждый insertWidget() триггерит relayout+repaint у _rows_container.
        # Для N строк это ≈O(N²) и есть основной источник фриза при открытии
        # ScrollableComboBox-flyout'а с длинным списком.
        self._rows_container.setUpdatesEnabled(False)
        try:
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
                row.rowClicked.connect(self._on_row_clicked)
                self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)
            self._update_size()
        finally:
            self._rows_container.setUpdatesEnabled(True)

    def _update_size(
        self,
        match_width: int = 0,
        exact_match: bool = False,
        available_height: int | None = None,
    ):
        """Size the panel to the longest row, optionally at least ``match_width``.

        ``exact_match`` is kept for ``show_below`` call-site compatibility; when
        ``match_width`` is set, width is ``max(content, anchor)`` (no 180px floor).
        """
        del exact_match
        num = len(self._options)
        spacing = self._rows_layout.spacing()
        outer_margins = self.content_layout.contentsMargins()
        margins_v = outer_margins.top() + outer_margins.bottom()
        margins_h = outer_margins.left() + outer_margins.right()

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

        # Prefer live row sizeHints (label + row pad). Font metrics are a
        # fallback before rows exist / while updates are disabled mid-populate.
        content_w = 0
        for index in range(max(0, self._rows_layout.count() - 1)):
            row = self._rows_layout.itemAt(index).widget()
            if row is None:
                continue
            content_w = max(content_w, int(row.sizeHint().width()))
        if content_w <= 0:
            fm = QFontMetrics(self._item_font)
            text_w = max(
                (fm.boundingRect(text).width() for text in self._options),
                default=0,
            )
            content_w = text_w + 16
        content_w = content_w + margins_h

        if match_width > 0:
            target_container_width = max(1, match_width - (self.MARGIN * 2))
            width = max(content_w, target_container_width)
        else:
            width = max(1, content_w)

        self.container.setFixedSize(width, container_h)
        total_width = width + self.MARGIN * 2
        self.setFixedSize(total_width, container_h + self.MARGIN * 2)

    def show_aligned(self, *args, **kwargs):
        # Re-fit after populate so BaseFlyout.adjustSize cannot keep a stale
        # oversized hint from an earlier open.
        self._update_size()
        return super().show_aligned(*args, **kwargs)

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
                # size-based edges (not QRect.bottom()/top() inclusive pixels)
                anchor_top_edge = anchor_rect.y()
                anchor_bottom_edge = anchor_rect.y() + anchor_rect.height()
                space_below = avail.bottom() - anchor_bottom_edge - offset - gap
                space_above = anchor_top_edge - avail.top() - offset - gap
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
                anchor_top_edge = anchor_rect.y()
                anchor_bottom_edge = anchor_rect.y() + anchor_rect.height()
                if (anchor_bottom_edge + offset + self.height()) > avail.bottom() - gap \
                        and (anchor_top_edge - offset - self.height()) >= avail.top() + gap:
                    position = "top"
            rect = self._overlay_rect_relative_to_anchor(
                anchor_widget,
                self.size(),
                position=position,
                offset=offset,
            )
            final_x = rect.x()
            total_width, total_height = self.width(), self.height()
            # Recompute Y with size-based edges — place_surface_rect still uses
            # inclusive QRect.bottom()/top() and lands 1px into the anchor.
            if anchor_rect is not None:
                if position == "bottom":
                    final_y = anchor_rect.y() + anchor_rect.height() + offset
                else:
                    final_y = anchor_rect.y() - offset - total_height
            else:
                final_y = rect.y()
        else:
            parent_widget = self.parentWidget()
            use_parent_coords = parent_widget is not None and not self.isWindow()

            def _map(point: QPoint) -> QPoint:
                if use_parent_coords:
                    return anchor_widget.mapTo(parent_widget, point)
                return anchor_widget.mapToGlobal(point)

            # Prefer size-based edges. QRect.bottomLeft() is the inclusive
            # last pixel (height-1) and short-changes clearance by 1px.
            anchor_top_left = _map(QPoint(0, 0))
            anchor_size = anchor_widget.size()
            anchor_bottom_y = anchor_top_left.y() + max(1, anchor_size.height())
            anchor_top_y = anchor_top_left.y()
            anchor_center_x = _map(anchor_widget.rect().center()).x()

            if use_parent_coords:
                avail = parent_widget.rect()
            else:
                try:
                    screen = anchor_widget.screen() or QGuiApplication.screenAt(
                        QPoint(anchor_top_left.x(), anchor_bottom_y)
                    )
                    avail = screen.availableGeometry()
                except Exception:
                    avail = QGuiApplication.primaryScreen().availableGeometry()

            space_below = avail.bottom() - anchor_bottom_y - offset - gap
            space_above = anchor_top_y - avail.top() - offset - gap
            budget = max(space_below, space_above)
            self._update_size(
                match_width=anchor_width,
                exact_match=exact_width_match,
                available_height=budget,
            )
            total_width, total_height = self.width(), self.height()

            if space_below >= total_height or space_below >= space_above:
                final_y = anchor_bottom_y + offset
            else:
                final_y = anchor_top_y - offset - total_height
            final_x = int(anchor_center_x - total_width / 2) + 2

            final_x = max(avail.left(), min(final_x, avail.right() - total_width))
            final_y = max(avail.top(), min(final_y, avail.bottom() - total_height))
            anchor_rect = QRect(anchor_top_left, anchor_size)

        end_pos = QPoint(final_x, final_y)
        final_rect = QRect(end_pos, QSize(total_width, total_height))
        if anchor_rect is None:
            # Overlay path without geometry — fall back to unclamped drop.
            start_pos = QPoint(final_x, final_y - self._drop_offset_px)
        else:
            dx, dy = slide_start_delta(
                final_rect,
                anchor_rect,
                distance=self._drop_offset_px,
                animation_axis="vertical",
                shadow_radius=self.SHADOW_RADIUS,
                ux=0.0,
                uy=1.0,
                length=1.0,
            )
            start_pos = QPoint(final_x + dx, final_y + dy)

        self.move(start_pos)

        # Prefer QWidget.show so BaseFlyout registration / active state stay in
        # sync (request_show already ran above; BaseFlyout.show would re-enter).
        from PySide6.QtWidgets import QWidget as _QWidget

        _QWidget.show(self)
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
        # Never swallow hideEvent: ignoring it after hide() already ran leaves
        # host flags (e.g. _interp_popup_open) desynced because closed is skipped.
        # Open-click races are handled by FlyoutManager anchor hits / host toggle.
        if hasattr(self, "_just_opened"):
            self._just_opened = False

        super().hideEvent(e)

        if self._anim:
            self._anim.stop()
            self._anim = None

        try:
            self.closed.emit()
        except Exception:
            pass
