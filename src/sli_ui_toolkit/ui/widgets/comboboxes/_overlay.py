from __future__ import annotations

from typing import TYPE_CHECKING, cast

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
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.ui.widgets.helpers import calculate_centered_overlay_geometry
from sli_ui_toolkit.ui.widgets.virtual_list import RowPool, visible_window

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.comboboxes.combo_box import ComboBox


#: Text this module itself wrote as a tooltip. Kept on the widget so a tooltip
#: set by the HOST is never mistaken for an automatic one (see
#: ``apply_elided_tooltip``); shared by the dropdown rows and the ComboBox
#: field because both follow the same rule.
_AUTO_TOOLTIP_ATTR = "_auto_elided_tooltip"


def apply_elided_tooltip(widget: QWidget, text: str, available_width: int) -> None:
    """Give ``widget`` ``text`` as a tooltip iff its painted label elides.

    The caller passes the same ``text``, font (``paint_font``) and text-rect
    width its paint layer uses, so the tooltip appears exactly when an
    ellipsis does and is cleared as soon as the whole text fits again — a
    short label must behave exactly as before.

    Explicit wins: a tooltip this helper did not write (the host's own, e.g.
    ``combo.setToolTip(...)``) is left untouched in both directions. Never
    raises — a zero/negative width simply clears the automatic tooltip.
    """
    written = getattr(widget, _AUTO_TOOLTIP_ATTR, "")
    current = widget.toolTip()
    if current and current != written:
        return
    desired = ""
    if text and available_width > 0:
        fm = QFontMetrics(paint_font(widget))
        if fm.elidedText(text, Qt.TextElideMode.ElideRight, available_width) != text:
            desired = text
    if current != desired:
        widget.setToolTip(desired)
    setattr(widget, _AUTO_TOOLTIP_ATTR, desired)


class _SlotBgLayer(Layer):
    """Прозрачный фон, list_item.background.hover на hover/pressed.

    ``widget._is_focus_row`` gives the same hover-look background to the one
    row a commit would take when the row is not natively hovered: the row
    under the pointer during a press-and-release selection
    (``ComboBox._pointer_select_index`` — the field holds the implicit grab,
    so the rows never see those moves themselves), or the row the keyboard
    typeahead currently walks (``_typing_focus_index``). That row reads as
    "this is what gets picked" the same way a normal hover does.
    """

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        states = ctx.effective_states
        return (
            ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
            or widget._is_focus_row
        )

    def draw(self, ctx, tm: ThemeManager) -> None:
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tm.get_color("list_item.background.hover")))
        p.drawRoundedRect(ctx.rect.toRect().adjusted(0, 1, 0, -1), 6, 6)


class _CurrentIndexRingLayer(Layer):
    """Ring on the row a keyboard commit would take while the dropdown is open.

    That is the typeahead highlight while a jump query is active (it can point
    at a row that is NOT ``currentIndex`` — typing only walks the list, Enter
    commits it), otherwise the row matching ``owner.currentIndex()`` — the
    keyboard-navigable "this is what Enter picks" indicator.

    Not ``FocusLayer``: that layer gates on real Qt ``hasFocus()``, which
    this popup never grants to a row (the field keeps keyboard focus so
    typeahead/search keep working — see
    docs/legacy/plan_combobox_baseflyout_unification.md §2.4 Option A).
    This is the same visual (ring geometry/color) driven off the combo's own
    current-index state instead, and yields to the pointer's own highlight
    (``_SlotBgLayer``) while a press-and-release selection is in progress.

    Gated on ``owner._keyboard_focus`` (set by ``Button.focusInEvent`` —
    True for Tab/arrow-granted focus, False for a mouse click), same
    convention as every other flyout's own focus ring: a mouse-opened
    dropdown must not flash a ring any more than a mouse-opened
    ``BaseFlyout`` does (``BaseFlyout._grab_focus``'s ``anchor_kbd``).
    """

    def applies(self, ctx) -> bool:
        widget = ctx.widget
        owner = widget._overlay._owner
        if not owner._expanded or owner._pointer_select_armed:
            return False
        typing_index = owner._typing_focus_index
        if typing_index >= 0:
            # Typing is keyboard input even when the list was opened by mouse
            # (``_keyboard_focus`` is False then) — the walked row must be
            # visible or the jump looks like nothing happened.
            return widget._item_index == typing_index
        return (
            bool(getattr(owner, "_keyboard_focus", False))
            and widget._item_index == owner.currentIndex()
        )

    def draw(self, ctx, tm: ThemeManager) -> None:
        factor = UiScale.get_instance().factor()
        radius = max(0, ctx.corner_radius)
        design_radius = radius / factor if factor > 0 else radius

        rect = ctx.rect
        if hasattr(rect, "toAlignedRect"):
            rect = rect.toAlignedRect()

        thickness = max(1.0, 2.0 * factor)
        inset = thickness * 0.5
        ring = QRectF(rect).adjusted(inset, inset, -inset, -inset)
        if ring.width() <= 0 or ring.height() <= 0:
            return

        path = QPainterPath()
        path.addRoundedRect(ring, design_radius, design_radius)

        color = QColor(tm.get_color("accent"))
        color.setAlpha(220)

        p = ctx.painter
        p.save()
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(color)
            pen.setWidthF(thickness)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        finally:
            p.restore()


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

    def __init__(self, text_padding: int, parent: QWidget | None, overlay: "_DropdownOverlay"):
        super().__init__(
            text="",
            size=(0, 0),
            corner_radius=6,
            layers=[_SlotBgLayer(), RippleLayer(), _SlotContentLayer(), _CurrentIndexRingLayer()],
            parent=parent,
        )
        self._text = ""
        self._item_index = -1
        self._text_padding = text_padding
        self._is_focus_row = False
        self._overlay = overlay

    def bind(self, *, text: str, item_index: int, is_focus_row: bool = False) -> None:
        self._text = text
        self._item_index = item_index
        self._is_focus_row = is_focus_row
        self._sync_elided_tooltip()
        self.update()

    def _sync_elided_tooltip(self) -> None:
        """Row tooltip = the item's full text while the painted label elides.

        Same font and text rect as ``_SlotContentLayer.draw`` — the tooltip
        must appear exactly when that layer draws an ellipsis. Borders the
        pooled-slot staleness case: a slot rebound from a long item to a
        short one clears the tooltip (``apply_elided_tooltip`` tracks what it
        wrote itself).
        """
        available = self.width() - 2 * scaled_px(self._text_padding)
        apply_elided_tooltip(self, self._text, available)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # A press on a row arms the same press-and-release selection the field
        # arms on open; nothing is committed until the release lands on a row
        # (see ComboBox._finish_pointer_selection).
        if event.button() == Qt.MouseButton.LeftButton:
            self._overlay._owner._begin_pointer_selection(from_field=False)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._overlay._owner._update_pointer_selection(
                event.globalPosition().toPoint()
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._overlay._owner._commit_pointer_selection(
                event.globalPosition().toPoint()
            )
        super().mouseReleaseEvent(event)


class _DropdownOverlay(BaseFlyout):

    def __init__(self, owner: "ComboBox", parent: QWidget):
        super().__init__(parent)
        #: Named after its OWNER so a live probe (or a layout dump) can address one card: every combo carries an overlay
        #: with no Designer name, and `findChild` by a shared name returns whichever was built first - the backend combo's
        #: hidden card answered a question about the model combo's popup (measured live 2026-11-24).
        owner_name = owner.objectName() if owner is not None else ""
        self.setObjectName(f"{owner_name}Overlay" if owner_name else "ComboBoxOverlay")
        self._owner = owner
        self._theme = owner._theme
        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar_width = MINIMAL_SCROLLBAR_WIDTH
        # Rows are children of self.container (BaseFlyout's shadow-clipped
        # surface), not of the overlay itself, so Qt clips their painting to
        # the list area.
        self._list_viewport = QWidget(self.container)
        self._list_viewport.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._pool = RowPool(self._list_viewport, self._make_slot)
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
        # Whether the field held focus from a user gesture (Tab/Enter), not
        # from the pointer press that opens the list. The popup never grabs
        # focus (see ``show_for_owner``), so a close must not hand the field a
        # focus the gesture did not ask for — see ``_restore_focus_policies``.
        self._field_focus_was_deliberate = True

    def _item_height(self) -> int:
        return self._owner._item_height()

    def _visible_items(self) -> int:
        return self._owner._visible_items()

    def _visible_item_indices(self) -> list[int]:
        return self._owner._visible_indices()

    def _list_height(self) -> int:
        return self._visible_items() * self._item_height()

    def _content_rect(self) -> QRect:
        return self.container.geometry()

    def _has_scrollbar(self) -> bool:
        # Overflow is exactly "a scroll offset exists", from the one formula
        # the bar/wheel/mutators share (combo_box._max_scroll_offset).
        return self._owner._max_scroll_offset() > 0

    def _list_rect(self) -> QRect:
        width = self._content_rect().width()
        if self._has_scrollbar():
            width -= overlay_scrollbar_max_inset()
        return QRect(0, 0, max(0, width), self._list_height())

    # -------- slot pool management (shared VirtualRowPool) --------

    @property
    def _slots(self) -> list["_DropdownItemSlot"]:
        """Live pooled slot widgets — see virtual_list.RowPool."""
        return cast("list[_DropdownItemSlot]", self._pool.widgets())

    def _make_slot(self) -> "_DropdownItemSlot":
        slot = _DropdownItemSlot(
            text_padding=self._owner.TEXT_HORIZONTAL_PADDING,
            parent=None,
            overlay=self,
        )
        slot.clicked.connect(lambda s=slot: self._on_slot_clicked(s))
        return slot

    def _bind_slot(self, visible_pos: int, slot: QWidget) -> None:
        item_slot = cast(_DropdownItemSlot, slot)
        owner = self._owner
        visible_indices = self._visible_item_indices()
        if not (0 <= visible_pos < len(visible_indices)):
            return
        item_index = visible_indices[visible_pos]
        item = owner._items[item_index]
        item_slot.bind(
            text=item.text,
            item_index=item_index,
            is_focus_row=owner._focus_row_index >= 0 and item_index == owner._focus_row_index,
        )

    def _position_viewport(self) -> None:
        # _list_viewport is a child of self.container now (not of self), so
        # its geometry is already container-local — no translate needed.
        self._list_viewport.setGeometry(self._list_rect())

    def refresh_geometry(self) -> None:
        """Re-derive the open popup from the live row count and row height.

        ``_list_height()`` is the popup's content height (visible rows × row
        height), and the card, viewport, row pitch and scrollbar must all move
        with it. Opening is the only path that used to derive them, so a
        filter that narrows the rows (``typing_mode="filter"``), an item
        mutation or a font/scale change while the list is open left the card
        at its open-time size while those consumers read the new numbers.
        ``ComboBox._refresh_open_overlay`` is the single caller-side gate.

        The scroll offset is clamped first: a list that just got shorter (or
        a window that shows more rows) must not keep a row position past its
        last row.
        """
        owner = self._owner
        owner._scroll_offset = min(owner._scroll_offset, owner._max_scroll_offset())
        self._reposition()
        self._sync_scrollbar()
        self._rebind_slots()

    def _rebind_slots(self) -> None:
        self._position_viewport()
        self._rebind_slots_normal()

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
        # Rebinding runs BEFORE the pool assigns each row its geometry, so a
        # freshly created (0 px wide) slot or one resized by this pass would
        # decide its tooltip from a stale width. Re-evaluate once every row
        # in the window has its final size.
        for slot in self._slots:
            if slot.isVisible():
                slot._sync_elided_tooltip()

    def row_index_at_global_pos(self, global_pos: QPoint) -> int:
        """Item index of the visible row under a screen point, or -1.

        The pointer's own position is the only input: a press-and-release
        selection hit-tests real row geometry (see
        ``ComboBox._update_pointer_selection``), so no synthetic
        ``QApplication.widgetAt`` reconciliation is needed to know which row a
        release would pick.
        """
        local = self._list_viewport.mapFromGlobal(global_pos)
        for slot in self._slots:
            if not slot.isVisible():
                continue
            if slot.geometry().contains(local):
                return slot._item_index
        return -1

    def clear_hover(self) -> None:
        """Drop native hover state on every slot (used, incl. hidden, ones).

        Slots are a reused pool: a row hidden while still hovered must not show
        that stale hover the next time it is rebound to a different item.
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
        # A click is an explicit choice: the typing session ends with it.
        self._owner._reset_typeahead()
        self._owner.hideDropdown()

    # -------- show/position --------

    def show_for_owner(self):
        # The popup is field-centric: it never grabs Qt focus (see below), so
        # it must not grant focus on close either. Record whether the field
        # held focus from a real gesture — a keyboard-opened list (Tab, Enter)
        # keeps it after closing; a pointer-opened one must give back whatever
        # had focus before the opening press. ``hasFocus()`` alone is not that
        # signal: Qt's click-focus policy focuses the field from a real press
        # before the widget sees it (owner report 2026-11-24, second round:
        # open, pick a row, the wheel stepped the committed value).
        # See tests/test_combo_popup_wheel_policy.py.
        self._field_focus_was_deliberate = self._owner._deliberately_focused()
        # An OPEN centres the target row under the field (the popup is
        # centred on the field, so the middle window row is the one the user
        # reads as "current"); later scrolling only keeps rows in view.
        self._owner._center_current_visible()
        self._anchor_widget = self._owner
        # Field-centric focus model (see
        # docs/legacy/plan_combobox_baseflyout_unification.md §2.4 Option A):
        # real Qt focus stays on the ComboBox field so typeahead/search keep
        # working. Nav-section registration is Phase 2 (still local
        # keyPressEvent-driven Up/Down for now).
        self._skip_focus_grab = True
        self._skip_nav_register = True
        self._reposition()
        self._sync_scrollbar()
        self._rebind_slots()
        self.show()
        self.raise_()
        self.update()

    def _restore_focus_policies(self) -> None:
        """Keep the pre-open focus situation; never grant the field focus.

        ``BaseFlyout`` restores focus to the anchor (the explicit trigger) so
        keyboard navigation continues where it was. For the dropdown that is
        wrong when the user did not focus the field: the anchor restore then
        hands it Qt focus, which ``WheelScrollPolicyMixin`` reads as "the user
        deliberately focused this control" and the wheel starts stepping the
        combo (owner report 2026-11-24).

        Two cases keep the field focused:
        - it held focus from a real gesture when the list opened (Tab/Enter);
        - the list was driven by the keyboard since (a row committed with
          Enter after a pointer-opened list — the user is on the keyboard now).

        Everything else is a pointer-driven cycle and must leave focus exactly
        where the opening gesture found it: the field's own ``focus_before_grant``
        widget, or nothing. The field itself is never a valid target — the
        opening press may have focused it, which is the grant this fixes.
        """
        owner = self._owner
        if self._field_focus_was_deliberate or (
            owner.hasFocus() and getattr(owner, "_list_driven_by_keyboard", False)
        ):
            super()._restore_focus_policies()
            return
        anchor = getattr(self, "_anchor_widget", None)
        prev = getattr(self, "_previous_focus_widget", None)
        if prev is owner:
            # show() captured the field because the opening press had already
            # focused it (Qt's click-focus policy, see ComboBox.
            # _on_app_focus_changed); the real pre-gesture widget is the one
            # the field took that focus from.
            prev = getattr(owner, "_focus_before_grant", None)
        # BaseFlyout prefers the anchor over ``_previous_focus_widget``; with
        # the anchor withdrawn it restores ``prev`` (or nothing, when nothing
        # had focus before the gesture).
        self._anchor_widget = None
        self._previous_focus_widget = prev
        try:
            super()._restore_focus_policies()
        finally:
            self._anchor_widget = anchor
        # A row's own press focuses it (StrongFocus + Qt's click policy). When
        # no pre-gesture widget could be restored, that row is still focused
        # until the tree is hidden — and hiding the focused widget makes Qt
        # walk the focus chain, which can land on the field and grant the wheel
        # after all. Drop the in-popup focus explicitly instead.
        current = QApplication.focusWidget()
        if current is not None and (current is self or self.isAncestorOf(current)):
            current.clearFocus()

    def _reposition(self):
        owner = self._owner
        window = self.parentWidget()
        if window is None:
            return

        # Same selection-centered geometry as a normal click so the list stays
        # aligned with the field. Find Action only changes which row gets the
        # accent wash (``_focus_row``), not where the popup is parked.
        # Deliberately not routed through BaseFlyout.show_aligned — no
        # existing anchor-point mode centers content on a specific row (see
        # plan §2.3 Option A); this stays a local override calling
        # setGeometry directly.
        # The row the scroll targeted (a Find Action reveal may point at a row
        # that is not ``currentIndex``) — the popup must park on THAT row.
        anchor_index = owner._focus_or_current_index()
        outer = calculate_centered_overlay_geometry(
            anchor_widget=owner,
            owner_window=window,
            content_size=QSize(
                max(owner.width(), owner.minimumWidth()), self._list_height()
            ),
            shadow_radius=self.SHADOW_RADIUS,
            current_index=anchor_index,
            visible_index=max(
                0,
                owner._visible_position_for_index(anchor_index) - owner._scroll_offset,
            ),
            row_height=self._item_height(),
            scrollable=self._has_scrollbar(),
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
        max_offset = self._owner._max_scroll_offset()
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
        new_offset = max(0, min(int(value), self._owner._max_scroll_offset()))
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

    # paintEvent: inherited from BaseFlyout's _FlyoutStyleApi — shadow +
    # rounded-rect fill/border on self.container.geometry(), same tokens
    # this class used to paint by hand. Rows paint themselves via child
    # Button slots.

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
        owner = self._owner
        if owner._pointer_select_armed and event.buttons() & Qt.MouseButton.LeftButton:
            # The press started on the field or on a row: whichever widget holds
            # the implicit grab forwards the pointer's own travel here, and the
            # row under it is re-derived from real geometry (no cursor warping,
            # no widgetAt reconciliation).
            owner._update_pointer_selection(event.globalPosition().toPoint())
            event.accept()
            return
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
        owner = self._owner
        if event.button() == Qt.MouseButton.LeftButton and owner._pointer_select_armed:
            owner._commit_pointer_selection(event.globalPosition().toPoint())
            event.accept()
            return
        if self._sb_dragging:
            self._forward_to_scrollbar(event)
            self._sb_dragging = False
            return
        if event.button() == Qt.MouseButton.LeftButton and self._forward_to_scrollbar(event):
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        max_offset = self._owner._max_scroll_offset()
        if max_offset <= 0:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._owner._scroll_offset = max(0, self._owner._scroll_offset - 1)
        elif delta < 0:
            self._owner._scroll_offset = min(
                max_offset,
                self._owner._scroll_offset + 1,
            )
        self._sync_scrollbar()
        self._rebind_slots()
        super().update()
        event.accept()
