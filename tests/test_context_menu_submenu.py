"""Popup-submenu grab chain + hover-open regression tests.

Live-Wayland bug: a submenu opened via ``toggle_submenu`` from a
popup-surface parent never received leaf clicks (3 opens, row hovers,
0 triggers — the compositor never transferred the xdg_popup grab because
the child popup was transient for the main window instead of the parent
popup). Offscreen QTest cannot reproduce the compositor grab itself, so
these tests pin the mechanism Qt needs for the transfer:

1. hover opens the submenu within the FM-parity budget (~300ms) and the
   pending open is cancellable when the pointer leaves first;
2. the submenu popup's ``QWindow.transientParent`` is the PARENT POPUP's
   window (mirroring nested-QMenu xdg_popup nesting), not the logical
   anchor's window.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.composite.context_menu import submenu as submenu_ops
from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction


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


def test_hover_opens_submenu_within_budget(qtbot) -> None:
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    row = menu._rows[0]
    assert row._has_children
    assert submenu_ops.SUBMENU_HOVER_DELAY_MS <= 350

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


def test_parent_hide_closes_submenu(qtbot) -> None:
    menu, _parent = _popup_menu(qtbot, _submenu_entries())
    menu._rows[0].clicked.emit()
    assert menu._open_submenu is not None
    menu.hide()
    assert menu._open_submenu is None
