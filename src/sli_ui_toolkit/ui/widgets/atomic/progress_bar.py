"""A standalone painted progress bar — determinate, indeterminate, and themed.

Both hosts painted one by hand: BlinkTable subclassed ``QProgressBar`` and repainted it, REAL-Video-Enhancer drew a
thin bar inside a list-row painter. The toolkit had only the toast's bar, which is toast-only and takes token names as
constructor arguments. This is the reusable one: track from ``progress.track.background``, chunk from ``progress.fill``
/ ``progress.success`` / ``progress.error``, rounded ends, no stylesheet and no ``QProgressBar`` subclass.

The palette gap this closes: ``progress.success`` did not exist while a host already read it, so its "the chunk turns
green when the export succeeded" resolved through ``try_get_color`` to a fallback and never showed the designed colour.
"""

from __future__ import annotations

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font
from sli_ui_toolkit.ui.managers.ui_metrics import connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.themed import ThemedWidget

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor

_STATE_TOKENS: dict[str, str] = {
    "normal": "progress.fill",
    "success": "progress.success",
    "error": "progress.error",
}


class ProgressBar(ThemedWidget, QWidget):
    """Horizontal painted progress bar with optional centred text.

    ``height`` is design px (default 6) resolved through ``UiScale`` at paint/size-hint time; the rounded ends use
    half the painted height as the corner radius. ``text=None`` paints nothing — a host that wants a label passes
    ``"42%"`` (the hint then grows to fit one text line, since a 6 px bar cannot host glyphs). ``indeterminate=True``
    paints a chunk sliding across the track instead of a growing one, driven by a single timer that stops while the
    widget is hidden and stops on ``setIndeterminate(False)``.
    """

    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar["WidgetDescriptor"]

    #: Design-px bar height at ``UiScale`` factor 1.0.
    HEIGHT = 6
    #: Design-px width the layout hint asks for (the bar itself expands).
    HINT_WIDTH = 160
    #: Indeterminate chunk width, as a fraction of the painted track.
    INDETERMINATE_CHUNK = 0.3
    #: One full indeterminate travel takes ~1 s at 30 ms per tick.
    INDETERMINATE_TICK_MS = 30
    INDETERMINATE_STEP = 0.03

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        value: int = 0,
        minimum: int = 0,
        maximum: int = 100,
        indeterminate: bool = False,
        state: str = "normal",
        text: str | None = None,
        height: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._height = max(2, int(height) if height is not None else self.HEIGHT)
        self._minimum = int(minimum)
        self._maximum = max(self._minimum + 1, int(maximum))
        self._value = max(self._minimum, min(self._maximum, int(value)))
        self._indeterminate = bool(indeterminate)
        self._state = self._checked_state(state)
        self._text = None if text is None else str(text)
        self._phase = 0.0
        self._resume_on_show = False

        self.setAutoFillBackground(False)
        # Without this Qt erases the widget with the palette window colour before paintEvent, so the rounded ends
        # would sit on an opaque rectangle of the page colour.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_ui_font(self)

        self._timer = QTimer(self)
        self._timer.setInterval(self.INDETERMINATE_TICK_MS)
        self._timer.timeout.connect(self._tick)
        if self._indeterminate and not self.isHidden():
            self._timer.start()

        connect_ui_metrics(self, self.on_ui_metrics_changed)

    # -- value / range --------------------------------------------------

    def setValue(self, value: int) -> None:  # noqa: N802 - Qt naming, a host swaps its QProgressBar call 1:1
        clamped = max(self._minimum, min(self._maximum, int(value)))
        if clamped == self._value:
            return
        self._value = clamped
        self.update()

    def value(self) -> int:
        return self._value

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802 - Qt naming
        self._minimum = int(minimum)
        # An inverted/empty range would divide by zero in the fill fraction; QProgressBar's own convention is to keep
        # at least one step, so `maximum <= minimum` clamps instead of raising.
        self._maximum = max(self._minimum + 1, int(maximum))
        self.setValue(self._value)
        self.update()

    def minimum(self) -> int:
        return self._minimum

    def maximum(self) -> int:
        return self._maximum

    # -- state ----------------------------------------------------------

    def setIndeterminate(self, indeterminate: bool) -> None:  # noqa: N802 - Qt naming
        indeterminate = bool(indeterminate)
        if indeterminate == self._indeterminate:
            return
        self._indeterminate = indeterminate
        self._phase = 0.0
        if not indeterminate:
            self._timer.stop()
            self._resume_on_show = False
        elif not self.isHidden():
            self._timer.start()
        self.update()

    def isIndeterminate(self) -> bool:  # noqa: N802 - Qt naming
        return self._indeterminate

    def setState(self, state: str) -> None:  # noqa: N802 - Qt naming
        checked = self._checked_state(state)
        if checked == self._state:
            return
        self._state = checked
        self.update()

    def state(self) -> str:
        return self._state

    def setText(self, text: str | None) -> None:  # noqa: N802 - Qt naming
        new_text = None if text is None else str(text)
        if new_text == self._text:
            return
        self._text = new_text
        self.updateGeometry()
        self.update()

    def text(self) -> str | None:
        return self._text

    @staticmethod
    def _checked_state(state: str) -> str:
        if state not in _STATE_TOKENS:
            raise ValueError(f"ProgressBar: unknown state {state!r} (expected one of {sorted(_STATE_TOKENS)})")
        return state

    # -- geometry -------------------------------------------------------

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        height = scaled_px(self._height)
        if self._text is not None:
            height = max(height, self.fontMetrics().height() + scaled_px(4))
        return QSize(scaled_px(self.HINT_WIDTH), height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(scaled_px(24), scaled_px(self._height))

    def on_ui_metrics_changed(self, *_args: object) -> None:
        self.updateGeometry()
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + self.INDETERMINATE_STEP) % 1.0
        self.update()

    # -- hide/show handshake -------------------------------------------

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        # A hidden bar cannot paint; parking the timer keeps an offscreen or collapsed pane from burning repaints.
        if self._timer.isActive():
            self._resume_on_show = True
            self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        # A bar born (or switched) indeterminate while hidden starts ticking when it is shown, not before.
        if (self._resume_on_show or self._indeterminate) and not self._timer.isActive():
            self._resume_on_show = False
            self._timer.start()

    # -- painting -------------------------------------------------------

    def _colour(self, token: str, fallback: str) -> QColor:
        colour = self._theme_manager.try_get_color(token)
        if colour is not None and colour.isValid():
            return QColor(colour)
        # A host palette that omits the token still gets a usable bar: the trough falls back to the shared neutral
        # hairline rather than to the accent (which would make the empty part look like the filled one).
        return QColor(self._theme_manager.get_color(fallback))

    def _track_rect(self) -> QRectF:
        # Half-pixel inset: a rounded fill drawn on the widget edge is otherwise clipped to half its stroke-free area.
        return QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)

            rect = self._track_rect()
            if rect.width() <= 0.0 or rect.height() <= 0.0:
                return
            radius = rect.height() * 0.5

            painter.setBrush(QBrush(self._colour("progress.track.background", "separator.color")))
            painter.drawRoundedRect(rect, radius, radius)

            painter.setBrush(QBrush(self._colour(_STATE_TOKENS[self._state], "accent")))
            if self._indeterminate:
                chunk = rect.width() * self.INDETERMINATE_CHUNK
                # Travel from fully off the left edge to fully off the right one, so the chunk enters and leaves
                # instead of popping in at x=0.
                x = -chunk + self._phase * (rect.width() + chunk)
                chunk_rect = QRectF(x, rect.y(), chunk, rect.height())
                painter.save()
                painter.setClipRect(rect)
                painter.drawRoundedRect(chunk_rect, radius, radius)
                painter.restore()
            else:
                span = max(1, self._maximum - self._minimum)
                fraction = (self._value - self._minimum) / float(span)
                if fraction > 0.0:
                    fill_width = min(rect.width(), max(radius * 2.0, rect.width() * fraction))
                    painter.drawRoundedRect(QRectF(rect.x(), rect.y(), fill_width, rect.height()), radius, radius)

            if self._text:
                self._paint_text(painter, rect)
        finally:
            # A painter left active at the end of the paint cycle stalls repaints ("QBackingStore::endPaint() called
            # with active painter"); see SurfacePanel's note for the measured case.
            painter.end()

    def _paint_text(self, painter: QPainter, rect: QRectF) -> None:
        painter.setFont(self.font())
        # The bar's own label ink (`progress.text`); the neutral `Text` role is the fallback for a host palette that
        # predates the key, and both carry the colour this label used to borrow from `dialog.text`.
        painter.setPen(QColor(self._colour("progress.text", "Text")))
        metrics = painter.fontMetrics()
        label = metrics.elidedText(self._text or "", Qt.TextElideMode.ElideRight, int(rect.width()) - 4)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)


ProgressBar.inspect_spec = InspectSpec(
    family="ProgressBar",
    state=(
        SpecField("value", "value"),
        SpecField("minimum", "minimum"),
        SpecField("maximum", "maximum"),
        SpecField("indeterminate", "isIndeterminate"),
        SpecField("state", "state"),
        SpecField("text", "text"),
        SpecField("phase", "_phase", private=True),
    ),
    token_family=(
        "progress.track.background",
        "progress.fill",
        "progress.success",
        "progress.error",
        "progress.text",
    ),
    docs="docs/user/API_CATALOG.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor  # noqa: E402

ProgressBar.widget_descriptor = WidgetDescriptor(
    family=ProgressBar.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ProgressBar.inspect_spec, "config", ()),
        state=ProgressBar.inspect_spec.state,
        token_family=getattr(ProgressBar.inspect_spec, "token_family", ()),
        regions=getattr(ProgressBar.inspect_spec, "regions", False),
        layers=getattr(ProgressBar.inspect_spec, "layers", False),
        docs=getattr(ProgressBar.inspect_spec, "docs", ""),
    ),
)
