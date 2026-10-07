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
