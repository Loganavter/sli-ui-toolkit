"""Guard tests for ThemeManager.suspend_widget_updates (qt-selfsizing Phase 3).

The CSD punch-through class: holding ``setUpdatesEnabled(False)`` across a
gap where the window keeps delivering layout passes leaves never-repainted
(see-through) areas on ``WA_TranslucentBackground`` shells. The suspension
must therefore skip translucent top-levels while still freezing opaque ones
— asserted here, offscreen-deterministically (no compositor needed: the
contract is about *which windows get frozen*, not about pixels).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.theme_manager import ThemeManager


def _shown(qapp, *, translucent: bool) -> QWidget:
    del qapp
    w = QWidget()
    if translucent:
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.resize(200, 100)
    w.show()
    QApplication.processEvents()
    return w


def test_suspend_freezes_opaque_but_not_translucent(qapp):
    mgr = ThemeManager.get_instance()
    opaque = _shown(qapp, translucent=False)
    shell = _shown(qapp, translucent=True)
    assert opaque.updatesEnabled() and shell.updatesEnabled()
    with mgr.suspend_widget_updates():
        assert not opaque.updatesEnabled()
        assert shell.updatesEnabled(), (
            "translucent CSD shells must never be frozen: a mid-suspension "
            "geometry mutation would punch a see-through hole"
        )
    assert opaque.updatesEnabled() and shell.updatesEnabled()


def test_suspend_restores_prior_disabled_state(qapp):
    mgr = ThemeManager.get_instance()
    opaque = _shown(qapp, translucent=False)
    opaque.setUpdatesEnabled(False)
    with mgr.suspend_widget_updates():
        assert not opaque.updatesEnabled()
    assert not opaque.updatesEnabled(), "prior disabled state must survive"


def test_suspend_nests_without_early_restore(qapp):
    mgr = ThemeManager.get_instance()
    opaque = _shown(qapp, translucent=False)
    with mgr.suspend_widget_updates():
        assert not opaque.updatesEnabled()
        with mgr.suspend_widget_updates():
            assert not opaque.updatesEnabled()
        assert not opaque.updatesEnabled(), "inner exit must not restore"
    assert opaque.updatesEnabled()
