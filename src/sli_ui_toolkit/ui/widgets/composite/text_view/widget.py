"""TextView — public composite: painted text rendering + editing.

A ``QScrollArea`` hosting a :class:`TextCanvas` (the painted surface that IS
the editor), a rounded border overlay glued to the visible area, and a
toolkit scrollbar. ``Expanding`` both ways so the frame hugs the visible
section area; the section page itself never scrolls.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QPixmap, QRegion
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QWidget

import logging
import os
import time
import traceback

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector.spec import InspectSpec  # noqa: E402
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.composite.help_document.image_lightbox import (
    HelpImageLightbox,
)

_tv_logger = logging.getLogger(__name__)
_last_scroll_log = 0.0

from . import constants
from .canvas import TextCanvas


class _FrameOverlay(QWidget):
    """Border-only overlay glued to the visible area of ``TextView``
    (transparent for mouse events): the scroll area paints nothing of its
    own behind its viewport, so the rounded frame is drawn ON TOP — the
    text canvas shows through, the border frames the visible region."""

    def __init__(self, owner: "TextView"):
        super().__init__()
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, _event) -> None:  # noqa: N802
        self._owner._paint_frame(self)


class TextView(QScrollArea):
    """Painted text view (the help-document text approach: text is painted,
    no stock Qt text widgets). The ROUNDED FRAME is an overlay glued to the
    visible viewport area, the scrollbar lives inside the widget. Both read
    and edit modes are the same painted canvas — identical rendering by
    construction."""

    changed = Signal()
    #: document mode: a link was clicked (href)
    linkActivated = Signal(str)
    #: document mode: an image was clicked (source asset path)
    imageActivated = Signal(str)

    def __init__(self, text: str = ""):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        # The canvas is resized to the viewport (and stretched to it when
        # the content is shorter): the view follows the window instead of
        # expanding to a fixed content-derived size.
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBar(MinimalistScrollBar())
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._canvas = TextCanvas(text)
        self._canvas.changed.connect(self.changed)
        self._canvas.linkActivated.connect(self.linkActivated)
        self._canvas.imageActivated.connect(self._on_image_activated)
        self.setWidget(self._canvas)
        # Stock QScrollArea viewports and setWidget-flipped content widgets
        # auto-fill the QPalette Window role, darker than the dialog surface
        # token the host paints — pin both transparent so the host surface
        # shows behind the frame overlay.
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self.viewport().setAutoFillBackground(False)
        self.viewport().setStyleSheet("background: transparent;")
        self._canvas.setAutoFillBackground(False)
        self._canvas.setStyleSheet("background: transparent;")
        # Debug: who scrolls the view (wheel / bar drag / HoverCoordinator)
        if os.getenv("SLI_TEXTVIEW_DEBUG") == "1":
            try:
                self.verticalScrollBar().valueChanged.connect(self._dbg_scroll_value)
                self._canvas.installEventFilter(self)
            except Exception:
                pass
        self._lightbox: HelpImageLightbox | None = None
        self._overlay = _FrameOverlay(self)
        self._overlay.setParent(self)
        self._sync_overlay_geometry()
        self._overlay.raise_()

    # -- state --------------------------------------------------------------

    def text(self) -> str:
        return self._canvas.text()

    def plain_text(self) -> str:
        """Full plain text of the current content (document or code)."""
        return self._canvas.plain_text()

    def set_text(self, text: str) -> None:
        self._canvas.set_text(text)

    def is_document(self) -> bool:
        return self._canvas.is_document()

    def set_markdown(self, markdown: str, *, resolve_asset=None) -> None:
        """Switch to read-only document mode (markdown blocks, images)."""
        self.exit_edit_mode()
        self._canvas.set_document(markdown, resolve_asset=resolve_asset)
        self.verticalScrollBar().setValue(0)

    def _on_image_activated(self, path: str) -> None:
        """Open the full-resolution image in the help lightbox (the plan's
        lightbox reuse); the ``imageActivated`` signal still fires so hosts
        can react too."""
        self.imageActivated.emit(path)
        pixmap = self._load_full_pixmap(path)
        if pixmap is None or pixmap.isNull():
            return
        host = self.window() if self.window() is not None else self
        if self._lightbox is None or self._lightbox.parent() is not host:
            if self._lightbox is not None:
                self._lightbox.hide()
                self._lightbox.deleteLater()
            self._lightbox = HelpImageLightbox(host)
        self._lightbox.show_pixmap(pixmap)

    def _load_full_pixmap(self, path: str) -> QPixmap | None:
        resolved: str | Path | QPixmap | None = path
        resolver = getattr(self._canvas, "_document_asset_resolver", None)
        if resolver is not None:
            try:
                resolved = resolver(path)
            except Exception:
                resolved = None
        if isinstance(resolved, QPixmap):
            return resolved
        if isinstance(resolved, (str, Path)):
            return QPixmap(str(resolved))
        return None

    def is_editing(self) -> bool:
        return self._canvas.is_editing()

    def canvas(self) -> TextCanvas:
        """The painted text surface (event filters, line math, gutters)."""
        return self._canvas

    def set_panel_fill(self, color: QColor | None) -> None:
        """Paint a shelf-style rounded well behind the text: the viewport
        gets an opaque fill clipped to the same rounded radius as the frame.
        ``None`` restores the default transparent state (the host surface
        shows behind the frame overlay). Used by hosts that want the code
        surface to read as a raised panel (e.g. the inspector Code section),
        like the app's recent-projects shelf.
        """
        viewport = self.viewport()
        if color is None:
            viewport.setStyleSheet("background: transparent;")
            viewport.setAutoFillBackground(False)
            viewport.clearMask()
            palette = viewport.palette()
            palette.setBrush(QPalette.ColorRole.Window, QPalette().window())
            viewport.setPalette(palette)
            return
        # The default transparent pin would override the palette fill —
        # clear it so the raised well paints.
        viewport.setStyleSheet("")
        palette = viewport.palette()
        palette.setBrush(QPalette.ColorRole.Window, QColor(color))
        viewport.setPalette(palette)
        viewport.setAutoFillBackground(True)
        self._apply_panel_mask()

    def _apply_panel_mask(self) -> None:
        viewport = self.viewport()
        if not viewport.autoFillBackground():
            return
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(viewport.rect()), constants.RADIUS, constants.RADIUS
        )
        viewport.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def set_line_number_start(self, start: int | None) -> None:
        """VS Code-style line-number gutter: the number of the first
        visible line (e.g. the class's line in its source file, so the
        gutter matches the actual file); ``None`` disables the gutter.
        """
        self._canvas.set_line_number_start(start)

    def editor(self) -> TextCanvas | None:
        """The editing surface (the painted canvas itself) while editing."""
        return self._canvas if self._canvas.is_editing() else None

    def enter_edit_mode(self) -> TextCanvas:
        # The painted canvas IS the editor — nothing is swapped, the scroll
        # position and rendering stay identical between modes.
        self._canvas.set_editing(True)
        return self._canvas

    def exit_edit_mode(self) -> None:
        self._canvas.set_editing(False)

    def _dbg_scroll_value(self, value: int) -> None:
        if os.getenv("SLI_TEXTVIEW_DEBUG") != "1":
            return
        global _last_scroll_log
        now = time.perf_counter()
        if now - _last_scroll_log < 0.05:  # throttle 20Hz
            return
        _last_scroll_log = now
        stack = "".join(traceback.format_stack()[-8:-3])
        msg = f"TextView scroll value={value} stack:\n{stack}"
        _tv_logger.warning(msg)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if os.getenv("SLI_TEXTVIEW_DEBUG") == "1":
            stack = "".join(traceback.format_stack()[-6:-2])
            msg = f"TextView wheel delta={event.angleDelta().y()} pixel={event.pixelDelta().y() if not event.pixelDelta().isNull() else 'null'} mods={event.modifiers()} stack:\n{stack}"
            _tv_logger.warning(msg)
        # Coalesce high-frequency touchpad wheel events (Wayland/X11 smooth
        # scroll sends dozens of small deltas per second, each would paint
        # 590 lines → 3ms × 100Hz = 300ms/s). Accumulate and flush once per
        # frame via singleShot(0) — best-practice for code editors.
        if not hasattr(self, "_wheel_accum"):
            from PySide6.QtCore import QTimer

            self._wheel_accum = 0
            self._wheel_timer = QTimer(self)
            self._wheel_timer.setSingleShot(True)
            self._wheel_timer.timeout.connect(self._flush_wheel)

        # Normalize to pixels: pixelDelta (touchpad smooth) is already pixels,
        # angleDelta (mouse wheel) is 120 per notch → ~15px per notch (Qt docs).
        if not event.pixelDelta().isNull():
            delta_px = event.pixelDelta().y()
        else:
            delta_px = int(event.angleDelta().y() / 8)
        self._wheel_accum += delta_px
        event.accept()
        if not self._wheel_timer.isActive():
            self._wheel_timer.start(0)
        return

    def _flush_wheel(self) -> None:
        if not hasattr(self, "_wheel_accum") or self._wheel_accum == 0:
            return
        delta_px = self._wheel_accum
        self._wheel_accum = 0
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - delta_px)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        if os.getenv("SLI_TEXTVIEW_DEBUG") == "1" and dy != 0:
            stack = "".join(traceback.format_stack()[-7:-3])
            msg = f"TextView scrollContentsBy dy={dy} stack:\n{stack}"
            _tv_logger.warning(msg)
        super().scrollContentsBy(dx, dy)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        return super().eventFilter(watched, event)

    # -- geometry / frame ---------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_overlay_geometry()
        self._apply_panel_mask()

    def _sync_overlay_geometry(self) -> None:
        # The frame encloses the whole widget, scrollbar included — the
        # scrollbar must sit INSIDE the rounded frame, not outside it.
        self._overlay.setGeometry(self.rect())

    def _paint_frame(self, target: QWidget) -> None:
        """Rounded border only — a fill here would cover the text canvas
        underneath, and the host background already reads as the surface."""
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = ThemeManager.get_instance()
        border = tm.try_get_color("separator.color")
        if border is None or not border.isValid():
            return
        rect = target.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(QColor(border), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, constants.RADIUS, constants.RADIUS)


TextView.inspect_spec = InspectSpec(
    family="TextView",
    docs="docs/user/TEXT_VIEW_API.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

TextView.widget_descriptor = WidgetDescriptor(
    family=TextView.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(TextView.inspect_spec, 'config', ()),
        state=TextView.inspect_spec.state,
        token_family=getattr(TextView.inspect_spec, 'token_family', ()),
        regions=getattr(TextView.inspect_spec, 'regions', False),
        layers=getattr(TextView.inspect_spec, 'layers', False),
        docs=getattr(TextView.inspect_spec, 'docs', ''),
        preview_seed=getattr(TextView.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(TextView.inspect_spec, 'apply_config_refresh', None),
    ),
)
