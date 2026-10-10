"""Submenu open/close/position helpers operating on a ContextMenu instance."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.core.debug_flags import any_flag
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

logger = logging.getLogger(__name__)

# Same stream as ``menu.py``: ``SLI_CTX_MENU_DEBUG``, ``[ctx-menu]`` prefix,
# off by default even under host ``--debug``. Firehose for the hover path:
# every open/close/schedule/forward decision logs one line so a "submenu
# vanishes on leave" report can be blamed on the exact transition instead
# of re-instrumented by hand.
_SUBMENU_DEBUG_VARS = ("SLI_CTX_MENU_DEBUG",)


def _submenu_debug_enabled() -> bool:
    """True when submenu hover tracing was opted in via env."""
    return any_flag(*_SUBMENU_DEBUG_VARS)


def _submenu_debug(message: str, *args) -> None:
    """Env-gated submenu trace line (already ``[ctx-menu]``-prefixed)."""
    if _submenu_debug_enabled():
        logger.debug(message, *args)


def _row_label(row) -> str:
    """Stable row identity for traces — never touches Qt beyond attrs."""
    try:
        spec = getattr(row, "_spec", None)
        action_id = getattr(spec, "action_id", None)
        text = getattr(row, "_text", None)
        return f"{type(row).__name__}(action_id={action_id!r} text={text!r})"
    except Exception:
        return "<undescribable>"


#: Hover delay before a parent row auto-opens its submenu. Zero on
#: purpose: our visual language opens branches immediately, no FM-parity
#: dwell (Dolphin hovers ~300ms). The single-shot timer machinery stays —
#: a Leave in the same event-loop turn still cancels the pending open —
#: but the interval is 0, so the open lands on the next loop pass.
#: Clicking still toggles immediately via ``toggle_submenu``.
SUBMENU_HOVER_DELAY_MS = 0

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
        _submenu_debug(
            "[ctx-menu] submenu open-keep row=%s (already owner)",
            _row_label(row),
        )
        return menu._open_submenu
    _submenu_debug(
        "[ctx-menu] submenu open-via-hover row=%s (open_owner=%s closed_row=%s)",
        _row_label(row),
        _row_label(menu._submenu_owner_row),
        _row_label(getattr(menu, "_submenu_closed_row", None)),
    )
    toggle_submenu(menu, row, spec)
    return menu._open_submenu


def close_submenu(menu: ContextMenu, *, reason: str = "unspecified") -> None:
    _cancel_pending_hover(menu)
    submenu = menu._open_submenu
    if submenu is None:
        return
    owner_label = _row_label(menu._submenu_owner_row)
    _submenu_debug(
        "[ctx-menu] submenu close reason=%s owner=%s visible=%s",
        reason,
        owner_label,
        bool(submenu.isVisible()),
    )
    menu._open_submenu = None
    if menu._submenu_owner_row is not None:
        menu._submenu_owner_row.set_submenu_open(False)
        # Arm the "just-closed owner" guard: the popup hide re-delivers a
        # hover Enter to the row still under the pointer, which would other-
        # wise re-schedule the hover-open (the branch blinks: closes and
        # reopens). Cleared when the pointer leaves the row / enters another.
        menu._submenu_closed_row = menu._submenu_owner_row
        _submenu_debug(
            "[ctx-menu] just-closed guard armed row=%s reason=%s",
            owner_label,
            reason,
        )
    menu._submenu_owner_row = None
    _remove_forwarding(menu, submenu)
    # Branches never fade (see ``toggle_submenu``): the hide is synchronous,
    # so the widget can be destroyed immediately — no fade finish handler
    # owns the ``deleteLater``.
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
        _submenu_debug(
            "[ctx-menu] submenu position row=%s target=%s (popup)",
            _row_label(row),
            submenu.geometry(),
        )
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
    _submenu_debug(
        "[ctx-menu] submenu position row=%s target=%s (in-window)",
        _row_label(row),
        submenu.geometry(),
    )


def toggle_submenu(
    menu: "ContextMenu", row: ContextMenuRow, spec: ContextMenuAction
) -> None:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu

    _cancel_pending_hover(menu)
    if menu._open_submenu is not None and menu._submenu_owner_row is row:
        _submenu_debug(
            "[ctx-menu] submenu toggle-close row=%s", _row_label(row)
        )
        close_submenu(menu, reason="toggle-same-row")
        return
    if menu._open_submenu is not None:
        _submenu_debug(
            "[ctx-menu] submenu toggle-switch from=%s to=%s",
            _row_label(menu._submenu_owner_row),
            _row_label(row),
        )
    else:
        _submenu_debug("[ctx-menu] submenu toggle-open row=%s", _row_label(row))
    close_submenu(menu, reason="toggle-switch")

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
    # Outside-click parity: a Qt popup grab natively hides only the topmost
    # popup, so an outside press would orphan the owner (still visible with
    # a stale ``_open_submenu``). QMenu dismisses the whole chain instead —
    # when the branch hides underneath an owner that still claims it, hide
    # the owner too (cascades up through nested owners via their own links).
    # Owner-driven closes clear ``_open_submenu`` before hiding the branch,
    # so this is a no-op on those paths (guarded in ``_on_branch_hidden``).
    submenu.aboutToHide.connect(
        lambda _m=menu, _s=submenu: _on_branch_hidden(_m, _s)
    )
    if not menu.is_popup_surface():
        submenu._ensure_overlay_parent(row)
    _submenu_debug(
        "[ctx-menu] submenu toggle-opened row=%s surface=%s",
        _row_label(row),
        menu._surface,
    )

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
    # Branches never fade. A submenu is a distinct popup, and fading the
    # outgoing branch kept it mapped for ~150ms while the incoming one faded
    # in — the two overlapped and the new branch read as "died" on switch.
    # Show/hide are instant for branches; only the root menu keeps the fade
    # (``_fade.fade_out_enabled`` stays False, so both ``hide()`` and
    # ``should_popup_fade_out`` take the instant path).
    submenu.show()
    submenu.raise_()
    if menu.is_popup_surface():
        # Wayland may ignore pre-show geometry/handles; re-apply once
        # mapped so the grab chain holds on the live surface too.
        bind_popup_transient_parent(submenu, menu)
    _install_forwarding(menu, submenu)


def _on_branch_hidden(menu: ContextMenu, submenu: ContextMenu) -> None:
    """Hide the owner when its branch hid underneath it (native-menu parity).

    No-op when the owner already detached the branch (owner-driven close,
    leaf-triggered root hide, entries reset): those clear ``_open_submenu``
    before the branch hides. Fires only for external hides — the native
    popup-grab outside press, compositor dismiss, or a direct ``hide()``
    on the branch — where the owner would otherwise stay orphaned.
    """
    try:
        still_claimed = menu._open_submenu is submenu
    except RuntimeError:
        return
    if not still_claimed:
        return
    _submenu_debug(
        "[ctx-menu] submenu branch hidden underneath -> hide owner"
    )
    try:
        menu.hide()
    except RuntimeError:
        pass


def _install_forwarding(menu: ContextMenu, submenu: ContextMenu) -> None:
    """Route submenu hover motion back to the owner menu.

    Once the submenu popup is shown it holds the mouse grab, so the owner
    menu's rows get no further Enter/hover events: without forwarding there
    is no switch when hovering a sibling parent row and no close when
    hovering a sibling leaf row. The owner installs itself as a filter on
    the submenu (and its rows); ``ContextMenu.eventFilter`` hit-tests the
    forwarded MouseMove/HoverMove positions (see ``_handle_submenu_forward``).
    """
    rows = list(getattr(submenu, "_rows", ()))
    try:
        submenu.setMouseTracking(True)
    except RuntimeError:
        pass
    try:
        submenu.installEventFilter(menu)
    except RuntimeError:
        pass
    for row in rows:
        try:
            row.installEventFilter(menu)
        except RuntimeError:
            pass
    _submenu_debug(
        "[ctx-menu] submenu forwarding installed rows=%d", len(rows)
    )


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


def _handle_submenu_forward(menu: ContextMenu, global_pos: QPoint) -> None:
    """Dispatch a hover position forwarded from the open submenu branch.

    The submenu holds the mouse grab while open, so the owner menu's rows
    see no Enter events; the position is hit-tested instead:

    (a) over a sibling parent row -> schedule a switch with the existing
    hover-delay machinery; (b) over a sibling leaf row -> close immediately
    (native-menu parity); (c) inside the open submenu branch, over the owner's
    own non-row chrome, or outside both menus -> change nothing (native-menu
    parity: aiming across the gap must never kill the submenu; it closes
    on sibling hover, outside click, Escape, or parent hide).
    """
    try:
        hit = QApplication.widgetAt(global_pos)
    except Exception as exc:
        _submenu_debug("[ctx-menu] submenu forward widgetAt raised err=%r", exc)
        return
    if hit is None:
        _submenu_debug(
            "[ctx-menu] submenu forward pos=%s hit=None -> keep (gap transit)",
            global_pos,
        )
        return
    if _branch_contains(menu, hit):
        _submenu_debug(
            "[ctx-menu] submenu forward pos=%s hit=%s -> keep (inside branch)",
            global_pos,
            type(hit).__name__,
        )
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
            _submenu_debug(
                "[ctx-menu] submenu forward pos=%s hit=%s -> switch-schedule",
                global_pos,
                _row_label(owner_row),
            )
            menu._schedule_submenu_hover(owner_row, spec)
        else:
            _submenu_debug(
                "[ctx-menu] submenu forward pos=%s hit=%s -> close (sibling leaf)",
                global_pos,
                _row_label(owner_row),
            )
            close_submenu(menu, reason="forward-sibling-leaf")
        return
    _submenu_debug(
        "[ctx-menu] submenu forward pos=%s hit=%s -> keep (owner chrome/outside)",
        global_pos,
        type(hit).__name__,
    )


def root_menu(menu: ContextMenu) -> ContextMenu:
    current = menu
    while current._owner_menu is not None:
        current = current._owner_menu
    return current
