"""Structural test for gpu_fill QRhi path — no real GPU required."""
from __future__ import annotations
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.ui.widgets.composite.gpu_fill.widget import FlyoutGpuFillWidget
def test_gpu_fill_instantiates(qapp):
    w = FlyoutGpuFillWidget()
    assert w is not None
    w.deleteLater()
    qapp.processEvents()
def test_release_before_initialize_is_safe(qapp, qtbot):
    host = QWidget()
    host.show()
    qtbot.addWidget(host)
    w = FlyoutGpuFillWidget(parent=host)
    w.show()
    qtbot.addWidget(w)
    qapp.processEvents()
    w.releaseResources()
    w.releaseResources()
    assert w._pipeline is None
    assert w._srb is None
    assert w._ubuf is None
    assert w._last_rhi is None
    w.set_fill_color(QColor("#ff0000"))
    assert w.fill_color() == QColor("#ff0000")
def test_set_fill_color_noop_when_same(qapp, qtbot):
    w = FlyoutGpuFillWidget()
    qtbot.addWidget(w)
    w.set_fill_color(QColor(0, 0, 0, 0))
    w.set_fill_color(QColor(0, 0, 0, 0))
    w.set_fill_color(QColor("#112233"))
    assert w.fill_color().name() == QColor("#112233").name()
    w.deleteLater()
def test_internal_release_is_idempotent(qapp):
    w = FlyoutGpuFillWidget()
    w._release()
    w._release()
    assert w._pipeline is None
    assert w._srb is None
    assert w._ubuf is None
def test_sizehint_is_minimal(qapp):
    w = FlyoutGpuFillWidget()
    hint = w.sizeHint()
    assert hint.width() >= 1
    assert hint.height() >= 1
    w.deleteLater()
