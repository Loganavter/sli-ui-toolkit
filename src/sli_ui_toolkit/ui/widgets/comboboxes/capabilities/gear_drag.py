from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.widgets.buttons.capabilities import ButtonCapability
from sli_ui_toolkit.ui.widgets.helpers.hover_coordinator import hover_coordinator

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.comboboxes.combo_box import ComboBox


@dataclass(frozen=True)
class _GearReleaseOutcome:
    suppress_click: bool


class GearDragCapability(ButtonCapability):
    """"Gear-shifter" drag-select: hold the field for ``hold_ms``, or drag it
    sideways/vertically past ``drag_threshold_px`` right after pressing, to
    open the dropdown and scrub through rows by dragging — like sliding a
    gearbox knob into its slot. Releasing commits whichever row is under the
    field at that moment, immediately; a plain click/release still just
    toggles the list.
    """

    def __init__(
        self,
        *,
        hold_ms: int,
        drag_threshold_px: int,
    ) -> None:
        super().__init__()
        self.hold_ms = hold_ms
        self.drag_threshold_px = drag_threshold_px

        self._combo: "ComboBox | None" = None
        self._press_pos: QPointF | None = None
        # Global (screen) coordinates of the press that armed this gesture,
        # kept for the gesture's full lifetime (unlike _press_pos, which
        # handle_release clears immediately) so _restore_cursor can warp the
        # real cursor back there once the drag ends — otherwise it reappears
        # wherever the physically-unclamped mouse travel happened to leave
        # it, which can be arbitrarily far from the field.
        self._press_global_pos: QPoint | None = None
        self._anchor_index: int = -1
        self._anchor_visible_pos: int = 0
        self.active: bool = False
        self.focus_index: int = -1
        self._started_by_long_press: bool = False
        # True when a long-press or threshold-drag gesture landed on an
        # overflow list (see _begin_drag) and was downgraded to "just open
        # the list" instead of arming real gear-drag mode — read by
        # handle_release to suppress the click that same press/release would
        # otherwise fire and immediately close what it just opened.
        self._overflow_open_only: bool = False
        # Popup window's on-screen position when the drag started. In the
        # non-overflow case we physically translate the whole popup by the
        # (clamped) drag distance each move — card, shadow, and rows all move
        # together because they're one widget — rather than repositioning
        # rows within a static window.
        self._window_origin: QPoint | None = None
        # True while an override cursor (blank) is pushed for the duration
        # of an active gear-drag gesture — paired set/restore calls around
        # _begin_drag's active branch and _commit_selection so the real
        # cursor doesn't sit on top of the row scrubbing under the finger.
        self._cursor_hidden: bool = False

    # -------- ButtonCapability protocol --------

    def attach(self, button, region_id: str | None = None) -> None:
        super().attach(button, region_id=region_id)
        self._combo = button
        self._combo.longPressed.connect(self._on_long_pressed)

    def detach(self, button) -> None:
        self._restore_cursor()
        if self._combo is not None and self._combo._overlay is not None:
            self._combo._overlay._hover_suppressed = False
        self._combo = None

    def is_enabled(self) -> bool:
        return self._combo is not None and self._combo.isEnabled()

    # -------- mouse dispatch (called explicitly from ComboBox) --------

    def handle_press(self, event: QMouseEvent) -> None:
        combo = self._combo
        # Only ever called while attached (between ComboBox.__init__'s
        # attach_capability() and detach()) — see attach()/detach() below.
        assert combo is not None
        if (
            event.button() == Qt.MouseButton.LeftButton
            and combo.isEnabled()
            and combo.count() > 0
            # Only arm on genuine, OS-delivered input (spontaneous() is
            # False for anything constructed and injected in-process, e.g.
            # QApplication.sendEvent/postEvent) — an external tool or other
            # in-app code driving synthetic mouse events at this widget
            # can't trigger the drag gesture, only a real press-and-hold or
            # press-and-drag from the user can.
            and event.spontaneous()
        ):
            self._press_pos = event.position()
            self._press_global_pos = event.globalPosition().toPoint()
            self._anchor_index = combo.currentIndex()
            self.active = False
            self._started_by_long_press = False
            self._overflow_open_only = False
        else:
            self._press_pos = None
            self._press_global_pos = None
            self.active = False
            self._overflow_open_only = False

    def handle_move(self, event: QMouseEvent) -> bool:
        if self._press_pos is not None and not self.active:
            delta = event.position() - self._press_pos
            if (
                abs(delta.x()) >= self.drag_threshold_px
                or abs(delta.y()) >= self.drag_threshold_px
            ):
                self._begin_drag()
        if self.active:
            self._update_drag(event.position())
            return True
        return False

    def handle_release(self, event: QMouseEvent) -> "_GearReleaseOutcome | None":
        if event.button() == Qt.MouseButton.LeftButton and self.active:
            self._press_pos = None
            # Drag started by crossing the move threshold (no long-press):
            # ComboBox's release handler doesn't know a drag happened, so
            # tell it to skip the click it would otherwise fire. If the
            # release lands outside the field (the common case for a real
            # drag), Button's own same-target check already skips the click
            # and never consumes this flag — ComboBox clears it after so it
            # can't leak into whatever gets clicked next.
            suppress = not self._started_by_long_press
            self._finish_drag()
            return _GearReleaseOutcome(suppress_click=suppress)
        if event.button() == Qt.MouseButton.LeftButton and self._overflow_open_only:
            # The list was already opened (without arming gear-drag) when
            # this gesture crossed into overflow territory in _begin_drag.
            # Unlike the real gear-drag path, this one was never a genuine
            # long-press, so LongPressCapability never marks it and won't
            # suppress the click on its own — do it ourselves, otherwise
            # Button emits ``clicked`` on release and _on_field_clicked
            # immediately closes the list we just opened.
            self._overflow_open_only = False
            return _GearReleaseOutcome(suppress_click=True)
        self._press_pos = None
        self.active = False
        return None

    # -------- gesture internals --------

    def _on_long_pressed(self) -> None:
        if self._press_pos is not None and not self.active:
            # Button's own LongPressCapability already marks this press as
            # long-pressed, which makes its mouseReleaseEvent skip emitting
            # ``clicked`` on its own — no extra suppression needed from us.
            self._started_by_long_press = True
            self._begin_drag()

    def _begin_drag(self) -> None:
        combo = self._combo
        # Only ever called while attached (between ComboBox.__init__'s
        # attach_capability() and detach()) — see attach()/detach() below.
        assert combo is not None
        if combo.count() == 0 or self._press_pos is None:
            return
        visible = combo._visible_indices()
        if not visible:
            return
        if len(visible) > combo._max_visible_items:
            # Same "overflow" criterion _update_drag itself uses: with more
            # rows than fit, the popup window stays put and only its
            # internal scroll offset moves (see the `overflow` branch there)
            # — it never gets the "physically drag the window to the exact
            # row" treatment gear-drag is built around, whether this gesture
            # started from a long-press or from dragging past the move
            # threshold. Just open the list like a normal click instead of
            # arming gear-drag mode. Clearing _press_pos here (rather than in
            # handle_release) also stops handle_move from calling back in on
            # every subsequent move past the threshold. handle_release still
            # needs to explicitly suppress the click this same
            # press/release would otherwise fire — unlike the real gear-drag
            # path, a plain threshold-drag never triggers LongPressCapability,
            # so there's no built-in suppression to lean on here.
            self._overflow_open_only = True
            if not combo._expanded:
                combo.showDropdown()
            if combo._overlay is not None:
                combo._overlay.hover_row_at_global_pos(QCursor.pos())
            self._press_pos = None
            return
        self.active = True
        if not self._cursor_hidden:
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
            self._cursor_hidden = True
            # The real cursor keeps moving under that blanked icon and can
            # cross other controls while the popup is being dragged — without
            # this they'd light up hover as if the user were pointing at them
            # normally. See HoverCoordinator.suppress_all.
            hover_coordinator().suppress_all(True)
        self._anchor_index = combo._current_index
        self.focus_index = combo._current_index
        try:
            self._anchor_visible_pos = visible.index(self._anchor_index)
        except ValueError:
            self._anchor_visible_pos = 0
        if not combo._expanded:
            # Must run before the _hover_suppressed assignment below: on a
            # combo's first-ever open, ``combo._overlay`` is still None until
            # showDropdown() lazily constructs it — checking "is overlay set"
            # before this call meant the flag never got applied on that first
            # drag, silently leaving hover unsuppressed for its entire
            # lifetime.
            combo.showDropdown(focus_index=self._anchor_index)
        if combo._overlay is not None:
            # See _DropdownItemSlot.hoverHitTest — the real cursor keeps
            # moving throughout the drag (only its icon is hidden), and
            # HoverCoordinator polls QApplication.widgetAt() on every such
            # move app-wide, so it can land native hover on whichever row
            # the physically-translating popup now happens to sit under.
            # Released only once the gesture fully ends (cancel(), reached via
            # _commit_selection -> hideDropdown), so it also covers whatever
            # native Enter Qt posts right after the mouse grab lets go.
            combo._overlay._hover_suppressed = True
        # _reposition() (run by showDropdown, or whenever the popup was last
        # opened/repositioned) already places the anchor item's row aligned
        # with the field — that's the geometry helper's normal, non-drag
        # behavior for a selection-centered popup. Recording the popup's
        # position *here* as the drag's zero point means we can just
        # translate it by the raw drag distance from now on.
        self._window_origin = combo._overlay.pos() if combo._overlay is not None else None
        if combo._overlay is not None:
            combo._overlay.update()
        combo.update()

    def _update_drag(self, pos: QPointF) -> None:
        combo = self._combo
        # Only ever called while attached (between ComboBox.__init__'s
        # attach_capability() and detach()) — see attach()/detach() below.
        assert combo is not None
        if self._press_pos is None:
            return
        item_h = combo._item_height()
        if item_h <= 0:
            return
        visible = combo._visible_indices()
        if not visible:
            return
        delta_y = pos.y() - self._press_pos.y()
        overflow = len(visible) > combo._max_visible_items
        if overflow:
            # Overflow: more rows than fit, so the popup isn't anchored to
            # the current row (see _reposition's `scrollable` branch) —
            # dragging the window wouldn't track the field either. Fall back
            # to whole-row scrolling, same as browsing a normally opened
            # list; the window itself stays put.
            steps = round(delta_y / item_h)
            new_pos = max(0, min(len(visible) - 1, self._anchor_visible_pos - steps))
            new_index = visible[new_pos]
            focus_changed = new_index != self.focus_index
            if focus_changed:
                self.focus_index = new_index
                combo._ensure_index_visible(new_index)
            if combo._overlay is not None:
                combo._overlay._sync_scrollbar()
                combo._overlay.update()
        else:
            # Physically drag the whole popup window (card + shadow + rows,
            # all one widget) by the raw pixel distance — clamped so the
            # field's fixed outline can't be dragged past the first/last
            # item — instead of repositioning rows within a static window.
            # Card/shadow and cells therefore always move together, because
            # they're the same object; no separate per-row math needed.
            max_drag_down = self._anchor_visible_pos * item_h
            max_drag_up = (len(visible) - 1 - self._anchor_visible_pos) * item_h
            delta_y_clamped = max(-max_drag_up, min(max_drag_down, delta_y))
            steps = round(delta_y_clamped / item_h)
            new_pos = max(0, min(len(visible) - 1, self._anchor_visible_pos - steps))
            new_index = visible[new_pos]
            focus_changed = new_index != self.focus_index
            self.focus_index = new_index
            if combo._overlay is not None and self._window_origin is not None:
                combo._overlay.move(
                    self._window_origin.x(),
                    self._window_origin.y() + round(delta_y_clamped),
                )
                combo._overlay._update_gear_frame()
                if focus_changed:
                    # Re-bind slots so the row now nearest the fixed
                    # selection frame picks up the hover highlight
                    # (_SlotBgLayer keys off owner._gear_focus_index) — the
                    # window move above repositions the card but doesn't by
                    # itself refresh which row is bound as hovered.
                    combo._overlay.update()
        combo.update()

    def _finish_drag(self) -> None:
        combo = self._combo
        # Only ever called while attached (between ComboBox.__init__'s
        # attach_capability() and detach()) — see attach()/detach() below.
        assert combo is not None
        final_index = self.focus_index
        overlay = combo._overlay
        if overlay is not None:
            # Belt-and-suspenders eager clear. The real fix for the "two
            # highlights at once" bug is _hover_suppressed (see
            # _DropdownItemSlot.hoverHitTest and its set/clear in
            # _begin_drag/cancel) — HoverCoordinator reconciles hover from
            # real cursor position on every app-wide mouse move, independent
            # of this capability's own bookkeeping, so suppressing at the
            # hit-test is what actually sticks. This call just clears
            # anything already set before drag start (e.g. a leftover from
            # _begin_drag's overflow-open-only path).
            overlay.clear_hover()
        # Commit the row under the frame straight away. There used to be a
        # 40ms ease-in "snap" to the exact item boundary plus a 250ms hold
        # after release; both made a released drag feel laggy, and the popup
        # is about to close anyway — the row that was under the frame at
        # release is the one the user chose.
        self._commit_selection(final_index)

    def _commit_selection(self, final_index: int) -> None:
        combo = self._combo
        # Only ever called while attached (between ComboBox.__init__'s
        # attach_capability() and detach()) — see attach()/detach() below.
        assert combo is not None
        if final_index >= 0:
            combo.setCurrentIndex(final_index)
        # hideDropdown() calls self.cancel(), which restores the cursor and
        # resets the rest of the drag state.
        combo.hideDropdown()

    def _restore_cursor(self) -> None:
        if self._cursor_hidden:
            # Warp back to where the gesture started *before* the icon
            # reappears — the real cursor traveled the raw, unclamped
            # physical drag distance the whole time (only the popup's
            # on-screen position was clamped to the item range), so without
            # this it would pop back into view wherever that raw motion left
            # it, possibly far from the field. Order matters: setting the
            # position while still blank avoids a visible flash of the
            # arrow at the old (wrong) spot.
            if self._press_global_pos is not None:
                QCursor.setPos(self._press_global_pos)
            QApplication.restoreOverrideCursor()
            self._cursor_hidden = False
            hover_coordinator().suppress_all(False)

    def cancel(self) -> None:
        """Force-abort an in-flight drag without committing a selection.

        Called from ``ComboBox.hideDropdown()`` for closes the gesture itself
        didn't initiate (outside click, window deactivate) — those bypass
        ``handle_release``/``_commit_selection``, so without this the
        override cursor would stay pushed with no matching release to pop it.
        """
        self._restore_cursor()
        if self._combo is not None and self._combo._overlay is not None:
            self._combo._overlay._hover_suppressed = False
        self._press_pos = None
        self._press_global_pos = None
        self.active = False
        self._overflow_open_only = False
        self.focus_index = -1
        self._window_origin = None
