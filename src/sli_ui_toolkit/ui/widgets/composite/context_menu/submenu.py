"""Submenu open/close/position helpers operating on a ContextMenu instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.ui.popup_surface import (
    bind_popup_transient_parent,
    clamp_popup_rect,
    screen_available_rect,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import ContextMenuAction
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import ContextMenuRow

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu


#: Hover delay before a parent row auto-opens its submenu (FM parity:
#: Dolphin hovers ~300ms). Clicking still opens immediately via
#: ``toggle_submenu``; the pending hover open is cancellable when the
#: pointer leaves the row first.
SUBMENU_HOVER_DELAY_MS = 300

#: Grace period before an open submenu closes when the pointer sits outside
#: both the owner menu and the submenu branch. The pointer merely transits
#: the gap between the two menus on the way in, so an immediate close would
#: flicker; a pending switch/close/branch-return cancels this timer.
_SUBMENU_OUTSIDE_GRACE_MS = 350


def _cancel_pending_hover(menu: ContextMenu) -> None:
    """Drop a scheduled hover-open without touching an open submenu."""
    timer = getattr(menu, "_submenu_hover_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except RuntimeError:
            pass
        menu._submenu_hover_timer = None
    if getattr(menu, "_submenu_hover_row", None) is not None:
        menu._submenu_hover_row = None


def open_submenu(
    menu: ContextMenu, row: ContextMenuRow, spec: ContextMenuAction
) -> ContextMenu | None:
    """Open hover-style: no-op when this row's submenu is already open.

    Unlike ``toggle_submenu`` (click path), hovering the owner row of an
    already-open submenu must keep it open, not close it.
    """
    if menu._open_submenu is not None and menu._submenu_owner_row is row:
        return menu._open_submenu
    toggle_submenu(menu, row, spec)
    return menu._open_submenu


def close_submenu(menu: ContextMenu) -> None:
    _cancel_pending_hover(menu)
    _cancel_outside_grace(menu)
    submenu = menu._open_submenu
    if submenu is None:
        return
    menu._open_submenu = None
    if menu._submenu_owner_row is not None:
        menu._submenu_owner_row.set_submenu_open(False)
    menu._submenu_owner_row = None
    _remove_forwarding(menu, submenu)
    submenu.hide()
    submenu.deleteLater()


def position_submenu(
    menu: ContextMenu, submenu: ContextMenu, row: ContextMenuRow
) -> None:
    size = submenu.sizeHint()
    if menu.is_popup_surface():
        anchor_tl = row.mapToGlobal(QPoint(0, 0))
        anchor_rect = QRect(anchor_tl, row.size())
        available = screen_available_rect(submenu, margin=4)
        target = QRect(
            anchor_rect.right() + 2,
            anchor_rect.top() - menu.SHADOW_RADIUS,
            size.width(),
            size.height(),
        )
        if (
            target.right() > available.right()
            and anchor_rect.left() - size.width() - 2 >= available.left()
        ):
            target.moveLeft(anchor_rect.left() - size.width() - 2)
        submenu.setGeometry(clamp_popup_rect(target, submenu, margin=4))
        return

    anchor_rect = surface_anchor_rect(submenu, row, submenu.overlay_layer)
    available = surface_available_rect(submenu, row, submenu.overlay_layer, margin=4)
    target = QRect(
        anchor_rect.right() + 2,
        anchor_rect.top() - menu.SHADOW_RADIUS,
        size.width(),
        size.height(),
    )
    if (
        target.right() > available.right()
        and anchor_rect.left() - size.width() - 2 >= available.left()
    ):
        target.moveLeft(anchor_rect.left() - size.width() - 2)
    target = clamp_surface_rect(target, available)
    submenu.setGeometry(target)


def toggle_submenu(
    menu: "ContextMenu", row: ContextMenuRow, spec: ContextMenuAction
) -> None:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu

    _cancel_pending_hover(menu)
    if menu._open_submenu is not None and menu._submenu_owner_row is row:
        close_submenu(menu)
        return
    close_submenu(menu)

    parent = menu._logical_parent if menu.is_popup_surface() else menu.parentWidget()
    submenu = ContextMenu(
        parent,
        entries=spec.children,
        on_triggered=menu._on_triggered,
        _is_submenu=True,
        surface=menu._surface,
    )
    submenu.actionTriggered.connect(menu.actionTriggered)
    submenu._owner_menu = menu
    if not menu.is_popup_surface():
        submenu._ensure_overlay_parent(row)

    menu._open_submenu = submenu
    menu._submenu_owner_row = row
    row.set_submenu_open(True)
    if menu.is_popup_surface():
        # Join the live compositor grab chain: the child popup must be
        # transient for the PARENT POPUP's window (not the logical anchor
        # widget's window), mirroring Qt's nested-QMenu xdg_popup nesting.
        # A submenu transient for the main window never joins the parent
        # popup's grab, so leaf presses never dispatch on live Wayland.
        bind_popup_transient_parent(submenu, menu)

    # Re-run the width/font pass just before showing, the same way
    # ``popup_at``/``show_aligned`` do for the top menu: the constructor's
    # set_entries -> _relayout_widths pass can leave the freshly created
    # rows on the inherited (design-sized) window font in some hosts (live:
    # Improve-ImgSLI — submenu rows rendered at the unscaled 12pt while the
    # parent menu rows were at 24pt), while a second pass reliably pins the
    # scale-resolved UI font on every row.
    submenu._relayout_widths()
    position_submenu(menu, submenu, row)
    submenu.show()
    submenu.raise_()
    if menu.is_popup_surface():
        # Wayland may ignore pre-show geometry/handles; re-apply once
        # mapped so the grab chain holds on the live surface too.
        bind_popup_transient_parent(submenu, menu)
    _install_forwarding(menu, submenu)


def _install_forwarding(menu: ContextMenu, submenu: ContextMenu) -> None:
    """Route submenu hover motion back to the owner menu.

    Once the submenu popup is shown it holds the mouse grab, so the owner
    menu's rows get no further Enter/hover events: without forwarding there
    is no switch when hovering a sibling parent row and no close when
    hovering a sibling leaf row. The owner installs itself as a filter on
    the submenu (and its rows); ``ContextMenu.eventFilter`` hit-tests the
    forwarded MouseMove/HoverMove positions (see ``_handle_submenu_forward``).
    """
    try:
        submenu.setMouseTracking(True)
    except RuntimeError:
        pass
    try:
        submenu.installEventFilter(menu)
    except RuntimeError:
        pass
    for row in list(getattr(submenu, "_rows", ())):
        try:
            row.installEventFilter(menu)
        except RuntimeError:
            pass


def _remove_forwarding(menu: ContextMenu, submenu: ContextMenu) -> None:
    """Detach a previous :func:`_install_forwarding` (close path)."""
    for row in list(getattr(submenu, "_rows", ())):
        try:
            row.removeEventFilter(menu)
        except RuntimeError:
            pass
    try:
        submenu.removeEventFilter(menu)
    except RuntimeError:
        pass


def _is_forwarded_obj(menu: ContextMenu, obj: object) -> bool:
    """True when *obj* belongs to the owner's open submenu branch."""
    submenu = menu._open_submenu
    if submenu is None or obj is None:
        return False
    try:
        if obj is submenu or submenu.isAncestorOf(obj):  # type: ignore[arg-type]
            return True
    except RuntimeError:
        return False
    # Nested open submenus hold the grab instead of the direct child; their
    # motion must still reach the owner (transit cancellation at least).
    nested = getattr(submenu, "_open_submenu", None)
    while nested is not None:
        try:
            if obj is nested or nested.isAncestorOf(obj):  # type: ignore[arg-type]
                return True
        except RuntimeError:
            return False
        nested = getattr(nested, "_open_submenu", None)
    return False


def _branch_contains(menu: ContextMenu, widget: object) -> bool:
    """True when *widget* sits inside the open submenu branch (any depth)."""
    submenu = menu._open_submenu
    while submenu is not None:
        try:
            if widget is submenu or submenu.isAncestorOf(widget):  # type: ignore[arg-type]
                return True
        except RuntimeError:
            return False
        submenu = getattr(submenu, "_open_submenu", None)
    return False


def _cancel_outside_grace(menu: ContextMenu) -> None:
    """Drop a pending outside-grace close without touching the submenu."""
    timer = getattr(menu, "_submenu_outside_timer", None)
    if timer is not None:
        try:
            timer.stop()
        except RuntimeError:
            pass
        menu._submenu_outside_timer = None


def _schedule_outside_grace(menu: ContextMenu) -> None:
    """Close the open submenu ~350ms after the pointer left both menus."""
    if menu._open_submenu is None:
        return
    if getattr(menu, "_submenu_outside_timer", None) is not None:
        return  # already pending; a single grace covers the gap transit
    timer = QTimer(menu)
    timer.setSingleShot(True)
    timer.setInterval(_SUBMENU_OUTSIDE_GRACE_MS)
    timer.timeout.connect(lambda: _on_outside_grace_timeout(menu, timer))
    menu._submenu_outside_timer = timer
    timer.start()


def _on_outside_grace_timeout(menu: ContextMenu, timer: QTimer) -> None:
    if getattr(menu, "_submenu_outside_timer", None) is not timer:
        return  # superseded by a cancel
    menu._submenu_outside_timer = None
    try:
        visible = menu._open_submenu is not None and menu._open_submenu.isVisible()
    except RuntimeError:
        return
    if not visible:
        return
    close_submenu(menu)


def _handle_submenu_forward(menu: ContextMenu, global_pos: QPoint) -> None:
    """Dispatch a hover position forwarded from the open submenu branch.

    The submenu holds the mouse grab while open, so the owner menu's rows
    see no Enter events; the position is hit-tested instead:

    (a) over a sibling parent row -> schedule a switch with the existing
    hover-delay machinery; (b) over a sibling leaf row -> close immediately
    (QMenu parity); (c) inside the open submenu branch -> cancel any pending
    switch/grace, change nothing else; (d) outside both menus -> start the
    outside-grace timer. Pointer motion over the owner's own non-row chrome
    only cancels the grace timer (the pointer is back over the owner).
    """
    try:
        hit = QApplication.widgetAt(global_pos)
    except Exception:
        return
    if hit is None:
        _schedule_outside_grace(menu)
        return
    owner_row: ContextMenuRow | None = None
    node: QWidget | None = hit
    for _ in range(8):
        if node is None:
            break
        if isinstance(node, ContextMenuRow):
            owner_row = node
            break
        try:
            node = node.parentWidget()
        except RuntimeError:
            break
    if owner_row is not None and any(owner_row is own for own in menu._rows):
        spec = getattr(owner_row, "_spec", None)
        children = getattr(spec, "children", None)
        if children:
            _cancel_outside_grace(menu)
            menu._schedule_submenu_hover(owner_row, spec)
        else:
            close_submenu(menu)
        return
    if _branch_contains(menu, hit):
        _cancel_pending_hover(menu)
        _cancel_outside_grace(menu)
        return
    try:
        if hit is menu or menu.isAncestorOf(hit):
            _cancel_outside_grace(menu)
            return
    except RuntimeError:
        pass
    _schedule_outside_grace(menu)


def root_menu(menu: ContextMenu) -> ContextMenu:
    current = menu
    while current._owner_menu is not None:
        current = current._owner_menu
    return current
