"""Show-time activation opt-out: hover pills must not page the compositor.

Regression for the gallery busy-cursor storm: a hover-frequency flyout
(one bare ``show()`` per pointer Enter — cards also sweep under a
stationary cursor during grid scroll) minted one xdg-activation request
per show whenever Qt reported the window inactive mid-gesture (the
common Wayland scroll state). The compositor answers the storm with
busy/loading cursor feedback — same class as the MC wheel-zoom storm
and the hide-time focus-restore banner. ``_no_window_activate`` opts a
pill out; default show() behavior is unchanged.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.widgets import IconActionFlyout


def _pill(parent):
    flyout = IconActionFlyout(parent, button_size=22, icon_size=14)
    flyout.set_actions([])
    return flyout


def test_show_activates_inactive_window_by_default(qapp, monkeypatch):
    """Pin existing behavior: keyboard/dialog flyouts still kick."""
    host = QWidget()
    host.resize(400, 300)
    host.show()
    flyout = _pill(host)
    calls: list[str] = []
    monkeypatch.setattr(host, "isActiveWindow", lambda: False)
    monkeypatch.setattr(
        host, "activateWindow", lambda *a, **k: calls.append("activate")
    )
    try:
        flyout.show()
    finally:
        flyout.deleteLater()
        host.deleteLater()
    assert calls == ["activate"]


def test_show_opt_out_issues_no_activation(qapp, monkeypatch):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    flyout = _pill(host)
    flyout._no_window_activate = True
    calls: list[str] = []
    monkeypatch.setattr(host, "isActiveWindow", lambda: False)
    monkeypatch.setattr(
        host, "activateWindow", lambda *a, **k: calls.append("activate")
    )
    try:
        flyout.show()
    finally:
        flyout.deleteLater()
        host.deleteLater()
    assert calls == []


def test_show_series_opt_out_leaves_no_override_cursor(qapp, monkeypatch):
    """Hover-frequency series: no activation storm, no override cursor."""
    host = QWidget()
    host.resize(400, 300)
    host.show()
    flyout = _pill(host)
    flyout._no_window_activate = True
    calls: list[str] = []
    monkeypatch.setattr(host, "isActiveWindow", lambda: False)
    monkeypatch.setattr(
        host, "activateWindow", lambda *a, **k: calls.append("activate")
    )
    try:
        for _ in range(12):
            flyout.show()
            qapp.processEvents()
            flyout.hide()
            qapp.processEvents()
    finally:
        flyout.deleteLater()
        host.deleteLater()
    assert calls == []
    assert QApplication.overrideCursor() is None


def test_show_active_window_needs_no_kick_either_way(qapp, monkeypatch):
    """Active host: no kick with or without the opt-out (already skipped)."""
    host = QWidget()
    host.resize(400, 300)
    host.show()
    calls: list[str] = []
    monkeypatch.setattr(host, "isActiveWindow", lambda: True)
    monkeypatch.setattr(
        host, "activateWindow", lambda *a, **k: calls.append("activate")
    )
    for flag in (False, True):
        flyout = _pill(host)
        flyout._no_window_activate = flag
        try:
            flyout.show()
            flyout.hide()
        finally:
            flyout.deleteLater()
    host.deleteLater()
    assert calls == []
