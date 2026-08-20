from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
    MINIMAL_SCROLLBAR_WIDTH,
    MinimalistScrollBar,
    overlay_scrollbar_max_inset,
    sdbg,
)
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.helpers import (
    calculate_centered_overlay_geometry,
    centered_inner_offset,
    draw_rounded_shadow,
)
from sli_ui_toolkit.ui.widgets.virtual_list import RowPool, visible_window

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.comboboxes.combo_box import ComboBox


class _SlotBgLayer(Layer):
    """Прозрачный фон, list_item.background.hover на hover/pressed.

    ``widget._is_gear_focus`` gives the same hover-look background to
    whichever single row is currently under the gear-shifter's fixed frame
    during a drag (see ComboBox._gear_active / ComboBox._gear_focus_index),
    so that row reads as "this is what gets picked" the same way a normal
    hover does — on top of (not instead of) the stationary outline drawn
    separately by ``_GearFrame``, pinned to the field's own position.
    """

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        states = ctx.effective_states
        return (
            ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
            or widget._is_gear_focus
        )

    def draw(self, ctx, tm: ThemeManager) -> None:
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tm.get_color("list_item.background.hover")))
        p.drawRoundedRect(ctx.rect.toRect().adjusted(0, 1, 0, -1), 6, 6)


class _SlotContentLayer(Layer):
    """Текст слева с TEXT_HORIZONTAL_PADDING, эллипс справа."""

    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        rect = ctx.rect.toRect()
        # Field label pads via scaled_px(TEXT_HORIZONTAL_PADDING) (see
        # _ComboFieldContentLayer.draw) — scale here too, or the two drift
        # apart by a few px at any UiScale factor != 1.0.
        padding = scaled_px(widget._text_padding)
        text_rect = rect.adjusted(padding, 0, -padding, 0)
        p = ctx.painter
        p.setPen(QPen(tm.get_color("dialog.text")))
        font = paint_font(widget)
        p.setFont(font)
        fm = QFontMetrics(font)
        elided = fm.elidedText(widget._text, Qt.TextElideMode.ElideRight, text_rect.width())
        p.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )


class _DropdownItemSlot(Button):
    """Один переиспользуемый «слот» строки в dropdown'е ComboBox'а.

    Виртуальный список держит K = maxVisibleItems слотов; при скролле/фильтре
    каждому слоту переназначается `(item_index, text)`.
    """

    def __init__(self, text_padding: int, parent: QWidget, overlay: "_DropdownOverlay"):
        super().__init__(
            text="",
            size=(0, 0),
            corner_radius=6,
            layers=[_SlotBgLayer(), RippleLayer(), _SlotContentLayer()],
            parent=parent,
        )
        self._text = ""
        self._item_index = -1
        self._text_padding = text_padding
        self._is_gear_focus = False
        self._overlay = overlay

    def bind(self, *, text: str, item_index: int, is_gear_focus: bool = False) -> None:
        self._text = text
        self._item_index = item_index
        self._is_gear_focus = is_gear_focus
        self.update()

    def hoverHitTest(self, pos) -> bool:
        # While the mouse is grabbed for a gear-drag, hover here comes only
        # from HoverCoordinator (see hover_coordinator.py), an app-wide
        # QApplication event filter that reconciles every registered
        # widget's hover on every MouseMove/Enter anywhere in the app via
        # QApplication.widgetAt(real_cursor_pos), calling this method to
        # confirm the hit — Qt itself doesn't deliver native enter/leave to
        # other widgets while a widget holds the implicit grab. During a
        # gear-drag it's the *popup* that physically translates under a
        # stationary (blank-cursor) real pointer, so widgetAt() can
        # legitimately land on a row here — HoverCoordinator would then
        # light it up on top of the gear-focus frame's own highlight, a
        # second highlight the frame doesn't own. Returning False makes
        # _reconcile_widget treat this row as an explicit miss instead.
        if self._overlay._hover_suppressed:
            return False
        return super().hoverHitTest(pos)

    def enterEvent(self, event) -> None:
        # The grab that keeps other widgets from seeing native enter/leave
        # (see hoverHitTest above) ends the moment mouseReleaseEvent
        # returns — well before the drag gesture is actually done: the snap
        # animation and its post-landing hold (GEAR_SNAP_HOLD_MS) still have
        # the gear-focus frame highlighting the committed row, and last for
        # a while after release. If the real cursor happens to sit over a
        # *different* row once the grab lets go, Qt delivers this a genuine
        # native Enter for it, and Button's own base implementation would
        # light it up — a second, unwanted highlight next to the gear-focus
        # one until _hover_suppressed finally clears in GearDragCapability
        # cancel(). Swallow it while suppressed; leaveEvent still runs
        # normally so nothing can get stuck lit.
        if self._overlay._hover_suppressed:
            return
        super().enterEvent(event)


class _GearFrame(QWidget):
    """Outline-only marker drawn on top of the list, pinned to the
    ComboBox field's own screen rect (not a "row within the popup" — the
    field's literal position/size), while a gear-shifter drag is in
    progress (see ComboBox._gear_active). It never moves; whichever row
    happens to be behind it at release time is what gets committed. Reuses
    the field's own border pen (``input.border.thin``, same as
    ``_ComboFieldBgLayer``) rather than an arbitrary accent color.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

    def paintEvent(self, event):
        overlay = self.parentWidget()
        owner = getattr(overlay, "_owner", None)
        tm = overlay._theme if overlay is not None else ThemeManager.get_instance()
        radius = owner.RADIUS if owner is not None else 6
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(tm.get_color("input.border.thin")))
        pen.setWidthF(max(1.0, 2.0 * UiScale.get_instance().factor()))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0), radius, radius)


class _DropdownOverlay(QWidget):
    RADIUS = 8
    SHADOW = 10
    GAP = 6

    def __init__(self, owner: "ComboBox", parent: QWidget):
        if parent is None:
            raise ValueError("_DropdownOverlay requires an in-window parent widget")
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self._owner = owner
        self._theme = owner._theme
        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar_width = MINIMAL_SCROLLBAR_WIDTH
        # Rows are children of this viewport (not of the overlay itself) so
        # Qt clips their painting to the list area — needed during a
        # gear-shifter drag, where rows are positioned at sub-item pixel
        # offsets and can briefly extend a few pixels above/below the list.
        self._list_viewport = QWidget(self)
        self._list_viewport.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._pool = RowPool(self._list_viewport, self._make_slot)
        self._gear_frame = _GearFrame(self)
        # See _DropdownItemSlot.enterEvent — true for the duration of a
        # gear-drag gesture (and a beat past its release), to swallow the
        # native Enter Qt posts to whatever row sits under the cursor once
        # the field's implicit mouse grab lets go.
        self._hover_suppressed = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMouseTracking(True)
        self.custom_v_scrollbar.valueChanged.connect(self._on_scrollbar_value_changed)
        self.custom_v_scrollbar.setVisible(False)
        # True while the overlay is forwarding a scrollbar drag that started on
        # a press it received itself (i.e. the scrollbar got a synthesized
        # press instead of a real one and thus has no mouse grab of its own).
        # While set, every move/release is forwarded to the scrollbar
        # regardless of geometry so the drag tracks the cursor outside the
        # 10px column and the release always resets its internal dragging state.
        self._sb_dragging = False
        self.hide()

    def _item_height(self) -> int:
        return self._owner._item_height()

    def _visible_items(self) -> int:
        return self._owner._visible_items()

    def _visible_item_indices(self) -> list[int]:
        return self._owner._visible_indices()

    def _list_height(self) -> int:
        return self._visible_items() * self._item_height()

    def _content_rect(self) -> QRect:
        return self.rect().adjusted(self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW)

    def _has_scrollbar(self) -> bool:
        return len(self._visible_item_indices()) > self._owner.maxVisibleItems()

    def _list_rect(self) -> QRect:
        width = self._content_rect().width()
        if self._has_scrollbar():
            width -= overlay_scrollbar_max_inset()
        return QRect(0, 0, max(0, width), self._list_height())

    # -------- slot pool management (shared VirtualRowPool) --------

    @property
    def _slots(self) -> list["_DropdownItemSlot"]:
        """Live pooled slot widgets — see virtual_list.RowPool."""
        return self._pool.widgets()

    def _make_slot(self) -> "_DropdownItemSlot":
        slot = _DropdownItemSlot(
            text_padding=self._owner.TEXT_HORIZONTAL_PADDING,
            parent=None,
            overlay=self,
        )
        slot.clicked.connect(lambda s=slot: self._on_slot_clicked(s))
        return slot

    def _bind_slot(self, visible_pos: int, slot: "_DropdownItemSlot") -> None:
        owner = self._owner
        visible_indices = self._visible_item_indices()
        if not (0 <= visible_pos < len(visible_indices)):
            return
        item_index = visible_indices[visible_pos]
        item = owner._items[item_index]
        slot.bind(
            text=item.text,
            item_index=item_index,
            is_gear_focus=owner._gear_active and item_index == owner._gear_focus_index,
        )

    def _position_viewport(self) -> None:
        list_rect = self._list_rect()
        self._list_viewport.setGeometry(list_rect.translated(self._content_rect().topLeft()))

    def _rebind_slots(self) -> None:
        self._position_viewport()
        # Row layout itself never special-cases a drag — see
        # ComboBox._update_gear_drag: in the non-overflow case, the whole
        # popup window (this widget: card + shadow + rows) is what
        # physically translates via self.move(), so card/shadow and rows
        # move together automatically, with zero per-row math. The overflow
        # (more items than fit) case keeps the window static and scrolls
        # via owner._scroll_offset like a normal opened list, same as
        # always — that logic lives entirely in this one method.
        self._rebind_slots_normal()
        self._update_gear_frame()

    def _rebind_slots_normal(self) -> None:
        owner = self._owner
        visible_indices = self._visible_item_indices()
        item_h = self._item_height()
        scroll_px = owner._scroll_offset * item_h
        # The virtual list here is the FILTERED visible-index array: the
        # window spans [scroll_offset, scroll_offset + maxVisibleItems)
        # visible positions, each mapped back to a source item index by the
        # bind callback. visible_window() reproduces that window in px.
        start, end = visible_window(
            len(visible_indices), self._list_height(), item_h, scroll_px, overscan=0
        )
        self._pool.rebind(
            start, end, self._bind_slot,
            row_height=item_h, scroll_offset=scroll_px,
        )

    def _update_gear_frame(self) -> None:
        """Position the fixed outline over the field's real screen rect.

        Computed via global coordinates (not "row N of the popup"), so it
        stays correct regardless of where the popup window currently sits —
        including while that window is being dragged around by
        ComboBox._update_gear_drag.

        Sized to row height, not the field's own (fixed BASE_HEIGHT) height:
        the field height and the dropdown row height are independent
        quantities — row height tracks font metrics, the field doesn't — so
        they rarely match exactly. Framing at the field's height left a
        gap between the frame and whichever row was riding under it, and
        because that gap is usually an odd pixel count it split unevenly
        (e.g. 1px/2px) rather than centering, so the row visibly poked past
        the outline on one edge and sat recessed on the other. Matching the
        frame to row height instead makes it hug the row exactly, at every
        step of the drag, not just at the anchor.
        """
        owner = self._owner
        if not owner._gear_active:
            self._gear_frame.hide()
            return
        item_h = self._item_height()
        field_rect = owner.rect()
        field_top_left_global = owner.mapToGlobal(field_rect.topLeft())
        local_top_left = self.mapFromGlobal(field_top_left_global)
        # centered_inner_offset (not plain // 2): the popup positions the
        # anchored row with this same helper (overlay_geometry), so a
        # different rounding here left the row's top poking a full pixel out
        # of the frame.
        local_top_left.setY(local_top_left.y() + centered_inner_offset(field_rect.height(), item_h))
        frame_rect = QRect(local_top_left, QSize(field_rect.width(), item_h))
        self._gear_frame.setGeometry(frame_rect)
        self._gear_frame.show()
        self._gear_frame.raise_()

    def hover_row_at_global_pos(self, global_pos: QPoint) -> None:
        """Mark whichever visible row sits under ``global_pos`` as hovered.

        Used when the list opens via a long-press-only gesture (see
        ``GearDragCapability._begin_drag``'s overflow branch): the popup
        appears without the mouse having moved into it, so Qt never fires
        the row's own ``enterEvent`` — without this the just-opened list
        would show no hover at all until the user physically moves the
        mouse.
        """
        local = self._list_viewport.mapFromGlobal(global_pos)
        for slot in self._slots:
            if not slot.isVisible():
                continue
            slot._hovered = slot.geometry().contains(local)

    def clear_hover(self) -> None:
        """Drop hover state on every slot (used, incl. hidden, ones).

        ``hover_row_at_global_pos`` forces ``_hovered`` on directly rather
        than through Qt's own enter/leave tracking, and slots are a reused
        pool — without an explicit clear on close, a row hidden while still
        force-hovered would show that stale hover the next time it's rebound
        to a different item.
        """
        for slot in self._slots:
            slot._hovered = False

    def slot_for_index(self, index: int):
        """Visible dropdown row widget for ``index``, or ``None``."""
        for slot in self._slots:
            if slot.isVisible() and slot._item_index == index:
                return slot
        return None

    def _on_slot_clicked(self, slot: _DropdownItemSlot) -> None:
        idx = slot._item_index
        if idx >= 0:
            self._owner.setCurrentIndex(idx)
        self._owner.hideDropdown()

    # -------- show/position --------

    def show_for_owner(self):
        self._owner._ensure_current_visible()
        self._reposition()
        self._sync_scrollbar()
        self._rebind_slots()
        self.show()
        self.raise_()
        self.update()

    def _reposition(self):
        owner = self._owner
        window = self.parentWidget()
        if window is None:
            return

        # Same selection-centered geometry as a normal click so the list stays
        # aligned with the field. Find Action only changes which row gets the
        # accent wash (``_focus_row``), not where the popup is parked.
        anchor_index = owner.currentIndex()
        outer = calculate_centered_overlay_geometry(
            anchor_widget=owner,
            owner_window=window,
            content_size=QSize(
                max(owner.width(), owner.minimumWidth()), self._list_height()
            ),
            shadow_radius=self.SHADOW,
            current_index=anchor_index,
            visible_index=max(
                0,
                owner._visible_position_for_index(anchor_index) - owner._scroll_offset,
            ),
            row_height=self._item_height(),
            scrollable=len(self._visible_item_indices()) > owner.maxVisibleItems(),
        )
        self.setGeometry(outer)
        self._position_scrollbar()

    def _position_scrollbar(self):
        content = self._content_rect()
        if not self._has_scrollbar():
            self.custom_v_scrollbar.setVisible(False)
            return
        x = content.right() - self._scrollbar_width + 1
        self.custom_v_scrollbar.setGeometry(
            x,
            content.y(),
            self._scrollbar_width,
            content.height(),
        )
        self.custom_v_scrollbar.raise_()

    def _sync_scrollbar(self):
        max_offset = max(0, len(self._visible_item_indices()) - self._visible_items())
        if max_offset <= 0:
            self.custom_v_scrollbar.setVisible(False)
            return
        self.custom_v_scrollbar.blockSignals(True)
        self.custom_v_scrollbar.setRange(0, max_offset)
        self.custom_v_scrollbar.setPageStep(self._visible_items())
        self.custom_v_scrollbar.setSingleStep(1)
        self.custom_v_scrollbar.setValue(self._owner._scroll_offset)
        self.custom_v_scrollbar.blockSignals(False)
        self.custom_v_scrollbar.setVisible(True)
        self._position_scrollbar()

    def _on_scrollbar_value_changed(self, value: int):
        new_offset = max(0, min(int(value), max(0, len(self._visible_item_indices()) - self._visible_items())))
        if new_offset == self._owner._scroll_offset:
            return
        self._owner._scroll_offset = new_offset
        self._rebind_slots()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_viewport()
        self._position_scrollbar()
        self._sync_scrollbar()

    def update(self):
        # ComboBox дёргает overlay.update() при изменении items/scroll/search →
        # пересвязываем слоты, чтобы текст и индексы соответствовали текущему окну.
        super().update()
        if self.isVisible():
            self._rebind_slots()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        content = QRectF(self._content_rect())
        draw_rounded_shadow(painter, content, steps=self.SHADOW, radius=self.RADIUS)

        bg = self._theme.get_color("flyout.background")
        border = self._theme.get_color("flyout.border")

        path = QPainterPath()
        path.addRoundedRect(content.adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)
        painter.setPen(QPen(border))
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)
        painter.end()
        # Сами строки отрисовывают child-Button-слоты.

    # -------- scrollbar pass-through --------

    def _forward_to_scrollbar(self, event: QMouseEvent) -> bool:
        sb = self.custom_v_scrollbar
        sb_geo = sb.geometry()
        event_pos = event.position().toPoint()
        hit = sb.isVisible() and (self._sb_dragging or sb_geo.contains(event_pos))
        sdbg(
            f"forward {'yes' if hit else 'NO'} evt={int(event.type())} "
            f"overlay_pos={event_pos} overlay_rect={self.rect()} "
            f"sb_visible={sb.isVisible()} sb_geo={sb_geo} sb_dragging={self._sb_dragging}"
        )
        if not hit:
            return False
        scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(event.globalPosition().toPoint())
        QApplication.sendEvent(
            self.custom_v_scrollbar,
            QMouseEvent(
                event.type(),
                QPointF(scrollbar_pos),
                event.globalPosition(),
                event.button(),
                event.buttons(),
                event.modifiers(),
            ),
        )
        event.accept()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._forward_to_scrollbar(event):
                self._sb_dragging = True
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._sb_dragging:
            if self._forward_to_scrollbar(event):
                return
            # Drag in progress but the cursor left the overlay window: keep
            # forwarding while the button is held so the thumb keeps tracking.
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._forward_to_scrollbar(event)
            return
        if self._forward_to_scrollbar(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._sb_dragging:
            self._forward_to_scrollbar(event)
            self._sb_dragging = False
            return
        if event.button() == Qt.MouseButton.LeftButton and self._forward_to_scrollbar(event):
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        visible_count = len(self._visible_item_indices())
        if visible_count <= self._owner._max_visible_items:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._owner._scroll_offset = max(0, self._owner._scroll_offset - 1)
        elif delta < 0:
            self._owner._scroll_offset = min(
                visible_count - self._owner._max_visible_items,
                self._owner._scroll_offset + 1,
            )
        self._sync_scrollbar()
        self._rebind_slots()
        super().update()
        event.accept()
