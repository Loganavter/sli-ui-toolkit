"""App tooltip interceptor must tolerate non-QObject watched objects (QRhi)."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject

from sli_ui_toolkit.ui.widgets.atomic.tooltips import (
    _ApplicationTooltipInterceptor,
    _TooltipInterceptor,
)


class _FakeEvent(QEvent):
    def __init__(self, etype: QEvent.Type):
        super().__init__(etype)


def test_application_tooltip_filter_ignores_non_qobject_watched(qapp):
    interceptor = _ApplicationTooltipInterceptor()
    # QRhi is not a QObject; app filters still receive its events under RHI.
    fake_rhi = SimpleNamespace()
    assert interceptor.eventFilter(fake_rhi, _FakeEvent(QEvent.Type.MetaCall)) is False


def test_widget_tooltip_filter_ignores_non_qobject_watched(qapp):
    interceptor = _TooltipInterceptor()
    fake_rhi = SimpleNamespace()
    assert interceptor.eventFilter(fake_rhi, _FakeEvent(QEvent.Type.ToolTip)) is False


def test_application_tooltip_filter_ignores_plain_qobject(qapp):
    interceptor = _ApplicationTooltipInterceptor()
    obj = QObject()
    assert interceptor.eventFilter(obj, _FakeEvent(QEvent.Type.ToolTip)) is False
    obj.deleteLater()
