from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QColor,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiDepthStencilClearValue,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiViewport,
    QShader,
)
from PySide6.QtWidgets import QRhiWidget

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UBUF_SIZE = 16  # std140 vec4


def _load_shader(name: str) -> QShader:
    data = (_SHADER_DIR / name).read_bytes()
    shader = QShader.fromSerialized(data)
    if not shader.isValid():
        raise RuntimeError(f"Failed to load shader: {name}")
    return shader


class FlyoutGpuFillWidget(QRhiWidget):
    """Opt-in GPU rendering path for BaseFlyout's panel fill.

    Renders a single flat-color fullscreen-triangle pass with straight-alpha
    blending, so it composites translucently over whatever sibling raster
    widgets are already drawn under it in the same top-level window -- this
    is a normal `QRhiWidget`-among-widgets scenario (Qt's own backingstore
    compositing), not a translucent top-level/CSD window, so it does not hit
    the Windows-D3D "see-through shell" class of bug documented for the main
    canvas (that one is specific to a *top-level* translucent QRhiWidget host).

    This is intentionally minimal (solid color only, no gradient/texture/blur
    yet) -- a foundation for a future GPU-blur fill, not a replacement for
    BaseFlyout's existing QPainter path, which stays the default.
    """

    def __init__(self, parent=None, *, api: "QRhiWidget.Api | None" = None):
        super().__init__(parent)
        if api is not None:
            self.setApi(api)
        self.setAutoFillBackground(False)  # see qrhi-gotchas.md#qrhiwidget-autofill
        self._fill_color = QColor(0, 0, 0, 0)
        self._pipeline: QRhiGraphicsPipeline | None = None
        self._srb = None
        self._ubuf = None
        self._last_rhi = None

    def set_fill_color(self, color: QColor) -> None:
        if color == self._fill_color:
            return
        self._fill_color = QColor(color)
        self.update()

    def fill_color(self) -> QColor:
        return QColor(self._fill_color)

    def initialize(self, command_buffer: QRhiCommandBuffer) -> None:
        rhi = self.rhi()
        if rhi is self._last_rhi and self._pipeline is not None:
            return
        self._release()
        self._last_rhi = rhi

        self._ubuf = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic, QRhiBuffer.UsageFlag.UniformBuffer, _UBUF_SIZE
        )
        if not self._ubuf.create():
            raise RuntimeError("Failed to create FlyoutGpuFillWidget uniform buffer")

        self._srb = rhi.newShaderResourceBindings()
        self._srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(
                    0,
                    QRhiShaderResourceBinding.StageFlag.VertexStage
                    | QRhiShaderResourceBinding.StageFlag.FragmentStage,
                    self._ubuf,
                )
            ]
        )
        if not self._srb.create():
            raise RuntimeError("Failed to create FlyoutGpuFillWidget SRB")

        pipeline = rhi.newGraphicsPipeline()
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("flyout_fill.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, _load_shader("flyout_fill.frag.qsb")
                ),
            ]
        )
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        pipeline.setTargetBlends([blend])
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
        pipeline.setShaderResourceBindings(self._srb)
        pipeline.setRenderPassDescriptor(self.renderTarget().renderPassDescriptor())
        if not pipeline.create():
            raise RuntimeError("Failed to create FlyoutGpuFillWidget pipeline")
        self._pipeline = pipeline

    def releaseResources(self) -> None:
        self._release()

    def _release(self) -> None:
        for res in (self._pipeline, self._srb, self._ubuf):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self._pipeline = None
        self._srb = None
        self._ubuf = None
        self._last_rhi = None

    def render(self, command_buffer: QRhiCommandBuffer) -> None:
        rhi = self.rhi()
        if rhi is None or self._pipeline is None:
            return
        target = self.renderTarget()
        c = self._fill_color
        color_bytes = struct.pack(
            "<4f", c.redF(), c.greenF(), c.blueF(), c.alphaF()
        )

        updates = rhi.nextResourceUpdateBatch()
        updates.updateDynamicBuffer(self._ubuf, 0, color_bytes)

        clear = QColor(0, 0, 0, 0)
        command_buffer.beginPass(
            target, clear, QRhiDepthStencilClearValue(1.0, 0), updates
        )
        command_buffer.setGraphicsPipeline(self._pipeline)
        size = target.pixelSize()
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, size.width(), size.height()))
        command_buffer.setShaderResources(self._srb)
        command_buffer.draw(3)
        command_buffer.endPass()

    def sizeHint(self) -> QSize:  # noqa: D401 - Qt override
        return QSize(1, 1)
