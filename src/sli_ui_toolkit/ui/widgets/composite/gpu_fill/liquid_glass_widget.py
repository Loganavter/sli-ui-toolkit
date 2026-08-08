from __future__ import annotations

import logging
import os
import struct
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPen,
    QRhiBuffer,
    QRhiColorAttachment,
    QRhiCommandBuffer,
    QRhiDepthStencilClearValue,
    QRhiGraphicsPipeline,
    QRhiReadbackDescription,
    QRhiReadbackResult,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiTextureRenderTargetDescription,
    QRhiViewport,
    QShader,
)
from PySide6.QtWidgets import QRhiWidget

logger = logging.getLogger("sli_ui_toolkit")

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_BLUR_UBUF_SIZE = 32  # std140: vec2 direction + float radiusPx + pad + vec2 uvOffset + vec2 uvScale
# std140: vec2 direction + float radiusPx + float cornerRadiusPx + vec4 tint
# + vec2 uvOffset + vec2 uvScale + vec2 panelSizePx + float borderWidthPx
# + float pad + vec4 borderColor + float debugViz + vec3 pad (struct size
# must round up to the largest member's alignment, vec4 = 16 bytes; 84 -> 96)
_COMPOSITE_UBUF_SIZE = 96

# Set to "1" to replace the composite shader's normal output with a
# false-color view of the border mask math (see liquid_glass_composite.frag's
# debugViz branch) -- diagnoses corner/border artifacts by showing the actual
# per-pixel mask values instead of guessing blind from the shader formulas.
_DEBUG_VIZ = os.environ.get("SLI_LIQUID_GLASS_DEBUG_VIZ") == "1"

# Set to a directory path to enable on-demand debug capture (see
# request_debug_capture()). Not a continuous per-frame dump -- render() fires
# on every repaint (every zoom/pan tick, cursor move, frameSubmitted from the
# source canvas -- see glass_hud.py's _watch_target), so dumping unconditionally
# produces tens of thousands of unlabelled PNGs with no way to tell which
# frame corresponds to a moment you actually cared about. Instead,
# request_debug_capture() arms a one-shot capture that the *next* render()
# call fulfills, wire it to a keypress/button so you control exactly when a
# capture happens (see GlassHUD's debug shortcut).
#
# Each capture saves a *pair*, not just this widget's own output: "after"
# (this widget's colorTexture(), i.e. what the shader actually produced) and
# "before" (the *source* canvas's own colorTexture(), cropped to the exact
# same on-screen sub-rect via the same uvOffset/uvScale this widget already
# computes for its raw-backdrop sampling) -- so the real ground-truth
# backdrop and the shader's attempt to reproduce it sit side by side as two
# same-sized, directly diffable images, instead of trusting the shader's own
# "raw" sample is self-consistent.
#
# No OS screenshot tool, window compositor, or display scaling sits between
# either texture and the saved pixels, unlike a manually taken screenshot.
# Same "poll for completion on the next call" pattern as shared.rendering.
# mip_cascade._flush_debug_readbacks in the host app: QRhi's Python bindings
# don't expose QRhiReadbackResult.completed, so _flush_debug_dump() (called
# at the top of the next render()) just checks whether result.data is
# populated yet instead of using a completion callback.
_DEBUG_DUMP_DIR = os.environ.get("SLI_LIQUID_GLASS_DEBUG_DUMP")


def _load_shader(name: str) -> QShader:
    data = (_SHADER_DIR / name).read_bytes()
    shader = QShader.fromSerialized(data)
    if not shader.isValid():
        raise RuntimeError(f"Failed to load shader: {name}")
    return shader


class LiquidGlassFillWidget(QRhiWidget):
    """GPU backdrop-glass fill: 2-pass separable blur of a *live* source
    ``QRhiWidget``'s own ``colorTexture()``, tinted, with a cheap top-glow +
    edge-rim "liquid glass" light cue.

    Replaces the CPU ``QGraphicsBlurEffect`` (and, before that, an even
    older CPU ``grabFramebuffer()`` + reupload round-trip -- see git
    history) path in ``GlassHUD``. Sampling ``colorTexture()`` directly
    works because Qt shares one underlying ``QRhi`` across every
    ``QRhiWidget`` in the same top-level window (``GlassHUD`` and the
    canvas both live in the app's single main window via
    ``attach_in_window_widget``, never a separate popup window) -- so this
    widget's blur pass can bind the canvas's own render-target texture as
    a sampled input with zero CPU involvement, not even a resource-update
    upload. The tradeoff: the source and this widget must request the same
    QRhi backend API, or Qt ends up with two incompatible QRhi instances in
    one window -- callers must pass a matching ``api=`` (see
    ``ui/widgets/canvas/rhi_backend.configure_rhi_widget`` in the app,
    which resolves the user's chosen backend consistently for both).

    Pipeline: pass 1 (``liquid_glass_blur.frag``) horizontal-blurs a
    sub-rect of the source's ``colorTexture()`` (selected via
    ``set_source_rect``'s ``uvOffset``/``uvScale``) into a small offscreen
    scratch texture sized to this widget's own panel; pass 2
    (``liquid_glass_composite.frag``) vertical-blurs the scratch texture
    straight into this widget's own render target, mixing in ``tint`` and
    the glow/rim. Both passes share one 5-tap linear-sampled Gaussian
    kernel (see the .frag files), applied once per axis -- a real
    separable blur, not a single-pass 2D approximation.
    """

    def __init__(self, parent=None, *, api: "QRhiWidget.Api | None" = None):
        super().__init__(parent)
        if api is not None:
            self.setApi(api)
        self.setAutoFillBackground(False)  # see qrhi-gotchas.md#qrhiwidget-autofill
        # Real transparency outside the rounded shape: the composite shader
        # outputs alpha=0 there (see liquid_glass_composite.frag's header
        # comment) and Qt needs this attribute to actually alpha-blend that
        # against sibling widgets instead of treating the backing store as
        # opaque. This app has a general QRhiWidget alpha=1 invariant
        # (render-pass-contract.md) guarding against a real Windows/D3D
        # failure mode (translucent CSD shell + alpha<1 QRhiWidget clear =
        # desktop hole, see qrhi-gotchas.md) -- that invariant was written
        # for the *main canvas* pass, not re-validated for this widget on
        # that platform. Confirmed working on this project's Linux/OpenGL
        # config (qrhi-gotchas.md separately notes "Linux OpenGL/Vulkan
        # usually fine" for the translucent-QRhiWidget class of issue).
        # Retest on Windows/D3D before relying on this there.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._source_widget: QRhiWidget | None = None
        self._tint = QColor(255, 255, 255, 0)
        self._blur_radius_px = 16.0
        self._corner_radius_px = 0.0
        self._border_color = QColor(255, 255, 255, 0)
        self._border_width_px = 1.0

        self._last_rhi = None
        self._sampler: QRhiSampler | None = None
        self._scratch_tex: QRhiTexture | None = None
        self._scratch_target = None
        self._scratch_rpdesc = None
        self._blur_pipeline: QRhiGraphicsPipeline | None = None
        self._blur_ubuf = None
        self._blur_srb = None
        self._composite_pipeline: QRhiGraphicsPipeline | None = None
        self._composite_pipeline_created = False
        self._composite_ubuf = None
        self._composite_srb = None

        self._debug_last_logged_state: tuple | None = None
        # (after_result, before_result) tuple once a capture has been issued
        # and is awaiting the "poll on next call" completion check; None
        # otherwise. before_result is None if there was no valid source_tex
        # to read back at capture time.
        self._debug_pending_capture: tuple | None = None
        self._debug_capture_requested = False
        self._debug_dump_seq = 0

    # -------- public API --------

    def set_source_widget(self, widget: "QRhiWidget | None") -> None:
        """The live ``QRhiWidget`` (e.g. the canvas) whose ``colorTexture()``
        this fill blurs. Must share this widget's QRhi (same top-level
        window, same requested backend API) -- see class docstring.

        This widget's on-screen position relative to ``widget`` is
        recomputed fresh every ``render()`` call (see
        ``_compute_uv_mapping``), not cached here -- matching the main
        canvas's own magnifier feature (``MagnifierPass.prepare()``, which
        recomputes its geometry every frame rather than caching it across
        discrete reposition events). A cache needs an invalidation trigger
        for every single thing that can move either widget, and missing
        just one leaves stale UVs -- which is exactly what happened before
        this: `GlassHUD._refresh_backdrop()` was called from `_position()`
        *before* `self.show()`, so an `isVisible()` guard silently skipped
        the very first computation and there was no later trigger
        guaranteed to fire and correct it for `InfoHUD` (shown once per
        image load, unlike `ZoomIndicator`, which self-healed by virtue of
        firing on every zoom/pan tick)."""
        self._source_widget = widget
        self.update()

    def set_tint(self, color: QColor) -> None:
        self._tint = QColor(color)
        self.update()

    def set_blur_radius_px(self, radius: float) -> None:
        self._blur_radius_px = max(0.0, float(radius))
        self.update()

    def set_corner_radius_px(self, radius: float) -> None:
        """Rounded-rect radius the composite shader shows the raw backdrop
        outside of (device px). Set to the panel's visual corner radius."""
        self._corner_radius_px = max(0.0, float(radius))
        self.update()

    def set_border(self, color: QColor, width_px: float) -> None:
        """Stroke drawn by the shader exactly at the content rect's edge
        (device px width) -- replaces BaseFlyout's CPU ``QPen`` border."""
        self._border_color = QColor(color)
        self._border_width_px = max(0.0, float(width_px))
        self.update()

    def request_debug_capture(self) -> None:
        """Arms a one-shot before/after GPU readback capture (see
        SLI_LIQUID_GLASS_DEBUG_DUMP's docstring above _DEBUG_DUMP_DIR),
        fulfilled by the *next* render() call. No-op if
        SLI_LIQUID_GLASS_DEBUG_DUMP isn't set. Wire this to a keypress or
        button in the host app -- see GlassHUD's debug shortcut -- so a
        capture happens at exactly the moment you're looking at the
        artifact, not at some arbitrary frame from a continuous dump."""
        if not _DEBUG_DUMP_DIR:
            return
        self._debug_capture_requested = True
        self.update()

    # -------- QRhiWidget lifecycle --------

    def initialize(self, command_buffer: QRhiCommandBuffer) -> None:
        rhi = self.rhi()
        if rhi is self._last_rhi and self._composite_pipeline is not None:
            return
        if self._last_rhi is None:
            # First-ever initialize() for this widget: log whether Qt
            # promoted it to a real native window. internalWinId() (unlike
            # winId()) does NOT force native-window creation as a side
            # effect of merely checking -- safe to call here for
            # diagnostics. A native child window stacks at the OS/window-
            # manager level, largely ignoring normal Qt widget Z-order
            # (raise_/lower_/stackUnder), which is the usual cause of a
            # QRhiWidget appearing to render "on top of everything" instead
            # of respecting sibling stacking.
            logger.debug(
                "LiquidGlassFillWidget.initialize(): api=%s native_window=%s "
                "internal_win_id=%s parent=%r geometry=%r",
                self.api(),
                self.testAttribute(Qt.WidgetAttribute.WA_NativeWindow),
                int(self.internalWinId()),
                self.parentWidget(),
                self.geometry(),
            )
        self._release()
        self._last_rhi = rhi

        self._sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self._sampler.create():
            raise RuntimeError("Failed to create LiquidGlassFillWidget sampler")

        self._blur_ubuf = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic, QRhiBuffer.UsageFlag.UniformBuffer, _BLUR_UBUF_SIZE
        )
        if not self._blur_ubuf.create():
            raise RuntimeError("Failed to create LiquidGlassFillWidget blur UBuf")

        self._composite_ubuf = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _COMPOSITE_UBUF_SIZE,
        )
        if not self._composite_ubuf.create():
            raise RuntimeError("Failed to create LiquidGlassFillWidget composite UBuf")

        composite_pipeline = rhi.newGraphicsPipeline()
        composite_pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    _load_shader("liquid_glass_pass.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    _load_shader("liquid_glass_composite.frag.qsb"),
                ),
            ]
        )
        composite_pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
        composite_pipeline.setRenderPassDescriptor(
            self.renderTarget().renderPassDescriptor()
        )
        self._composite_pipeline = composite_pipeline
        # Deferred: setShaderResourceBindings + .create() happen once the
        # scratch texture (pass 1's output, which this pass samples) exists
        # -- see _ensure_scratch, called from render() once this widget's
        # own target size is known. An SRB referencing a not-yet-created
        # texture is invalid.

    def releaseResources(self) -> None:
        self._release()

    def _release(self) -> None:
        resources = [
            self._blur_pipeline,
            self._composite_pipeline,
            self._blur_srb,
            self._composite_srb,
            self._blur_ubuf,
            self._composite_ubuf,
            self._scratch_target,
            self._scratch_tex,
            self._sampler,
        ]
        for res in resources:
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self._blur_pipeline = None
        self._composite_pipeline = None
        self._composite_pipeline_created = False
        self._blur_srb = None
        self._composite_srb = None
        self._blur_ubuf = None
        self._composite_ubuf = None
        self._scratch_target = None
        self._scratch_rpdesc = None
        self._scratch_tex = None
        self._sampler = None
        self._last_rhi = None

    def _ensure_scratch(self, size: QSize) -> bool:
        """Sized to this widget's own render target, not the (much larger)
        source texture -- pass 1 samples the source's colorTexture() at an
        arbitrary sub-rect but always writes at this panel's own
        resolution. Returns True if the scratch target was (re)created."""
        rhi = self.rhi()
        if self._scratch_tex is not None and self._scratch_tex.pixelSize() == size:
            return False
        for res in (self._scratch_target, self._scratch_tex):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass

        texture = rhi.newTexture(
            QRhiTexture.Format.RGBA8, size, 1, QRhiTexture.Flag.RenderTarget
        )
        if not texture.create():
            raise RuntimeError("Failed to create LiquidGlassFillWidget scratch texture")
        attachment = QRhiColorAttachment(texture)
        target = rhi.newTextureRenderTarget(
            QRhiTextureRenderTargetDescription(attachment)
        )
        rpdesc = target.newCompatibleRenderPassDescriptor()
        target.setRenderPassDescriptor(rpdesc)
        if not target.create():
            texture.destroy()
            raise RuntimeError(
                "Failed to create LiquidGlassFillWidget scratch render target"
            )
        self._scratch_tex = texture
        self._scratch_target = target
        self._scratch_rpdesc = rpdesc

        if self._blur_pipeline is not None:
            try:
                self._blur_pipeline.destroy()
            except RuntimeError:
                pass
            self._blur_pipeline = None  # rpdesc changed -- rebuilt in render()
        return True

    def _ensure_composite_resources(self) -> None:
        """No longer binds the foreign source texture -- the composite pass
        outputs real alpha=0 outside the rounded shape instead of an opaque
        resample of the live backdrop (see liquid_glass_composite.frag's
        header comment), so it only ever touches its own scratchTex. Kept
        rebuilding every call anyway (cheap: a small descriptor allocation,
        not a texture operation) rather than introducing new "when do I
        need to recreate this" caching logic for what's now a stable
        binding set. The pipeline is still built once and cached (first
        call only)."""
        rhi = self.rhi()
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        if self._composite_srb is not None:
            try:
                self._composite_srb.destroy()
            except RuntimeError:
                pass
        srb = rhi.newShaderResourceBindings()
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(
                    0, fragment, self._composite_ubuf
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, self._scratch_tex, self._sampler
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create LiquidGlassFillWidget composite SRB")
        self._composite_srb = srb

        if not self._composite_pipeline_created:
            self._composite_pipeline.setShaderResourceBindings(self._composite_srb)
            if not self._composite_pipeline.create():
                raise RuntimeError(
                    "Failed to create LiquidGlassFillWidget composite pipeline"
                )
            self._composite_pipeline_created = True

    def _ensure_blur_pipeline(self, source_tex: QRhiTexture) -> None:
        """Rebuilt every frame: the *foreign* source texture object can
        change identity any time the source widget resizes (its
        colorTexture() gets recreated), and a foreign QRhiTexture Python
        wrapper is not a reliable enough identity to detect that safely --
        so the SRB is simply recreated each call instead (cheap: a small
        descriptor allocation, not a texture operation). The pipeline
        itself is still built once and cached (only needs the scratch
        render-pass descriptor, which is stable across frames at a given
        panel size)."""
        rhi = self.rhi()
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        if self._blur_srb is not None:
            try:
                self._blur_srb.destroy()
            except RuntimeError:
                pass
        srb = rhi.newShaderResourceBindings()
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, fragment, self._blur_ubuf),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, source_tex, self._sampler
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create LiquidGlassFillWidget blur SRB")
        self._blur_srb = srb

        if self._blur_pipeline is None:
            pipeline = rhi.newGraphicsPipeline()
            pipeline.setShaderStages(
                [
                    QRhiShaderStage(
                        QRhiShaderStage.Type.Vertex,
                        _load_shader("liquid_glass_pass.vert.qsb"),
                    ),
                    QRhiShaderStage(
                        QRhiShaderStage.Type.Fragment,
                        _load_shader("liquid_glass_blur.frag.qsb"),
                    ),
                ]
            )
            pipeline.setTopology(QRhiGraphicsPipeline.Topology.Triangles)
            pipeline.setRenderPassDescriptor(self._scratch_rpdesc)
            pipeline.setShaderResourceBindings(srb)
            if not pipeline.create():
                raise RuntimeError("Failed to create LiquidGlassFillWidget blur pipeline")
            self._blur_pipeline = pipeline

    def _compute_uv_mapping(
        self, source_tex: QRhiTexture
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """This widget's own on-screen rect, mapped into the source
        widget's ``colorTexture()``'s own [0,1] UV space -- freshly, every
        call (see ``set_source_widget``'s docstring for why this isn't
        cached).

        Uses ``mapToGlobal``/``mapFromGlobal``, not ``mapTo`` -- ``mapTo``
        requires its argument to be an actual ancestor in the parent chain
        (raises ``QWidget::mapTo(): parent must be in parent hierarchy``
        otherwise), which doesn't hold here: this widget lives under a
        flyout attached to an in-window overlay layer
        (``attach_in_window_widget``), a separate branch of the widget tree
        from the source (canvas) widget, not a descendant of it. Global
        coordinates work for any two widgets sharing a screen regardless of
        tree relationship."""
        widget = self._source_widget
        top_left = widget.mapFromGlobal(self.mapToGlobal(QPoint(0, 0)))
        dpr = widget.devicePixelRatioF()
        size = source_tex.pixelSize()
        w = max(1, size.width())
        h = max(1, size.height())
        px_x = top_left.x() * dpr
        px_y = top_left.y() * dpr
        px_w = self.width() * dpr
        px_h = self.height() * dpr
        return (px_x / w, px_y / h), (px_w / w, px_h / h)

    def render(self, command_buffer: QRhiCommandBuffer) -> None:
        rhi = self.rhi()
        target = self.renderTarget()
        if rhi is None or target is None:
            return

        source_tex = (
            self._source_widget.colorTexture()
            if self._source_widget is not None
            else None
        )
        if source_tex is None or self._composite_pipeline is None:
            updates = rhi.nextResourceUpdateBatch()
            command_buffer.beginPass(
                target, QColor(0, 0, 0, 0), QRhiDepthStencilClearValue(1.0, 0), updates
            )
            command_buffer.endPass()
            return

        tsize = target.pixelSize()
        self._ensure_scratch(tsize)
        self._ensure_blur_pipeline(source_tex)
        self._ensure_composite_resources()

        (ox, oy), (sx, sy) = self._compute_uv_mapping(source_tex)

        updates = rhi.nextResourceUpdateBatch()
        updates.updateDynamicBuffer(
            self._blur_ubuf,
            0,
            struct.pack(
                "<8f", 1.0, 0.0, self._blur_radius_px, 0.0, ox, oy, sx, sy
            ),
        )
        t = self._tint
        b = self._border_color

        debug_state = (
            round(self._corner_radius_px, 3),
            round(self._border_width_px, 3),
            tsize.width(),
            tsize.height(),
        )
        if debug_state != self._debug_last_logged_state:
            self._debug_last_logged_state = debug_state
            logger.debug(
                "LiquidGlassFillWidget.render(): cornerRadiusPx=%s borderWidthPx=%s "
                "tsize=%sx%s (values actually packed into the composite UBuf -- "
                "if cornerRadiusPx here is 0 while set_corner_radius_px() was called "
                "with a nonzero value, the corner-radius setter call or its caller is "
                "the bug, not the shader math)",
                *debug_state,
            )

        updates.updateDynamicBuffer(
            self._composite_ubuf,
            0,
            struct.pack(
                "<24f",
                0.0,
                1.0,
                self._blur_radius_px,
                self._corner_radius_px,
                t.redF(),
                t.greenF(),
                t.blueF(),
                t.alphaF(),
                ox,
                oy,
                sx,
                sy,
                float(tsize.width()),
                float(tsize.height()),
                self._border_width_px,
                0.0,
                b.redF(),
                b.greenF(),
                b.blueF(),
                b.alphaF(),
                1.0 if _DEBUG_VIZ else 0.0,
                0.0,
                0.0,
                0.0,
            ),
        )

        command_buffer.beginPass(
            self._scratch_target,
            QColor(0, 0, 0, 0),
            QRhiDepthStencilClearValue(1.0, 0),
            updates,
        )
        command_buffer.setGraphicsPipeline(self._blur_pipeline)
        command_buffer.setViewport(
            QRhiViewport(0.0, 0.0, float(tsize.width()), float(tsize.height()))
        )
        command_buffer.setShaderResources(self._blur_srb)
        command_buffer.draw(3)
        command_buffer.endPass()

        command_buffer.beginPass(
            target, QColor(0, 0, 0, 0), QRhiDepthStencilClearValue(1.0, 0), None
        )
        command_buffer.setGraphicsPipeline(self._composite_pipeline)
        command_buffer.setViewport(
            QRhiViewport(0.0, 0.0, float(tsize.width()), float(tsize.height()))
        )
        command_buffer.setShaderResources(self._composite_srb)
        command_buffer.draw(3)
        command_buffer.endPass()

        if _DEBUG_DUMP_DIR:
            self._flush_debug_dump()
            if self._debug_capture_requested:
                self._debug_capture_requested = False
                # "after": this widget's own colorTexture() -- what the
                # shader actually produced. target (QRhiRenderTarget, from
                # self.renderTarget()) has no accessible texture()/
                # colorAttachmentAt() from here, so use the already-public
                # colorTexture() instead (the same texture object this
                # widget hands to any *other* widget that samples it as a
                # source).
                after_tex = self.colorTexture()
                after_result = None
                if after_tex is not None:
                    after_result = QRhiReadbackResult()
                    dump_updates = rhi.nextResourceUpdateBatch()
                    dump_updates.readBackTexture(
                        QRhiReadbackDescription(after_tex), after_result
                    )
                    command_buffer.resourceUpdate(dump_updates)
                # "before": the *source* canvas's own colorTexture(), full-size
                # -- cropped down to the same on-screen sub-rect as "after"
                # once the readback lands (see _flush_debug_dump), using the
                # ox/oy/sx/sy this render() call already computed above for
                # the shader's own raw-backdrop sampling. Reading back the
                # whole (much larger) canvas texture is wasteful per-frame,
                # which is exactly why this is capture-on-request instead of
                # continuous.
                before_result = QRhiReadbackResult()
                before_updates = rhi.nextResourceUpdateBatch()
                before_updates.readBackTexture(
                    QRhiReadbackDescription(source_tex), before_result
                )
                command_buffer.resourceUpdate(before_updates)
                self._debug_pending_capture = (
                    after_result,
                    before_result,
                    (ox, oy, sx, sy),
                )

    def _flush_debug_dump(self) -> None:
        """SLI_LIQUID_GLASS_DEBUG_DUMP-only: same "poll on the next call"
        idiom as the host app's mip_cascade._flush_debug_readbacks -- QRhi's
        Python bindings don't expose QRhiReadbackResult.completed, so this
        checks whether the readback(s) issued by a *previous* render() call
        (via request_debug_capture()) have landed yet, one call before this
        one might issue a new pair."""
        pending = self._debug_pending_capture
        if pending is None:
            return
        after_result, before_result, (ox, oy, sx, sy) = pending
        after_data = after_result.data if after_result is not None else b"done"
        before_data = before_result.data
        if not after_data or not before_data:
            return  # still waiting on the GPU -- check again next render()
        self._debug_pending_capture = None
        self._debug_dump_seq += 1
        try:
            os.makedirs(_DEBUG_DUMP_DIR, exist_ok=True)
        except OSError:
            logger.exception(
                "LiquidGlassFillWidget: failed to create debug dump dir %s",
                _DEBUG_DUMP_DIR,
            )
            return
        stem = f"liquid_glass_{id(self):x}_{self._debug_dump_seq:04d}"

        if after_result is not None and after_result.data:
            # Same backend-native-row-order readback caveat as "before"
            # below -- this widget is also a shown QRhiWidget, so its own
            # on-screen display is corrected by its normal compositing
            # blit, but this raw GPU readback of the same texture bypasses
            # that blit and needs the same mirror to be human-viewable.
            after_size = after_result.pixelSize
            after_image = QImage(
                bytes(after_result.data),
                after_size.width(),
                after_size.height(),
                QImage.Format.Format_RGBA8888,
            ).mirrored(False, True)
            after_image.save(os.path.join(_DEBUG_DUMP_DIR, f"{stem}_after.png"), "PNG")

        before_size = before_result.pixelSize
        # .mirrored(False, True): the raw readback is in the source
        # texture's own backend-native row order, not screen-top-down --
        # see liquid_glass_composite.frag's srcUv.y flip and its comment for
        # why (a shown QRhiWidget's Y-convention correction happens in its
        # own on-screen compositing blit, which this GPU-to-GPU/CPU readback
        # bypasses entirely). ox/oy/sx/sy are already top-down screen
        # fractions (from _compute_uv_mapping), so flip the image once here
        # rather than re-deriving flipped crop coordinates -- everything
        # below this line can then use plain top-down rects.
        before_full = QImage(
            bytes(before_result.data),
            before_size.width(),
            before_size.height(),
            QImage.Format.Format_RGBA8888,
        ).mirrored(False, True)
        crop = QRect(
            round(ox * before_size.width()),
            round(oy * before_size.height()),
            round(sx * before_size.width()),
            round(sy * before_size.height()),
        )
        before_full.copy(crop).save(
            os.path.join(_DEBUG_DUMP_DIR, f"{stem}_before.png"), "PNG"
        )
        # Also save the *whole* source canvas (uncropped) with the computed
        # crop rect outlined in red -- if the shader's raw/blurred sample
        # doesn't match what's visually under the flyout, this answers "is
        # the crop rect even landing in the right place on the full canvas,
        # or is _compute_uv_mapping's screen-to-texture math wrong" directly,
        # instead of only ever looking at the (already-cropped, so
        # impossible to place in context) before/after pair.
        annotated = before_full.convertToFormat(QImage.Format.Format_RGB32)
        painter = QPainter(annotated)
        painter.setPen(QPen(QColor(255, 0, 0), 3))
        painter.drawRect(crop)
        painter.end()
        annotated.save(
            os.path.join(_DEBUG_DUMP_DIR, f"{stem}_before_full_annotated.png"), "PNG"
        )
        logger.debug(
            "LiquidGlassFillWidget: saved debug capture %s_{before,after,"
            "before_full_annotated}.png in %s -- crop=%s of full %dx%d "
            "(ox=%.4f oy=%.4f sx=%.4f sy=%.4f)",
            stem,
            _DEBUG_DUMP_DIR,
            crop,
            before_size.width(),
            before_size.height(),
            ox,
            oy,
            sx,
            sy,
        )

    def sizeHint(self) -> QSize:  # noqa: D401 - Qt override
        return QSize(1, 1)
