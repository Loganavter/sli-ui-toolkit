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
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
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
        opaque: bool = False,
    ) -> None:
        super().__init__(parent)
        self._background_token = background_token
        self._radius = max(0, int(radius))
        self._border_token = border_token
        # Opaque host: the panel fills its WHOLE rect with the surface it sits on (palette Window) and draws its plate
        # on top, instead of being WA_TranslucentBackground and letting whatever is behind show through. That is the
        # reference host's OpaqueFillHost: a content host must not rely on what is behind it, because a compositor that
        # keeps a stale frame or a parent that skips a repaint then shows through the holes (owner, 2026-11-22).
        self._opaque = bool(opaque)
        if self._opaque:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
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

    def set_opaque(self, opaque: bool) -> None:
        """Make the panel paint its whole rect (see `_opaque`); idempotent."""
        opaque = bool(opaque)
        if opaque == self._opaque:
            return
        self._opaque = opaque
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not opaque)
        self.update()

    def is_opaque(self) -> bool:
        return bool(self._opaque)

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
        if self._opaque:
            # Fill first, straight from the palette (the shell pins Window to the page surface), so the rounded plate
            # below keeps its corners correct and nothing behind can show through.
            painter.fillRect(event.rect(), self.palette().color(QPalette.ColorRole.Window))
        # A square fill covers whole pixels; antialiasing it would leave a translucent 1 px rim (measured: corner alpha
        # 63 instead of 255). A rounded fill needs it.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, bool(self._radius))
        # Half-pixel inset for the 1 px stroke: on the widget edge it is otherwise clipped to half its width.
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5) if self._radius or border is not None else QRectF(self.rect())
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
