"""AnchoredFlyoutAutoHide backstop — timeout must not retry forever.

Regression shape: a backstop timer armed on Leave, with mouse-click focus
lingering on the anchor/panel while the cursor is long gone, retried
forever ("panel hangs open"). Focus retains the panel for keyboard modality
only; mouse users are governed by hover.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QPushButton, QWidget

from sli_ui_toolkit.managers import NavigationManager
from sli_ui_toolkit.ui.managers.flyout_timer_service import AnchoredFlyoutAutoHide


def _hider(qapp, monkeypatch, *, keyboard: bool):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    anchor = QPushButton(host)
    anchor.setGeometry(10, 10, 120, 30)
    anchor.show()
    from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

    flyout = BaseFlyout(host)
    flyout.setGeometry(10, 50, 160, 120)
    flyout.show()
    qapp.processEvents()

    anchor.setFocus()
    assert qapp.focusWidget() is anchor
    nav = NavigationManager.get_instance()
    monkeypatch.setattr(nav, "last_input_was_keyboard", lambda: keyboard)
    # Cursor parked far outside anchor + panel.
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: QPoint(390, 290)))

    auto_hide = AnchoredFlyoutAutoHide(
        flyout=flyout, anchor_getter=lambda: anchor, retry_ms=50
    )
    return host, anchor, flyout, auto_hide


def test_timeout_hides_on_mouse_focus_outside(qapp, monkeypatch):
    _host, _anchor, flyout, auto_hide = _hider(qapp, monkeypatch, keyboard=False)
    auto_hide._on_timeout()
    assert not flyout.isVisible()


def test_timeout_retries_on_keyboard_focus(qapp, monkeypatch):
    _host, _anchor, flyout, auto_hide = _hider(qapp, monkeypatch, keyboard=True)
    auto_hide._on_timeout()
    assert flyout.isVisible()
