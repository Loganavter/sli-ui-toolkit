"""The GPU filmstrip band of the timeline — a ``QRhiWidget`` over the strip row.

The host paints the tiles into one GPU pass and hands it over as a callback;
this widget owns only the Qt-side lifecycle and the view state:

* it is a child of the timeline widget, placed over the thumbnail row only,
  so the parent's QPainter chrome *outside* that row (gutter labels, track
  rows, ruler, footer, scrollbar) is never underneath it;
* a child widget composites above the parent's paint, so anything the parent
  draws *across* the strip row — the playhead line, the selection wash — is
  hidden inside the band rect; the renderer draws those itself (it receives
  the band, so ``band.view()``/``band.band_rect()`` are its inputs);
* it is paint-only (transparent to mouse events, no focus), so the host keeps
  hit-testing scrub / wheel zoom on the timeline itself;
* it never reads thumbnails, frames or scenes — :meth:`set_view` stores the
  scroll offset and zoom, and the injected renderer decides what to draw.

Intended parent wiring (``TimelineWidget.enable_strip_band`` does this in one
call; a host that drives its own scroll area calls ``sync_strip_band`` per
tick)::

    band = StripBand(timeline)
    band.set_renderer(render=draw_tiles, release=drop_textures)
    band.place(timeline.strip_band_rect())      # parent coordinates, band area
    band.set_view(scroll_x, zoom)               # per scroll / zoom tick

``render(command_buffer, band)`` draws the tiles for ``band.view()`` in the
band's own render target (``band.renderTarget()``) and reads the device pixel
ratio from ``band.device_pixel_ratio()``. ``release()`` drops every GPU
resource it created. Both are synchronous: no timer, no settle gate, no
debounce — the host's scroll tick reaches the GPU frame directly.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRect, QRectF, QSizeF, Qt
from PySide6.QtGui import QRhiCommandBuffer
from PySide6.QtWidgets import QRhiWidget, QWidget

#: ``render(command_buffer, band)`` — draw the tiles for ``band.view()``.
StripBandRenderer = Callable[[QRhiCommandBuffer, "StripBand"], None]
#: ``release()`` — drop every GPU resource the renderer created.
StripBandRelease = Callable[[], None]


class StripBand(QRhiWidget):
    """GPU band for the timeline's filmstrip row (host-rendered, toolkit-owned).

    The widget is app-agnostic: it creates no pipeline, loads no shader and
    owns no texture. It exists so the host does not have to subclass
    ``QRhiWidget`` itself and so the band's placement/view plumbing is one
    place in the toolkit.

    Geometry contract: :meth:`band_rect` is the band area *inside the parent
    widget*, and the band's own geometry is exactly that rect (the parent
    places an un-managed child, there is no layout). The parent recomputes it
    on resize and on scroll/zoom commits and calls :meth:`place` again; those
    calls are synchronous and cheap (an unchanged rect does nothing).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAutoFillBackground(False)  # see qrhi-gotchas.md#qrhiwidget-autofill
        # Paint-only overlay: the host keeps hit-testing (scrub, wheel zoom)
        # on the timeline underneath, so the band must never eat input.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._render: StripBandRenderer | None = None
        self._release: StripBandRelease | None = None
        self._view: tuple[int, float] = (0, 1.0)
        self._band_rect = QRect()

    # -- renderer injection -------------------------------------------------

    def set_renderer(
        self,
        render: StripBandRenderer | None = None,
        release: StripBandRelease | None = None,
    ) -> None:
        """Inject the host renderer / release pair (``None`` clears either).

        The pair is called from Qt's GPU callbacks only: ``render`` from
        :meth:`render`, ``release`` from :meth:`releaseResources`. Replacing a
        pair that already owns GPU resources does **not** release the previous
        one — the caller drops its own resources first, or replaces both
        before the first frame.
        """
        self._render = render
        self._release = release
        self.update()

    def renderer(self) -> StripBandRenderer | None:
        """The injected render callback, or ``None``."""
        return self._render

    # -- view state ---------------------------------------------------------

    def set_view(self, scroll_x: int, zoom: float) -> None:
        """Store the view and schedule one repaint — synchronous, no settle.

        Called per scroll/resize tick. An unchanged view is not "extra work":
        the store is idempotent and the only side effect is ``update()``, so
        the host never needs a debounce gate in front of it.
        """
        self._view = (int(scroll_x), float(zoom))
        self.update()

    def view(self) -> tuple[int, float]:
        """The stored ``(scroll_x, zoom)`` — what the renderer draws for."""
        return self._view

    # -- placement ----------------------------------------------------------

    def set_band_rect(self, rect: QRect | QRectF) -> None:
        """Set the band area (parent coordinates) and move the widget there."""
        area = rect.toRect() if isinstance(rect, QRectF) else QRect(rect)
        if area == self._band_rect:
            return
        self._band_rect = area
        self.setGeometry(area)
        self.update()

    def band_rect(self) -> QRect:
        """The band area inside the parent, in parent coordinates."""
        return QRect(self._band_rect)

    def place(self, rect: QRect | QRectF) -> None:
        """Place the band over ``rect`` (parent coordinates).

        The parent's per-tick entry point: same rect -> no geometry churn, new
        rect -> one resize + repaint. Callers pass the strip row's area, never
        the whole timeline (that would cover the parent's own chrome).
        """
        self.set_band_rect(rect)

    # -- device pixels ------------------------------------------------------

    def device_pixel_ratio(self) -> float:
        """This band's live device pixel ratio, unrounded.

        The renderer draws at device pixels: size its texture as
        :meth:`device_pixel_size` and tag it with this ratio. Never replace
        this with a constant — a fractional ratio (125 % / 150 %) is the
        normal case on those screens.
        """
        return float(self.devicePixelRatioF())

    def device_pixel_size(self) -> QSizeF:
        """The band's size in device pixels (``band_rect * ratio``, unrounded)."""
        area = self._band_rect
        ratio = self.device_pixel_ratio()
        return QSizeF(area.width() * ratio, area.height() * ratio)

    # -- QRhiWidget callbacks ----------------------------------------------

    def initialize(self, command_buffer: QRhiCommandBuffer) -> None:
        """Nothing to create: the injected renderer owns every GPU resource.

        Qt calls this once per RHI generation, before the first
        :meth:`render`; a renderer that needs the ``QRhi`` or the render
        target reads them from ``band.rhi()`` / ``band.renderTarget()``.
        """

    def render(self, command_buffer: QRhiCommandBuffer) -> None:  # type: ignore[override]
        # QRhiWidget's per-frame render callback — unrelated to (and shadows)
        # QWidget.render()'s paint-to-QPainter utility; PySide6's stubs model
        # both under the same name, hence the signature mismatch mypy sees.
        render = self._render
        if render is None:
            return
        render(command_buffer, self)

    def releaseResources(self) -> None:
        """Drop the renderer's GPU resources (the counterpart of :meth:`render`)."""
        release = self._release
        if release is None:
            return
        release()
