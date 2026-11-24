from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QColor,
    QRhi,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiDepthStencilClearValue,
    QRhiGraphicsPipeline,
    QRhiRenderPassDescriptor,
    QRhiShaderResourceBinding,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiViewport,
    QShader,
)
from PySide6.QtWidgets import QRhiWidget

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UBUF_SIZE = 16  # std140 vec4

#: Clear colour of the plate pass: straight alpha 1.0. A QRhiWidget's content is
#: blitted into the window's backingstore at flush time and OVERWRITES the
#: sibling widgets drawn under it (qrhi-gotchas.md), so there is no sibling
#: framebuffer to blend into -- an alpha-0 clear would leave the plate's
#: transparency undefined at the blit instead of showing anything through.
_OPAQUE_CLEAR_COLOR = QColor(0, 0, 0, 255)

#: Alpha written to the fill uniform, regardless of the colour's own alpha --
#: the plate is opaque by contract (see the class docstring).
_OPAQUE_FILL_ALPHA = 1.0


def _load_shader(name: str) -> QShader:
    data = (_SHADER_DIR / name).read_bytes()
    shader = QShader.fromSerialized(data)
    if not shader.isValid():
        raise RuntimeError(f"Failed to load shader: {name}")
    return shader


def _configure_opaque_pipeline(
    pipeline: QRhiGraphicsPipeline,
    *,
    srb: QRhiShaderResourceBindings,
    render_pass_descriptor: QRhiRenderPassDescriptor,
) -> None:
    """Configure *pipeline* for the plate's opaque fullscreen-triangle pass.

    Deliberately no ``setTargetBlends`` call: QRhi requests blending only when
    a ``TargetBlend`` asks for it, and this pass has nothing to blend against --
    the widget is blitted over the backingstore, not composited into it (see
    ``_OPAQUE_CLEAR_COLOR``). Split out of ``initialize`` so the no-blend
    contract is provable without a GPU.
    """
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
    pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
    pipeline.setShaderResourceBindings(srb)
    pipeline.setRenderPassDescriptor(render_pass_descriptor)


class FlyoutGpuFillWidget(QRhiWidget):
    """Opt-in GPU plate for BaseFlyout's panel fill: an OPAQUE solid-colour rect.

    The pass is opaque by contract -- no blend state is requested and the
    render target clears to alpha 1.0 -- because it cannot be anything else:
    a QRhiWidget's content is blitted into the window's backingstore at flush
    time and *overwrites* the sibling raster widgets drawn under it. There is
    no sibling framebuffer to alpha-blend against, no widget attribute that
    changes that (``WA_AlwaysStackOnTop`` only moves the widget above
    everything, and a mask is not a blend), and that is why REAL-Video-Enhancer
    dropped its translucent RHI overlay (commit ``00efff55``).

    Consequence for callers: ``set_fill_color`` uses the RGB channels only --
    an alpha below 255 is still painted opaque. A host that wants siblings to
    show through a flyout must use the default QPainter path, which paints a
    translucent panel in-process; this GPU path is for an opaque plate.

    Paint-only and mouse-transparent: it is never a hit target.

    Intentionally minimal (solid colour only, no gradient/texture/blur yet) --
    a foundation for a future GPU fill, never the default; BaseFlyout's
    QPainter path stays the default.
    """

    def __init__(self, parent=None, *, api: "QRhiWidget.Api | None" = None):
        super().__init__(parent)
        if api is not None:
            self.setApi(api)
        self.setAutoFillBackground(False)  # see qrhi-gotchas.md#qrhiwidget-autofill
        # A plate, not a control: clicks anywhere on it belong to the flyout
        # (or to the row above it), never to the GPU child.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # "Unset": BaseFlyout keeps the plate hidden until a solid brush
        # supplies a colour, and render() paints alpha opaque regardless.
        self._fill_color = QColor(0, 0, 0, 0)
        self._pipeline: QRhiGraphicsPipeline | None = None
        self._srb: QRhiShaderResourceBindings | None = None
        self._ubuf: QRhiBuffer | None = None
        self._last_rhi: QRhi | None = None

    def set_fill_color(self, color: QColor) -> None:
        """Set the plate's fill colour. Alpha is ignored -- the plate is opaque
        (see the class docstring); only R, G and B are painted."""
        if color == self._fill_color:
            return
        self._fill_color = QColor(color)
        self.update()

    def fill_color(self) -> QColor:
        """The colour last passed to :meth:`set_fill_color` (alpha included,
        even though the plate paints it opaque)."""
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
        _configure_opaque_pipeline(
            pipeline,
            srb=self._srb,
            render_pass_descriptor=self.renderTarget().renderPassDescriptor(),
        )
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

    def render(self, command_buffer: QRhiCommandBuffer) -> None:  # type: ignore[override]
        # QRhiWidget's per-frame render callback — unrelated to (and shadows)
        # QWidget.render()'s paint-to-QPainter utility; PySide6's stubs model
        # both under the same name, hence the signature mismatch mypy sees.
        rhi = self.rhi()
        if rhi is None or self._pipeline is None:
            return
        target = self.renderTarget()
        c = self._fill_color
        # Alpha is forced opaque: the pass blends nothing (see the class
        # docstring), so carrying the colour's alpha into the target would not
        # show a sibling through -- it would only make the blit's result
        # depend on the platform compositor.
        color_bytes = struct.pack(
            "<4f", c.redF(), c.greenF(), c.blueF(), _OPAQUE_FILL_ALPHA
        )

        updates = rhi.nextResourceUpdateBatch()
        # _ubuf/_srb are always set together with _pipeline in initialize().
        assert self._ubuf is not None
        # PySide6-stubs' updateDynamicBuffer overload for a raw bytes payload
        # is missing/mistyped; the (buffer, offset, data) call below is the
        # documented, working C++ signature.
        updates.updateDynamicBuffer(self._ubuf, 0, color_bytes)  # type: ignore[call-arg, arg-type]

        command_buffer.beginPass(
            target, _OPAQUE_CLEAR_COLOR, QRhiDepthStencilClearValue(1.0, 0), updates
        )
        command_buffer.setGraphicsPipeline(self._pipeline)
        size = target.pixelSize()
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, size.width(), size.height()))
        command_buffer.setShaderResources(self._srb)
        command_buffer.draw(3)
        command_buffer.endPass()

    def sizeHint(self) -> QSize:  # noqa: D401 - Qt override
        return QSize(1, 1)
