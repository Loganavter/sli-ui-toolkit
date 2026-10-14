"""Guard ``isAncestorOf`` against non-widget objects in the submenu filter.

Regression (live): the ``ContextMenu`` installs an APP-WIDE event filter while
open (``base_flyout/lifecycle.py`` ``_grab_focus``), so ``eventFilter`` also
receives the ``QWindow`` backing a popup/native surface, which still gets
MouseMove/HoverMove. ``_is_forwarded_obj`` then called
``submenu.isAncestorOf(obj)`` — ``isAncestorOf`` only has a ``QWidget``
overload and raised ``TypeError`` (only ``RuntimeError`` was caught):

    TypeError: 'PySide6.QtWidgets.QWidget.isAncestorOf' called with wrong
    argument types: (QWindow)

These tests pin the ``isinstance(obj, QWidget)`` gate (mirrors
``flyout_manager._is_inside_active_flyout``).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.context_menu import submenu as submenu_ops
from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction


def _open_submenu_menu(qtbot) -> ContextMenu:
    parent = QWidget()
    parent.resize(640, 480)
    qtbot.addWidget(parent)
    parent.show()
    menu = ContextMenu(
        parent,
        entries=(
            ContextMenuAction(
                "sort_by",
                "Sort by",
                children=(ContextMenuAction("sort.name", "Name"),),
            ),
            ContextMenuAction("leaf", "Leaf"),
        ),
        surface="popup",
    )
    qtbot.addWidget(menu)
    menu.popup_at(parent.mapToGlobal(QPoint(80, 80)))
    qtbot.wait(10)
    menu._rows[0].clicked.emit()
    assert menu._open_submenu is not None
    return menu


# Factories, not instances: constructing a ``QWindow`` needs a live
# ``QGuiApplication``, so it must not happen at collection/import time.
@pytest.mark.parametrize("obj_factory", [QObject, QWindow], ids=["QObject", "QWindow"])
def test_is_forwarded_obj_non_widget_returns_false(qtbot, obj_factory) -> None:
    """A non-widget object (notably a QWindow) is never a branch member.

    Pre-fix this raised ``TypeError`` from ``isAncestorOf``; the guard must
    return ``False`` without raising.
    """
    menu = _open_submenu_menu(qtbot)

    assert submenu_ops._is_forwarded_obj(menu, obj_factory()) is False


def test_is_forwarded_obj_without_submenu_returns_false(qtbot) -> None:
    """Guard parity: no open submenu short-circuits to ``False`` either."""
    menu = _open_submenu_menu(qtbot)
    submenu_ops.close_submenu(menu, reason="test")
    assert menu._open_submenu is None

    assert submenu_ops._is_forwarded_obj(menu, QWindow()) is False


def test_event_filter_tolerates_qwindow_move(qtbot) -> None:
    """The app-wide filter must not raise on the QWindow's forwarded move.

    This is the exact runtime path from the traceback: a MouseMove whose
    ``obj`` is the popup's ``QWindow``, delivered while a submenu is open.
    """
    menu = _open_submenu_menu(qtbot)
    submenu = menu._open_submenu
    assert submenu is not None

    # Must not raise TypeError; the branch stays open.
    menu.eventFilter(QWindow(), QEvent(QEvent.Type.MouseMove))
    assert menu._open_submenu is submenu
