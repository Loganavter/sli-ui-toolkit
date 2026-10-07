"""Scrollbar policy proxy — project-wide widget substitution enforcement.

The proxy style sees every widget at polish time and runs the registered
handlers: stock scroll areas get MinimalistScrollBar bars, overlay areas
keep their mirrored native bars, and future widget kinds plug in through
``register_widget_policy``. No host app code, no stylesheets — Qt mechanics
only (offscreen-safe).
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QScrollArea

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
    MinimalistScrollBar,
    OverlayScrollArea,
)
from sli_ui_toolkit.ui.widgets.helpers.scrollbar_policy import (
    WidgetPolicyProxyStyle,
    install_scrollbar_policy,
    register_widget_policy,
)


def _shown(qapp, w, *, w0=320, h0=240):
    w.resize(w0, h0)
    w.show()
    qapp.processEvents()
    return w


def test_public_surface_reexports_policy_api():
    import sli_ui_toolkit.widgets as pub

    assert pub.install_scrollbar_policy is install_scrollbar_policy
    assert pub.register_widget_policy is register_widget_policy
    assert pub.WidgetPolicyProxyStyle is WidgetPolicyProxyStyle


def test_polish_replaces_stock_bars(qapp):
    style = WidgetPolicyProxyStyle()
    for area in (QScrollArea(), QListWidget()):
        host = _shown(qapp, area)
        style.polish(area)
        qapp.processEvents()
        assert isinstance(area.verticalScrollBar(), MinimalistScrollBar)
        assert isinstance(area.horizontalScrollBar(), MinimalistScrollBar)
        host.close()


def test_polish_skips_overlay_areas(qapp):
    style = WidgetPolicyProxyStyle()
    area = OverlayScrollArea()
    host = _shown(qapp, area)
    style.polish(area)
    qapp.processEvents()
    # The hidden mirrored native bars stay stock; the floating overlay
    # thumbs are separate MinimalistScrollBar children.
    assert not isinstance(area.verticalScrollBar(), MinimalistScrollBar)
    assert not isinstance(area.horizontalScrollBar(), MinimalistScrollBar)
    host.close()


def test_polish_rehides_overlay_native_bars(qapp):
    """Leftover AsNeeded lines cannot resurrect the native look.

    Regression: call-site migrations to OverlayScrollArea kept stock-era
    policy overrides, showing a native scrollbar next to the custom one.
    """
    from PySide6.QtCore import Qt as _Qt

    style = WidgetPolicyProxyStyle()
    area = OverlayScrollArea()
    host = _shown(qapp, area)
    area.setVerticalScrollBarPolicy(_Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setHorizontalScrollBarPolicy(_Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    style.polish(area)
    qapp.processEvents()
    assert area.verticalScrollBarPolicy() == _Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert area.horizontalScrollBarPolicy() == _Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    # The mirrored native bars themselves are untouched (still stock).
    assert not isinstance(area.verticalScrollBar(), MinimalistScrollBar)
    assert not isinstance(area.horizontalScrollBar(), MinimalistScrollBar)
    host.close()


def test_policy_is_idempotent(qapp):
    style = WidgetPolicyProxyStyle()
    area = QScrollArea()
    host = _shown(qapp, area)
    style.polish(area)
    v0, h0 = area.verticalScrollBar(), area.horizontalScrollBar()
    style.polish(area)
    qapp.processEvents()
    assert area.verticalScrollBar() is v0
    assert area.horizontalScrollBar() is h0
    host.close()


def test_register_widget_policy_extension(qapp):
    calls: list = []
    key = register_widget_policy(QLabel, lambda w: calls.append(w), key="test-label-mark")
    assert isinstance(key, str) and key
    style = WidgetPolicyProxyStyle()
    label = QLabel("x")
    host = _shown(qapp, label)
    style.polish(label)
    style.polish(label)
    qapp.processEvents()
    assert calls == [label]
    host.close()


def _shown_area(qapp, **kw):
    from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea

    area = OverlayScrollArea(**kw)
    area.resize(320, 240)
    area.show()
    qapp.processEvents()
    return area


def test_sync_guard_cuts_nested_pass_and_defers(qapp):
    """A re-entrant sync returns immediately and re-arms the timer."""
    from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea

    area = _shown_area(qapp)
    assert isinstance(area, OverlayScrollArea)
    area._sync_depth = 1  # simulate mid-pass
    area._sync_steps_from_native()
    area._sync_h_steps_from_native()
    assert area._sync_depth == 1  # untouched by the cut passes
    assert area._update_timer.isActive()  # deferred re-sync queued
    area._sync_depth = 0
    area._update_timer.stop()
    area._sync_steps_from_native()  # normal path still runs
    assert area._sync_depth == 0
    area.close()


def test_guard_cuts_qt_delivered_nesting(qapp):
    """A native emission mid-pass reaches the guard, not a second pass."""
    area = _shown_area(qapp)
    orig_calls = []
    orig = OverlayScrollArea._update_scrollbar_visibility

    def noisy(*a, **k):
        n = area.verticalScrollBar()
        n.rangeChanged.emit(n.minimum(), n.maximum())  # nested delivery
        orig_calls.append(1)
        return orig(area, *a, **k)

    area._update_scrollbar_visibility = noisy
    try:
        area._sync_steps_from_native()
    finally:
        try:
            del area._update_scrollbar_visibility
        except Exception:
            pass
    # Without the guard the nested emission would run the visibility pass
    # a second time (orig twice); with it exactly once.
    assert len(orig_calls) == 1
    assert area._sync_cuts >= 1
    assert area._sync_depth == 0
    area.close()


def test_sync_spin_breaker_stops_rearming(qapp):
    """Past the cut budget the guard stops queueing the timer."""
    area = _shown_area(qapp)
    queued = []
    area._queue_scrollbar_sync = lambda: queued.append(1)  # type: ignore[method-assign]
    area._sync_depth = 1
    area._sync_cuts = 256
    try:
        area._sync_steps_from_native()
    finally:
        area._sync_depth = 0
    assert area._sync_cuts == 257
    assert queued == []  # breaker tripped: no re-arm
    area.close()


def test_install_end_to_end_and_restore(qapp):
    # Qt deletes the previous style inside setStyle: the pre-install style
    # object is gone after install, so teardown installs a fresh Fusion
    # instead of resurrecting a dangling wrapper. There is no uninstall —
    # production installs once per process.
    from PySide6.QtWidgets import QStyleFactory

    import sli_ui_toolkit.ui.widgets.helpers.scrollbar_policy as _pol

    app = QApplication.instance()
    assert app is not None
    try:
        assert install_scrollbar_policy() is True
        assert install_scrollbar_policy() is True  # idempotent
        assert isinstance(app.style(), WidgetPolicyProxyStyle)
        # Areas born after install are covered at real polish time.
        area = QScrollArea()
        host = _shown(qapp, area)
        assert isinstance(area.verticalScrollBar(), MinimalistScrollBar)
        assert isinstance(area.horizontalScrollBar(), MinimalistScrollBar)
        host.close()
    finally:
        try:
            app.setStyle(QStyleFactory.create("Fusion"))
        except Exception:
            pass
        try:
            _pol._STYLE_REF = None
        except Exception:
            pass
    assert not isinstance(app.style(), WidgetPolicyProxyStyle)
