"""The gpu_fill plate's contract — no real GPU required.

The widget paints an OPAQUE plate. A QRhiWidget's content is blitted over the
sibling widgets under it, so it cannot alpha-blend against them (see
``gpu_fill/widget.py``); the tests below pin that without a GPU — the pipeline
builder is fed a recording stand-in, the render pass a fake command buffer, and
the docstrings are checked for the sibling-blending claim the widget used to
make.
"""

from __future__ import annotations

import inspect
import struct

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.ui.widgets.composite.gpu_fill import widget as gpu_fill_widget
from sli_ui_toolkit.ui.widgets.composite.gpu_fill.widget import (
    FlyoutGpuFillWidget,
    _configure_opaque_pipeline,
)

#: Phrases that must not come back: the widget used to claim it blended
#: translucently over its raster siblings, which a QRhiWidget cannot do.
_SIBLING_BLENDING_CLAIMS = (
    "composites translucently",
    "straight-alpha blending",
    "blend factors",
)


class _RecordingPipeline:
    """Stand-in for QRhiGraphicsPipeline that records every setter call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        def _record(*args, **kwargs) -> None:
            self.calls.append(name)

        return _record


class _RecordingCommandBuffer:
    def __init__(self) -> None:
        self.clear_colors: list[QColor] = []
        self.draws: list[int] = []
        self.begun_passes = 0
        self.ended_passes = 0

    def beginPass(self, target, clear, depth, updates=None):  # noqa: N802 — Qt API
        self.clear_colors.append(QColor(clear))
        self.begun_passes += 1

    def setGraphicsPipeline(self, pipeline) -> None:  # noqa: N802 — Qt API
        pass

    def setViewport(self, viewport) -> None:  # noqa: N802 — Qt API
        pass

    def setShaderResources(self, srb) -> None:  # noqa: N802 — Qt API
        pass

    def draw(self, count) -> None:
        self.draws.append(count)

    def endPass(self) -> None:  # noqa: N802 — Qt API
        self.ended_passes += 1


class _RecordingUpdateBatch:
    def __init__(self) -> None:
        self.buffers: list[bytes] = []

    def updateDynamicBuffer(self, buf, offset, data) -> None:  # noqa: N802 — Qt API
        self.buffers.append(bytes(data))


class _FakeRhi:
    def __init__(self) -> None:
        self.batches: list[_RecordingUpdateBatch] = []

    def nextResourceUpdateBatch(self):  # noqa: N802 — Qt API
        batch = _RecordingUpdateBatch()
        self.batches.append(batch)
        return batch


class _FakeRenderTarget:
    def pixelSize(self):  # noqa: N802 — Qt API
        return QSize(64, 32)


class _PlateWithFakes(FlyoutGpuFillWidget):
    """FlyoutGpuFillWidget whose RHI/render target are recorders."""

    def __init__(self, rhi: _FakeRhi, target: _FakeRenderTarget) -> None:
        super().__init__()
        self._fake_rhi = rhi
        self._fake_target = target

    def rhi(self):  # type: ignore[override]
        return self._fake_rhi

    def renderTarget(self):  # noqa: N802 — Qt API
        return self._fake_target


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


def test_widget_is_mouse_transparent(qapp):
    w = FlyoutGpuFillWidget()
    try:
        assert w.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    finally:
        w.deleteLater()


def test_pipeline_requests_no_blend_state(qapp):
    """The plate's pipeline builder must never ask for blending.

    A recording stand-in rather than a GPU: ``_configure_opaque_pipeline`` is
    the only place the pipeline state is assembled, so "it never calls
    setTargetBlends" is the whole no-blend contract.
    """
    pipeline = _RecordingPipeline()
    _configure_opaque_pipeline(
        pipeline, srb=object(), render_pass_descriptor=object()
    )
    assert pipeline.calls == [
        "setShaderStages",
        "setTopology",
        "setShaderResourceBindings",
        "setRenderPassDescriptor",
    ]
    assert "setTargetBlends" not in pipeline.calls


def test_render_clears_and_fills_opaque(qapp):
    """The pass clears to alpha 1.0 and forces the fill alpha opaque.

    A ``QColor`` with alpha 40 must still come out opaque: there is no blend
    to make it translucent, so carrying it through would only hand the blit an
    undefined look.
    """
    rhi = _FakeRhi()
    command_buffer = _RecordingCommandBuffer()
    w = _PlateWithFakes(rhi, _FakeRenderTarget())
    try:
        w.set_fill_color(QColor(10, 20, 30, 40))
        w._pipeline = _RecordingPipeline()
        w._srb = _RecordingPipeline()
        w._ubuf = object()

        w.render(command_buffer)
    finally:
        w.deleteLater()

    assert command_buffer.begun_passes == 1
    assert command_buffer.ended_passes == 1
    assert command_buffer.draws == [3]
    assert command_buffer.clear_colors[0].alphaF() == 1.0

    assert len(rhi.batches) == 1
    red, green, blue, alpha = struct.unpack("<4f", rhi.batches[0].buffers[0])
    assert (red, green, blue) == pytest.approx((10 / 255, 20 / 255, 30 / 255))
    assert alpha == 1.0


def test_module_declares_no_blend_state_and_an_opaque_clear(qapp):
    """Source-level pin against a blend state sneaking back in elsewhere."""
    source = inspect.getsource(gpu_fill_widget)
    # Match the call/enum form, not the prose in the docstring that explains
    # why neither exists.
    assert "setTargetBlends(" not in source
    assert "BlendFactor." not in source
    assert gpu_fill_widget._OPAQUE_CLEAR_COLOR.alphaF() == 1.0
    assert gpu_fill_widget._OPAQUE_FILL_ALPHA == 1.0


def test_docstrings_do_not_promise_sibling_blending():
    # Whitespace-normalised: the claim has to be caught even when the line
    # wrap falls between its words.
    doc = " ".join((FlyoutGpuFillWidget.__doc__ or "").lower().split())
    for claim in _SIBLING_BLENDING_CLAIMS:
        assert claim not in doc
    assert "opaque" in doc
    setter_doc = (FlyoutGpuFillWidget.set_fill_color.__doc__ or "").lower()
    assert "opaque" in setter_doc


def test_base_flyout_gpu_plate_is_opaque_and_opt_in(qapp):
    host = QWidget()
    flyout = BaseFlyout(host, attach_overlay=False, gpu_fill=True)
    try:
        plate = flyout._gpu_fill
        assert isinstance(plate, FlyoutGpuFillWidget)
        assert plate.parent() is flyout.container
        assert plate.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Hidden until a *solid* brush asks for it -- gradient/texture brushes
        # (and the theme default) stay on the QPainter path.
        assert plate.isHidden()

        flyout.set_background_brush(QColor(32, 32, 36))
        assert not plate.isHidden()
        assert plate.fill_color().name() == QColor(32, 32, 36).name()

        gradient = QLinearGradient(0, 0, 0, 10)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 40))
        flyout.set_background_brush(gradient)
        assert plate.isHidden()
    finally:
        flyout.deleteLater()
        host.deleteLater()


def test_base_flyout_default_path_has_no_gpu_plate(qapp):
    host = QWidget()
    flyout = BaseFlyout(host, attach_overlay=False)
    try:
        assert flyout._gpu_fill is None
    finally:
        flyout.deleteLater()
        host.deleteLater()
