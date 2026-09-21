"""Flyout focus-restore guard: never page the compositor on hide.

Regression for the Wayland "«App» is ready" banner: a hiding flyout must
hand focus back to its host window ONLY when the host is the app's active
window. In particular, when nothing is active (minimizing / deactivating),
restoring carries no valid xdg-activation surface and Mutter marks the
host demanding attention.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.ui.widgets.composite.base_flyout.lifecycle import (
    should_restore_host_focus,
)
from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import (
    SimpleOptionsFlyout,
)


def _host(active, *, is_active=False):
    return SimpleNamespace(isActiveWindow=lambda: is_active)


def test_helper_no_window_never_restores(monkeypatch):
    monkeypatch.setattr(
        QApplication, "activeWindow", staticmethod(lambda: object())
    )
    assert (
        should_restore_host_focus(None, window_active_on_show=True) is False
    )


def test_helper_already_active_window_needs_no_restore(monkeypatch):
    win = QWidget()
    monkeypatch.setattr(QWidget, "isActiveWindow", lambda self: True)
    monkeypatch.setattr(
        QApplication, "activeWindow", staticmethod(lambda: win)
    )
    try:
        assert (
            should_restore_host_focus(win, window_active_on_show=True)
            is False
        )
    finally:
        win.deleteLater()


def test_helper_other_window_active_never_restores(monkeypatch):
    host = _host(None)
    other = object()
    monkeypatch.setattr(
        QApplication, "activeWindow", staticmethod(lambda: other)
    )
    assert (
        should_restore_host_focus(host, window_active_on_show=True) is False
    )


def test_helper_nothing_active_never_restores_minimize_case(monkeypatch):
    # THE minimize bug: activeWindow() is None while deactivating, but the
    # host was active when the flyout opened. Restoring here pages Mutter
    # with no valid token surface -> "«App» is ready" banner.
    host = _host(None)
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    assert (
        should_restore_host_focus(host, window_active_on_show=True) is False
    )


def test_helper_host_active_plus_shown_flag_restores(monkeypatch):
    host = _host(None)
    monkeypatch.setattr(
        QApplication, "activeWindow", staticmethod(lambda: host)
    )
    assert (
        should_restore_host_focus(host, window_active_on_show=True) is True
    )
    assert (
        should_restore_host_focus(host, window_active_on_show=False) is False
    )


def test_helper_errors_fail_closed(monkeypatch):
    class _Bad:
        def isActiveWindow(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        QApplication, "activeWindow", staticmethod(lambda: object())
    )
    assert (
        should_restore_host_focus(_Bad(), window_active_on_show=True) is False
    )


def test_simple_options_hide_with_nothing_active_skips_activate(
    qapp, monkeypatch
):
    host = QWidget()
    host.resize(400, 300)
    host.show()
    flyout = SimpleOptionsFlyout(parent_widget=host)
    flyout.populate(["a", "b"], current_index=0)
    calls: list[str] = []
    monkeypatch.setattr(
        host, "activateWindow", lambda *a, **k: calls.append("activate")
    )
    monkeypatch.setattr(
        host, "setFocus", lambda *a, **k: calls.append("focus")
    )
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: None))
    try:
        flyout.hide()
    finally:
        flyout.deleteLater()
        host.deleteLater()
    assert calls == [], f"restore paged compositor while inactive: {calls}"


def test_base_flyout_module_still_exports_helper():
    assert BaseFlyout is not None
