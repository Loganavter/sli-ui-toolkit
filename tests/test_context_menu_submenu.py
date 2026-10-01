"""Popup-submenu grab chain + hover-open regression tests.

Live-Wayland bug: a submenu opened via ``toggle_submenu`` from a
popup-surface parent never received leaf clicks (3 opens, row hovers,
0 triggers — the compositor never transferred the xdg_popup grab because
the child popup was transient for the main window instead of the parent
popup). Offscreen QTest cannot reproduce the compositor grab itself, so
these tests pin the mechanism Qt needs for the transfer:

1. hover opens the submenu immediately (zero dwell) and the
   pending open is cancellable when the pointer leaves first;
2. the submenu popup's ``QWindow.transientParent`` is the PARENT POPUP's
   window (mirroring nested-QMenu xdg_popup nesting), not the logical
   anchor's window.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.composite.context_menu import submenu as submenu_ops
from sli_ui_toolkit.ui.widgets.composite.context_menu import menu as menu_mod
from sli_ui_toolkit.ui.widgets.composite.context_menu import rows as rows_mod
from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list = []

    def emit(self, record):
        self.records.append(record)


def _popup_menu(qtbot, entries) -> tuple[ContextMenu, QWidget]:
    parent = QWidget()
    parent.resize(640, 480)
    qtbot.addWidget(parent)
    parent.show()
    menu = ContextMenu(parent, entries=entries, surface="popup")
    qtbot.addWidget(menu)
    menu.popup_at(parent.mapToGlobal(QPoint(80, 80)))
    qtbot.wait(10)
    assert menu.isVisible()
    return menu, parent


def _submenu_entries() -> tuple:
    return (
        ContextMenuAction(
            "sort_by",
            "Sort by",
            children=(
                ContextMenuAction("sort.name", "Name"),
                ContextMenuAction("sort.date", "Date"),
            ),
        ),
        ContextMenuAction("leaf", "Leaf"),
    )


def _two_parent_entries() -> tuple:
    return (
        ContextMenuAction(
            "alpha",
            "Alpha",
            children=(
                ContextMenuAction("alpha.one", "A-One"),
                ContextMenuAction("alpha.two", "A-Two"),
            ),
        ),
        ContextMenuAction(
            "beta",
            "Beta",
            children=(
                ContextMenuAction("beta.one", "B-One"),
                ContextMenuAction("beta.two", "B-Two"),
            ),
        ),
        ContextMenuAction("leaf", "Leaf"),
    )


def _forward_move(menu, obj, monkeypatch, hit) -> None:
    """Deliver a submenu-grabbed MouseMove hit-testing as *hit*.

    The open submenu holds the mouse grab, so motion over the owner menu
    only reaches it via the forwarding filter installed on the submenu.
    ``QApplication.widgetAt`` is stubbed because the offscreen platform has
    no real cursor position.
    """
    monkeypatch.setattr(QApplication, "widgetAt", staticmethod(lambda _pos: hit))
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(5, 5),
        QPointF(5000, 5000),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    menu.eventFilter(obj, move)


def test_forward_hover_switches_to_sibling_parent(qtbot, monkeypatch) -> None:
    """Grab-forwarded hover on a sibling parent schedules a switch."""
    menu, _parent = _popup_menu(qtbot, _two_parent_entries())
    menu._rows[0].clicked.emit()
    assert menu._submenu_owner_row is menu._rows[0]

    _forward_move(menu, menu._open_submenu, monkeypatch, menu._rows[1])
    assert menu._submenu_hover_row is menu._rows[1]

    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 150)
    assert menu._submenu_owner_row is menu._rows[1]
    assert [r._text for r in menu._open_submenu._rows] == ["B-One", "B-Two"]


def test_forward_hover_leaf_closes_submenu(qtbot, monkeypatch) -> None:
    """Grab-forwarded hover on a sibling leaf closes immediately."""
    menu, _parent = _popup_menu(qtbot, _two_parent_entries())
    menu._rows[0].clicked.emit()
    assert menu._open_submenu is not None

    _forward_move(menu, menu._open_submenu, monkeypatch, menu._rows[2])
    assert menu._open_submenu is None


def test_forward_outside_keeps_submenu_open(qtbot, monkeypatch) -> None:
    """Aiming across the gap must never kill the submenu (QMenu parity).

    The pointer transits the gap between the menus on the way in; closing
    there made the submenu vanish mid-aim. It closes on sibling hover,
    outside click, Escape, or parent hide instead.
    """
    menu, _parent = _popup_menu(qtbot, _two_parent_entries())
    menu._rows[0].clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    _forward_move(menu, submenu, monkeypatch, None)
    assert menu._open_submenu is submenu

    # A slow aim (longer than any old grace) still leaves it open ...
    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 250)
    assert menu._open_submenu is submenu

    # ... and the branch still switches afterwards.
    _forward_move(menu, submenu, monkeypatch, menu._rows[1])
    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 150)
    assert menu._submenu_owner_row is menu._rows[1]


def test_forward_hover_does_not_double_schedule(qtbot, monkeypatch) -> None:
    """Repeated forwarded moves over the same row keep one pending timer."""
    menu, _parent = _popup_menu(qtbot, _two_parent_entries())
    menu._rows[0].clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    _forward_move(menu, submenu, monkeypatch, menu._rows[1])
    first_timer = menu._submenu_hover_timer
    assert first_timer is not None

    _forward_move(menu, submenu, monkeypatch, menu._rows[1])
    assert menu._submenu_hover_timer is first_timer


def test_hover_opens_submenu_immediately(qtbot) -> None:
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    row = menu._rows[0]
    assert row._has_children
    assert submenu_ops.SUBMENU_HOVER_DELAY_MS == 0

    menu.eventFilter(row, QEvent(QEvent.Type.Enter))
    assert menu._submenu_hover_timer is not None

    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 150)
    submenu = menu._open_submenu
    assert submenu is not None
    assert submenu.isVisible()
    assert [r._text for r in submenu._rows] == ["Name", "Date"]


def test_hover_open_cancelled_when_pointer_leaves(qtbot) -> None:
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    row = menu._rows[0]

    menu.eventFilter(row, QEvent(QEvent.Type.Enter))
    assert menu._submenu_hover_timer is not None
    menu.eventFilter(row, QEvent(QEvent.Type.Leave))
    assert menu._submenu_hover_timer is None

    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 150)
    assert menu._open_submenu is None


def test_hover_leaf_row_closes_open_submenu(qtbot) -> None:
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    menu._rows[0].clicked.emit()
    assert menu._open_submenu is not None

    menu.eventFilter(menu._rows[1], QEvent(QEvent.Type.Enter))
    assert menu._open_submenu is None


def test_submenu_transient_parent_is_parent_popup(qtbot) -> None:
    """Grab-chain mechanism: child popup nests under the parent popup."""
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    menu._rows[0].clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    parent_handle = menu.windowHandle()
    child_handle = submenu.windowHandle()
    assert parent_handle is not None
    assert child_handle is not None
    assert child_handle.transientParent() is parent_handle


def test_submenu_stays_inside_parent_outside_close(qtbot) -> None:
    """The open submenu area must not count as outside-close."""
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    menu._rows[0].clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    panel_tl = submenu.container.mapToGlobal(QPoint(0, 0))
    inside_submenu = panel_tl + QPoint(
        submenu.container.width() // 2, submenu.container.height() // 2
    )
    assert menu.contains_global(inside_submenu) is True


def test_branch_row_enter_does_not_close_submenu(qtbot) -> None:
    """Live bug: first step into the open submenu killed the branch.

    The owner installs itself as a filter on the submenu's rows
    (grab forwarding), and the Enter on a branch leaf fell into the
    "sibling leaf hovered" path — ``recent-empty`` Sort by died the
    moment the pointer reached its first child row.
    """
    menu, _parent = _popup_menu(qtbot, _two_parent_entries())
    menu._rows[0].clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    menu.eventFilter(submenu._rows[0], QEvent(QEvent.Type.Enter))
    assert menu._open_submenu is submenu
    assert submenu.isVisible()

    menu.eventFilter(submenu._rows[1], QEvent(QEvent.Type.Enter))
    assert menu._open_submenu is submenu


def test_branch_row_leave_keeps_pending_switch(qtbot, monkeypatch) -> None:
    """Leave inside the branch must not cancel a pending sibling switch."""
    menu, _parent = _popup_menu(qtbot, _two_parent_entries())
    menu._rows[0].clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    _forward_move(menu, submenu, monkeypatch, menu._rows[1])
    assert menu._submenu_hover_timer is not None

    menu.eventFilter(submenu._rows[0], QEvent(QEvent.Type.Leave))
    assert menu._submenu_hover_timer is not None

    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 150)
    assert menu._submenu_owner_row is menu._rows[1]


def test_owner_sibling_leaf_still_closes(qtbot) -> None:
    """Guard check: Enter on the owner's own leaf still closes (parity)."""
    menu, _parent = _popup_menu(qtbot, _two_parent_entries())
    menu._rows[0].clicked.emit()
    assert menu._open_submenu is not None

    menu.eventFilter(menu._rows[2], QEvent(QEvent.Type.Enter))
    assert menu._open_submenu is None


def test_toggle_close_does_not_reopen_on_hover_reenter(qtbot) -> None:
    """Closing a branch (click the owner row) must stay closed.

    The popup hide re-delivers a hover Enter to the row still under the
    pointer; the just-closed-owner guard must swallow it, or the branch
    blinks — closes and immediately reopens, flashing the row highlight.
    """
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    row = menu._rows[0]
    row.clicked.emit()
    assert menu._open_submenu is not None
    row.clicked.emit()  # toggle-close
    assert menu._open_submenu is None

    menu.eventFilter(row, QEvent(QEvent.Type.Enter))  # Qt's post-hide re-enter
    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 60)
    assert menu._open_submenu is None


def test_reenter_after_leave_reopens_submenu(qtbot) -> None:
    """After actually leaving the just-closed row, hover opens it again."""
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    row = menu._rows[0]
    row.clicked.emit()
    row.clicked.emit()  # close -> guard armed
    menu.eventFilter(row, QEvent(QEvent.Type.Leave))  # pointer leaves
    menu.eventFilter(row, QEvent(QEvent.Type.Enter))  # and comes back
    qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 60)
    assert menu._open_submenu is not None


def test_branch_hide_hides_owner(qtbot) -> None:
    """Outside-click parity: the native popup grab hides only the topmost
    popup, which orphaned the owner (visible with a stale ``_open_submenu``).
    A branch hidden underneath a claiming owner now hides the owner too —
    the whole chain dismisses like QMenu.
    """
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    menu._rows[0].clicked.emit()
    submenu = menu._open_submenu
    assert submenu is not None

    submenu.hide()  # what the native grab does on an outside press
    assert not menu.isVisible()
    assert menu._open_submenu is None


def test_owner_driven_close_does_not_rehide(qtbot) -> None:
    """Owner-driven closes clear the branch first: no hide ping-pong."""
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    menu._rows[0].clicked.emit()
    assert menu._open_submenu is not None
    menu.hide()
    assert menu._open_submenu is None
    assert not menu.isVisible()


def _enable_fade():
    from sli_ui_toolkit.config import (
        FlyoutTimingConfig,
        configure_toolkit,
        get_flyout_timings,
        reset_toolkit_config,
    )

    configure_toolkit(timings=FlyoutTimingConfig(default_flyout_animation="fade"))
    return get_flyout_timings().flyout_fade_out_duration_ms, reset_toolkit_config


def test_submenu_never_fades_even_with_fade_mode(qtbot) -> None:
    """Branches never fade, even with a fade-bearing global mode.

    A fading outgoing branch stayed mapped for ~150ms while the incoming
    one faded in; the two popups overlapped and the new branch read as
    "died" on switch. The submenu's fade controller stays unarmed, so
    ``hide()`` takes the instant path.
    """
    _fade_ms, reset = _enable_fade()
    try:
        menu, _parent = _popup_menu(qtbot, _submenu_entries())
        menu._rows[0].clicked.emit()
        submenu = menu._open_submenu
        assert submenu is not None
        assert submenu._fade.fade_out_enabled is False

        submenu.hide()
        assert submenu._popup_fade_anim is None
        assert not submenu.isVisible()
    finally:
        reset()


def test_root_menu_still_fades(qtbot) -> None:
    """Only the root keeps the fade — the branch change must not regress it."""
    _fade_ms, reset = _enable_fade()
    try:
        menu, _parent = _popup_menu(qtbot, _submenu_entries())
        assert menu._fade.fade_out_enabled is True
        menu.hide()
        assert menu._popup_fade_anim is not None
        assert menu.isVisible()  # fading out, not yet hidden
    finally:
        reset()


def test_root_fade_snapshot_active_before_first_frame(qtbot) -> None:
    """The fade snapshot must cover the live tree from the very first frame.

    ``paintEvent`` composites the snapshot only while ``opacity < 1.0``; the
    close path clears the owner row's open-highlight in the same turn, so at
    full opacity the live (plain) row painted for a frame — the selected
    button blinked on close. ``start_popup_fade_out`` now drops below 1.0 and
    hides the live children immediately.
    """
    _fade_ms, reset = _enable_fade()
    try:
        menu, _parent = _popup_menu(qtbot, _submenu_entries())
        qtbot.wait(_fade_ms + 80)  # let the show fade-in settle to 1.0
        menu._rows[0].clicked.emit()
        assert menu._fade.opacity == 1.0
        menu.hide()
        assert menu._fade.cache is not None
        assert menu._fade.opacity < 1.0  # snapshot path active immediately
    finally:
        reset()


def test_switch_hides_old_branch_before_new_one(qtbot) -> None:
    """Switching branches hides the outgoing one synchronously.

    The regression: the old branch faded out while the new one opened, so
    both popups were mapped at once and the new branch looked dead.
    """
    import shiboken6

    _fade_ms, reset = _enable_fade()
    try:
        menu, _parent = _popup_menu(qtbot, _two_parent_entries())
        menu._rows[0].clicked.emit()
        first = menu._open_submenu
        assert first is not None and first.isVisible()

        menu._rows[1].clicked.emit()  # switch to the second branch
        second = menu._open_submenu
        assert second is not None and second is not first
        assert second.isVisible()
        assert not shiboken6.isValid(first) or not first.isVisible()
    finally:
        reset()


def test_child_first_close_hides_branch_instantly(qtbot) -> None:
    """Native outside press hides the topmost popup first (child-first):
    the branch goes instantly, and the still-claiming owner fades as usual.
    """
    import shiboken6

    fade_ms, reset = _enable_fade()
    try:
        menu, _parent = _popup_menu(qtbot, _submenu_entries())
        menu._rows[0].clicked.emit()
        submenu = menu._open_submenu
        assert submenu is not None
        submenu.hide()  # what the native grab does on an outside press
        assert menu._open_submenu is None
        assert not submenu.isVisible()
        assert menu._popup_fade_anim is not None
        qtbot.wait(fade_ms + 250)
        assert not shiboken6.isValid(menu)
    finally:
        reset()


def test_owner_hide_closes_branch_instantly(qtbot) -> None:
    """Owner close: the branch is hidden instantly, the owner fades."""
    import shiboken6

    fade_ms, reset = _enable_fade()
    try:
        menu, _parent = _popup_menu(qtbot, _submenu_entries())
        menu._rows[0].clicked.emit()
        submenu = menu._open_submenu
        assert submenu is not None
        menu.hide()  # owner fades; branch closes instantly
        assert menu._open_submenu is None
        assert not submenu.isVisible()
        assert menu._popup_fade_anim is not None
        qtbot.wait(fade_ms + 250)
        assert not shiboken6.isValid(submenu)
        assert not shiboken6.isValid(menu)
    finally:
        reset()


def test_parent_hide_closes_submenu(qtbot) -> None:
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    menu._rows[0].clicked.emit()
    assert menu._open_submenu is not None
    menu.hide()
    assert menu._open_submenu is None


def _attach_capture():
    handler = _Capture()
    loggers = [
        logging.getLogger(submenu_ops.__name__),
        logging.getLogger(menu_mod.__name__),
        logging.getLogger(rows_mod.__name__),
    ]
    old_levels = []
    for logger in loggers:
        old_levels.append(logger.level)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    return handler, loggers, old_levels


def _detach_capture(handler, loggers, old_levels):
    for logger, level in zip(loggers, old_levels):
        logger.removeHandler(handler)
        logger.setLevel(level)


def test_submenu_traces_silent_when_gate_closed(qtbot, monkeypatch) -> None:
    """Firehose stays off without the env gate (default log silence)."""
    monkeypatch.delenv("SLI_CTX_MENU_DEBUG", raising=False)
    handler, loggers, old_levels = _attach_capture()
    try:
        menu, _parent = _popup_menu(qtbot, _two_parent_entries())
        menu._rows[0].clicked.emit()
        _forward_move(menu, menu._open_submenu, monkeypatch, menu._rows[2])
        assert menu._open_submenu is None
    finally:
        _detach_capture(handler, loggers, old_levels)
    assert [r for r in handler.records if "[ctx-menu]" in r.getMessage()] == []


def test_submenu_traces_fire_with_gate_open(qtbot, monkeypatch) -> None:
    """Gate open: open/forward/close each leave one [ctx-menu] line."""
    monkeypatch.setenv("SLI_CTX_MENU_DEBUG", "1")
    handler, loggers, old_levels = _attach_capture()
    try:
        menu, _parent = _popup_menu(qtbot, _two_parent_entries())
        menu._rows[0].clicked.emit()
        assert menu._open_submenu is not None
        _forward_move(menu, menu._open_submenu, monkeypatch, menu._rows[2])
        assert menu._open_submenu is None
    finally:
        _detach_capture(handler, loggers, old_levels)
    lines = [r.getMessage() for r in handler.records if "[ctx-menu]" in r.getMessage()]
    assert any("toggle-open" in line for line in lines)
    assert any("sibling leaf" in line for line in lines)
    assert any("reason=" in line for line in lines)


def test_submenu_traces_close_guard_and_row_transitions(qtbot, monkeypatch) -> None:
    """Gate open: the close→re-enter path pins the guard and row transitions.

    A "the parent button blinks on submenu close" report needs the armed
    guard, the suppressed re-open, and the row-level submenu-open / hover
    transitions in the same ``[ctx-menu]`` stream.
    """
    monkeypatch.setenv("SLI_CTX_MENU_DEBUG", "1")
    handler, loggers, old_levels = _attach_capture()
    try:
        menu, _parent = _popup_menu(qtbot, _submenu_entries())
        row = menu._rows[0]
        row.clicked.emit()  # open  -> row submenu-open=True
        row.clicked.emit()  # close -> guard armed, submenu-open=False
        row.enterEvent(
            QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5))
        )  # row-level hover trace
        menu.eventFilter(row, QEvent(QEvent.Type.Enter))  # post-hide re-enter
        qtbot.wait(submenu_ops.SUBMENU_HOVER_DELAY_MS + 60)
        assert menu._open_submenu is None
    finally:
        _detach_capture(handler, loggers, old_levels)
    lines = [r.getMessage() for r in handler.records if "[ctx-menu]" in r.getMessage()]
    assert any("just-closed guard armed" in line for line in lines)
    assert any("submenu-open=False" in line for line in lines)
    assert any("hover-enter" in line for line in lines)
    assert any("suppressed (just-closed owner)" in line for line in lines)
