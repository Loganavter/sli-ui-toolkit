"""A token-free pixmap label — the toolkit's replacement for ``QLabel`` images.

Every host that shows a static image used a stock ``QLabel`` with
``setPixmap`` / ``setScaledContents``, which is the one widget the toolkit's
"no stock Q* widget" rule could not satisfy: there was no painter-based
label that draws a pixmap. ``ImageLabel`` is that widget. It paints from a
transparent surface (or an optional ``background_token`` resolved through
``ThemeManager``), never through QSS.

Scaling semantics
-----------------
``setScaledContents(True)`` stretches the pixmap over the contents rect without
preserving the aspect ratio — QLabel's behaviour, measured: a host replacing a
``QLabel`` saw a 1-2 % page deviation while this widget kept the ratio instead.

With ``setScaledContents(False)`` the pixmap is drawn at its own logical size,
aligned by ``setAlignment`` and clipped by the widget boundary. Placement uses
``QStyle::alignedRect`` arithmetic (integer division, RTL-aware) because that is
what QLabel does: at an odd difference the float form landed one pixel off on
every row. The default alignment is QLabel's too (``AlignLeft | AlignVCenter``),
so a widget that never calls ``setAlignment`` places its pixmap identically.
The logical size is the pixmap's ``deviceIndependentSize()``, so a 2× screenshot
tagged with ``setDevicePixelRatio(2)`` is drawn at its intended size and
stays crisp: the target rectangle is in logical px and the painter applies the
widget's ratio on the way to device pixels.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor

logger = logging.getLogger(__name__)


class ImageLabel(QWidget):
    """Paints one ``QPixmap``; a drop-in for the pixmap half of ``QLabel``.

    The supported surface is what Designer-generated host code calls:
    ``setPixmap`` / ``pixmap``, ``setScaledContents`` / ``hasScaledContents``,
    ``setAlignment`` / ``alignment``, plus ``text()`` (always empty) and
    ``clear()``. ``setText`` exists only so a mechanically converted
    ``QLabel`` keeps importing; a pixmap label has no text, so it warns and
    changes nothing.
    """

    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar["WidgetDescriptor"]

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        pixmap: QPixmap | None = None,
        scaled_contents: bool = False,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        background_token: str | None = None,
    ) -> None:
        # ``parent`` is the first positional argument on purpose: Designer
        # emits ``QLabel(parent)`` then ``setPixmap``, so a converted line
        # must not hand the parent to a text slot.
        super().__init__(parent)
        # A pixmap label is transparent wherever the image does not cover the
        # widget: without this Qt erases the child with the palette window
        # colour before paintEvent, which turns the "no background" corners
        # into a grey box (the parent's surface must show through instead).
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._pixmap = QPixmap(pixmap) if pixmap is not None else QPixmap()
        self._scaled_contents = bool(scaled_contents)
        self._alignment: Qt.AlignmentFlag = Qt.AlignmentFlag(alignment)
        self._background_token = background_token
        self._theme_manager = ThemeManager.get_instance()
        try:
            self._theme_manager.theme_changed.connect(self.update)
        except Exception:  # pragma: no cover - defensive, manager is a QObject
            pass

    # -- pixmap ---------------------------------------------------------

    def setPixmap(self, pixmap: QPixmap | None) -> None:
        """Set the image; ``None`` or a null pixmap clears it."""
        self._pixmap = QPixmap(pixmap) if pixmap is not None else QPixmap()
        self.updateGeometry()
        self.update()

    def pixmap(self) -> QPixmap:
        """The current image as a copy (``isNull()`` when empty)."""
        return QPixmap(self._pixmap)

    def clear(self) -> None:
        """Drop the image, keeping geometry policy and alignment."""
        self.setPixmap(None)

    def has_pixmap(self) -> bool:
        return not self._pixmap.isNull()

    # -- scaling / alignment -------------------------------------------

    def setScaledContents(self, scaled: bool) -> None:
        scaled = bool(scaled)
        if scaled == self._scaled_contents:
            return
        self._scaled_contents = scaled
        self.updateGeometry()
        self.update()

    def hasScaledContents(self) -> bool:
        return self._scaled_contents

    def set_scaled_contents(self, scaled: bool) -> None:
        """Snake-case alias of :meth:`setScaledContents`."""
        self.setScaledContents(scaled)

    def has_scaled_contents(self) -> bool:
        return self._scaled_contents

    def setAlignment(self, alignment: Qt.AlignmentFlag) -> None:
        self._alignment = Qt.AlignmentFlag(alignment)
        self.update()

    def alignment(self) -> Qt.AlignmentFlag:
        return self._alignment

    # -- QLabel compatibility ------------------------------------------

    def text(self) -> str:
        """A pixmap label carries no text; this is always ``""``."""
        return ""

    def setText(self, text: str) -> None:
        """No-op: warn instead of silently pretending text was stored."""
        logger.warning(
            "ImageLabel ignores setText(%r): a pixmap label has no text",
            text,
        )

    # -- background -----------------------------------------------------

    def set_background_token(self, token: str | None) -> None:
        """Paint the widget surface with a theme token, or transparently."""
        if token == self._background_token:
            return
        self._background_token = token
        self.update()

    def background_token(self) -> str | None:
        return self._background_token

    # -- geometry -------------------------------------------------------

    def _logical_pixmap_size(self) -> QSizeF:
        """The pixmap's own size in logical px (DPR already divided out)."""
        return self._pixmap.deviceIndependentSize()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        if self._pixmap.isNull():
            return super().sizeHint()
        size = self._logical_pixmap_size()
        return QSize(round(size.width()), round(size.height()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        """The smallest slot the image can take.

        Scaled contents can shrink, but not to nothing: a label with an explicit ``setMaximumSize`` (an info icon in a
        row, 25x25) has to hold that slot, or a row whose other members add up to the whole width starves it to 0 px -
        measured on a migrated row where the icon disappeared while the stock `QLabel` kept its 25 px. Unscaled keeps
        the image intact and reports the native logical size.
        """
        if not self._scaled_contents:
            return self.sizeHint()
        maximum = self.maximumSize()
        hint = self.sizeHint()
        width = hint.width() if maximum.width() >= 16777215 else min(hint.width(), maximum.width())
        height = hint.height() if maximum.height() >= 16777215 else min(hint.height(), maximum.height())
        unit = scaled_px(1)
        return QSize(width if width > 0 else unit, height if height > 0 else unit)

    # -- painting -------------------------------------------------------

    def _aligned_top_left(self, size: QSize) -> QPointF:
        """``QStyle::alignedRect`` arithmetic, integer and layout-aware.

        QLabel places an unscaled pixmap with ``QStyle::alignedRect``, which divides
        ``(available - size) / 2`` in **integers** and flips the horizontal flag on a
        right-to-left layout. Matching that matters at odd differences: a 40x20 image in
        a 47x27 widget lands at y=3 with QLabel and at y=4 with float maths, and a host
        replacing the widget measures that one-pixel shift on every row.
        """
        rect = self.contentsRect()
        alignment = Qt.AlignmentFlag(self._alignment)
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            alignment ^= Qt.AlignmentFlag.AlignLeft
            alignment ^= Qt.AlignmentFlag.AlignRight
        x = rect.x()
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            x += (rect.width() - size.width()) // 2
        elif alignment & Qt.AlignmentFlag.AlignRight:
            x += rect.width() - size.width()
        y = rect.y()
        if alignment & Qt.AlignmentFlag.AlignVCenter:
            y += (rect.height() - size.height()) // 2
        elif alignment & Qt.AlignmentFlag.AlignBottom:
            y += rect.height() - size.height()
        return QPointF(x, y)

    def _draw_rect(self) -> QRectF:
        """Where the pixmap lands, in logical px, for the current widget size."""
        native = self._logical_pixmap_size()
        if self._scaled_contents:
            # QLabel semantics, deliberately: `setScaledContents(True)` stretches the pixmap over the whole contents
            # rect and does NOT preserve the aspect ratio. Keeping the aspect (this widget's first behaviour) made a
            # logo sit 1-2% differently from the widget it replaced in the host - measured, and it is the difference a
            # page-level pixel diff sees.
            return QRectF(self.contentsRect())
        rect = QRectF(QPointF(0.0, 0.0), native)
        rect.moveTopLeft(self._aligned_top_left(native.toSize()))
        return rect

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        if self._background_token:
            painter.fillRect(self.rect(), self._theme_manager.get_color(self._background_token))
        if self._pixmap.isNull():
            return
        if self._scaled_contents:
            # QLabel scales the pixmap once and blits it at the contents rect's top-left; drawing the source rect
            # straight into a float target (the obvious form) resamples differently at the edges - measured as 19-36
            # stray pixels per label against the stock widget.
            ratio = self.devicePixelRatioF()
            target = self.contentsRect().size() * ratio
            scaled = self._pixmap.scaled(
                target, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            scaled.setDevicePixelRatio(ratio)
            painter.drawPixmap(self.contentsRect().topLeft(), scaled)
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # Target is logical px; QPainter applies this widget's device ratio
        # (at 2× a DPR-tagged source lands 1:1 on device pixels instead of
        # being resampled soft). The source rect is the pixmap's own device
        # rectangle, which is what the two-rect overload expects.
        painter.drawPixmap(self._draw_rect(), self._pixmap, QRectF(self._pixmap.rect()))


ImageLabel.inspect_spec = InspectSpec(
    family="ImageLabel",
    state=(
        SpecField("has_pixmap", "has_pixmap"),
        SpecField("scaled_contents", "hasScaledContents"),
        SpecField("alignment", "alignment"),
    ),
    token_family=("surface.background",),
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

ImageLabel.widget_descriptor = WidgetDescriptor(
    family=ImageLabel.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ImageLabel.inspect_spec, "config", ()),
        state=ImageLabel.inspect_spec.state,
        token_family=getattr(ImageLabel.inspect_spec, "token_family", ()),
        regions=getattr(ImageLabel.inspect_spec, "regions", False),
        layers=getattr(ImageLabel.inspect_spec, "layers", False),
        docs=getattr(ImageLabel.inspect_spec, "docs", ""),
    ),
)
