"""Hover host: a composite card lights an embedded action button.

Regression for the clean-review filmstrip cell: hovering the card did not
light its Restore button — HoverCoordinator lit a widget only from its own
area (``top_widget is widget or widget.isAncestorOf(top_widget)``), never
from a parent card. ``Button.setHoverHost(card)`` makes the card's area the
button's hover area (the mirror of the parent-stays-lit rule that keeps a
card lit while the pointer is over its children).
"""

from __future__ import annotations

from PySide6.QtCore import QPoint

from sli_ui_toolkit.ui.widgets.helpers import hover_coordinator
from sli_ui_toolkit.widgets import Button


def _lit(button) -> bool:
    return button._hovered_region is not None


def _pin_cursor(monkeypatch, point: QPoint) -> None:
    """Point ``QCursor.pos()`` at *point* (reconcile passes a pos, but
    ``setHoverActive`` derives the region from the live cursor)."""
    from sli_ui_toolkit.ui.widgets.buttons import events as button_events

    class _CursorAt:
        @staticmethod
        def pos() -> QPoint:
            return point

    monkeypatch.setattr(button_events, "QCursor", _CursorAt)


def test_hover_host_lights_button_from_card_area(qapp, monkeypatch):
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    host.resize(200, 120)
    host.show()
    btn = Button(text="restore", parent=host)
    btn.setGeometry(20, 80, 160, 32)
    btn.show()
    btn.setHoverHost(host)
    qapp.processEvents()

    coord = hover_coordinator()
    over_card = host.mapToGlobal(QPoint(100, 20))  # above the button rect
    _pin_cursor(monkeypatch, over_card)
    coord.reconcile(over_card)
    assert _lit(btn), "host hover must light the embedded button"

    off_card = host.mapToGlobal(QPoint(400, 400))
    _pin_cursor(monkeypatch, off_card)
    coord.reconcile(off_card)
    assert not _lit(btn), "leaving the card clears the button hover"

    host.deleteLater()


def test_plain_button_not_lit_from_card_area(qapp, monkeypatch):
    """Without a host, hovering the card area must not light the button."""
    from PySide6.QtWidgets import QWidget

    host = QWidget()
    host.resize(200, 120)
    host.show()
    btn = Button(text="plain", parent=host)
    btn.setGeometry(20, 80, 160, 32)
    btn.show()
    qapp.processEvents()

    coord = hover_coordinator()
    over_card = host.mapToGlobal(QPoint(100, 20))
    _pin_cursor(monkeypatch, over_card)
    coord.reconcile(over_card)
    assert not _lit(btn)

    btn.setHoverHost(host)
    coord.reconcile(over_card)
    assert _lit(btn)

    btn.setHoverHost(None)
    coord.reconcile(over_card)
    assert not _lit(btn)

    host.deleteLater()
