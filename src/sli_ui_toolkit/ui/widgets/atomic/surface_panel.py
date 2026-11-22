"""A container that paints a themed background — the toolkit's answer to a page's background rule.

Every host that styles its pages with `QWidget { background-color: … }` keeps a stylesheet alive for one reason: nothing
in the toolkit paints a plain surface. `SurfaceScrollArea` can, but a page is not always a scroll area (a navigation
page is a layout of panels), and a scripted host that deletes its stylesheets then loses the page colour entirely.

`SurfacePanel` paints `background_token` (through `ThemeManager`, re-read on `theme_changed`), optionally rounded and
optionally stroked, and nothing else — no children management, no layout opinion. It is the widget to make a page or a
card when the colour has to come from a token instead of a stylesheet.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager

logger = logging.getLogger(__name__)


class SurfacePanel(QWidget):
    """Paints a token background; transparent when ``background_token`` is ``None``.

    ``radius`` rounds all four corners of the fill and the stroke together; ``border_token`` draws a 1 px stroke on the
    same rounded rectangle. A missing token falls back to a transparent paint instead of raising: a page that loses its
    colour is a bug to see, not a crash at startup.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        background_token: str | None = "surface.background",
        radius: int = 0,
        border_token: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._background_token = background_token
        self._radius = max(0, int(radius))
        self._border_token = border_token
        self._theme_manager = ThemeManager.get_instance()
        self.setAutoFillBackground(False)
        # Without this Qt erases the widget with the palette window colour before paintEvent, so a panel with no token
        # (or an unknown one) would paint an opaque grey box instead of nothing.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        try:
            self._theme_manager.theme_changed.connect(self.update)
        except Exception:  # pragma: no cover - defensive, the manager is a QObject
            pass

    # -- configuration --------------------------------------------------

    def set_background_token(self, token: str | None) -> None:
        if token == self._background_token:
            return
        self._background_token = token
        self.update()

    def background_token(self) -> str | None:
        return self._background_token

    def set_radius(self, radius: int) -> None:
        radius = max(0, int(radius))
        if radius == self._radius:
            return
        self._radius = radius
        self.update()

    def radius(self) -> int:
        return self._radius

    def set_border_token(self, token: str | None) -> None:
        if token == self._border_token:
            return
        self._border_token = token
        self.update()

    def border_token(self) -> str | None:
        return self._border_token

    # -- painting -------------------------------------------------------

    def _colour(self, token: str | None) -> QColor | None:
        if not token:
            return None
        # `get_color` never fails: an unknown token falls back to `surface.background`, which would silently paint the
        # wrong colour. The panel asks `try_get_color` so a typo paints nothing and logs instead of lying.
        colour = self._theme_manager.try_get_color(token)
        if colour is None:
            logger.warning("SurfacePanel: unknown theme token %r - painting nothing", token)
            return None
        return colour

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        fill = self._colour(self._background_token)
        border = self._colour(self._border_token)
        if fill is None and border is None:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            # A square fill covers whole pixels; antialiasing it would leave a translucent 1 px rim (measured: corner
            # alpha 63 instead of 255). A rounded fill needs it.
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, bool(self._radius))
            # Half-pixel inset for the 1 px stroke: on the widget edge it is otherwise clipped to half its width.
            rect = (QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
                    if self._radius or border is not None else QRectF(self.rect()))
            if fill is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill)
                if self._radius:
                    painter.drawRoundedRect(rect, self._radius, self._radius)
                else:
                    painter.drawRect(rect)
            if border is not None:
                painter.setPen(QPen(border, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if self._radius:
                    painter.drawRoundedRect(rect, self._radius, self._radius)
                else:
                    painter.drawRect(rect)
        finally:
            # END IT. A painter left active when the paint cycle finishes makes Qt warn "QBackingStore::endPaint() called
            # with active painter" and the window stops answering under repaint pressure - every page and panel is a
            # SurfacePanel, so this one omission stalls the whole app (measured 2026-11-22).
            painter.end()
