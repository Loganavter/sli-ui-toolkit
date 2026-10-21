"""TextScrollArea — the scrolling host for a painted ``Text`` surface.

``Text`` is a plain widget and never scrolls (text-unification §1: "scrolling
composes outside"). A host that wants a scrolling code or document surface
composes one; this class is that composition, and it is where the retired
``TextView``'s HOST half survives: the toolkit scrollbar, the transparent
viewport pins, the rounded 1 px border over the visible area, and an optional
shelf-well fill behind the text.

It is not a second text implementation: text, selection, edit state and
document parsing all forward to the hosted ``Text``.

    host = TextScrollArea(source, mode="code")
    host.set_panel_fill(well_color)      # raised code surface
    host.enter_edit_mode()

``markdown_help_dialog`` does not need this class — its page is sized to its
content and the dialog's own scroll area scrolls the page.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen, QRegion
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.text import Text
from sli_ui_toolkit.ui.widgets.text.engine import constants as text_constants


class _FrameOverlay(QWidget):
    """Border-only overlay glued to the visible area of ``TextScrollArea``
    (transparent for mouse events): the scroll area paints nothing of its
    own behind its viewport, so the rounded frame is drawn ON TOP — the
    hosted ``Text`` shows through, the border frames the visible region."""

    def __init__(self, owner: "TextScrollArea"):
        super().__init__()
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, _event) -> None:  # noqa: N802
        self._owner._paint_frame(self)


class TextScrollArea(QScrollArea):
    """Scroll host for one painted ``Text`` (code or document mode).

    The rounded frame is an overlay glued to the visible viewport area and
    the scrollbar lives inside the widget, as the retired ``TextView`` did,
    so a migrated call site keeps its look and its scrolling; the text
    itself is the unified ``Text``.
    """

    changed = Signal()
    #: document mode: a link was clicked (href)
    linkActivated = Signal(str)
    #: document mode: an image was clicked (source asset path)
    imageActivated = Signal(str)

    def __init__(
        self,
        text: str = "",
        *,
        mode: str = "code",
        editable: bool = False,
        resolve_asset=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # The hosted Text is resized to the viewport (and stretched to it when
        # the content is shorter): the host follows the window instead of
        # expanding to a fixed content-derived size. Its own minimum height
        # (the painted content height) is what makes this area scroll.
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBar(MinimalistScrollBar())
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.text_widget = Text(
            text, mode=mode, editable=editable, resolve_asset=resolve_asset
        )
        self.text_widget.textChanged.connect(self.changed)
        self.text_widget.linkActivated.connect(self.linkActivated)
        self.text_widget.imageActivated.connect(self.imageActivated)
        self.setWidget(self.text_widget)
        # Stock QScrollArea viewports and setWidget-flipped content widgets
        # auto-fill the QPalette Window role, darker than the dialog surface
        # token the host paints — pin both transparent so the host surface
        # shows behind the frame overlay.
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self.viewport().setAutoFillBackground(False)
        self.viewport().setStyleSheet("background: transparent;")
        self.text_widget.setAutoFillBackground(False)
        # Transparency pin. ``setWidget`` / viewport re-polish flips the
        # content auto-fill back on, and per-widget palette/attribute pins do
        # not survive it — the widget stylesheet is the only override that
        # holds (same transparency-plumbing case as ``SurfaceScrollArea``).
        # This is not a visual style: the painter pipeline still owns the
        # text output.
        self.text_widget.setStyleSheet("background: transparent;")
        self._frame_visible = True
        self._overlay = _FrameOverlay(self)
        self._overlay.setParent(self)
        self._sync_overlay_geometry()
        self._overlay.raise_()

    # -- text surface (forwards to the hosted Text) -------------------------

    def text(self) -> str:
        return self.text_widget.text()

    def plain_text(self) -> str:
        """Full plain text of the current content (document or code)."""
        return self.text_widget.plain_text()

    def set_text(self, text: str) -> None:
        self.text_widget.setText(text)

    #: ``Text``'s camel-case spelling, accepted for call-site parity.
    setText = set_text

    def is_document(self) -> bool:
        return self.text_widget.mode() == "document"

    def set_markdown(self, markdown: str, *, resolve_asset=None) -> None:
        """Switch the hosted surface to document mode (markdown blocks)."""
        self.text_widget.set_markdown(markdown, resolve_asset=resolve_asset)
        self.verticalScrollBar().setValue(0)

    def anchor_y(self, anchor: str) -> int | None:
        """Content y of a heading anchor (``None`` when absent/not a document)."""
        return self.text_widget.anchor_y(anchor)

    def scroll_to_anchor(self, anchor: str) -> bool:
        """Scroll so ``anchor``'s heading sits at the top (``False`` when the
        anchor is unknown)."""
        y = self.text_widget.anchor_y(anchor)
        if y is None:
            return False
        bar = self.verticalScrollBar()
        bar.setValue(min(max(0, y), bar.maximum()))
        return True

    def canvas(self):
        """The painted surface (line math, gutter map, folds, hit-testing)."""
        return self.text_widget.canvas()

    def is_editing(self) -> bool:
        return self.text_widget.is_editing()

    def set_editing(self, editing: bool) -> None:
        self.text_widget.set_editing(bool(editing))

    def enter_edit_mode(self):
        """The painted buffer IS the editor — nothing is swapped, so the
        scroll position and rendering stay identical between modes. Returns
        the editing surface, as the retired composite did."""
        self.text_widget.set_editing(True)
        return self.text_widget.canvas()

    def exit_edit_mode(self) -> None:
        self.text_widget.set_editing(False)

    def editor(self):
        """The editing surface while editing (the painted canvas), else None."""
        return self.text_widget.canvas() if self.text_widget.is_editing() else None

    def set_line_number_start(self, start: int | None) -> None:
        """VS Code-style line-number gutter: the number of the first visible
        line; ``None`` disables the gutter."""
        self.text_widget.set_line_number_start(start)

    # -- host chrome --------------------------------------------------------

    def set_frame_visible(self, visible: bool) -> None:
        """Draw the rounded 1 px border over the visible area (default on)."""
        self._frame_visible = bool(visible)
        self._overlay.setVisible(self._frame_visible)
        self._overlay.update()

    def set_panel_fill(self, color: QColor | None) -> None:
        """Paint an opaque shelf-style rounded well behind the text.

        ``None`` restores the default transparent state (the host surface
        shows behind the frame overlay). Used by hosts that want the code
        surface to read as a raised panel (the inspector Code section), like
        the app's recent-projects shelf. This is the host's fill, not a text
        style — the hosted ``Text`` stays transparent on top of it.
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
            QRectF(viewport.rect()),
            text_constants.RADIUS,
            text_constants.RADIUS,
        )
        viewport.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_overlay_geometry()
        self._apply_panel_mask()

    def wheelEvent(self, event) -> None:  # noqa: N802
        # Coalesce high-frequency touchpad wheel events (Wayland/X11 smooth
        # scroll sends dozens of small deltas per second, each would repaint
        # the whole visible buffer). Accumulate and flush once per frame via
        # singleShot(0) — best-practice for code editors.
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

    def _flush_wheel(self) -> None:
        if not hasattr(self, "_wheel_accum") or self._wheel_accum == 0:
            return
        delta_px = self._wheel_accum
        self._wheel_accum = 0
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - delta_px)

    def _sync_overlay_geometry(self) -> None:
        # The frame encloses the whole widget, scrollbar included — the
        # scrollbar must sit INSIDE the rounded frame, not outside it.
        self._overlay.setGeometry(self.rect())

    def _paint_frame(self, target: QWidget) -> None:
        """Rounded border only — a fill here would cover the text underneath,
        and the host background already reads as the surface."""
        if not self._frame_visible:
            return
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = ThemeManager.get_instance()
        border = tm.try_get_color("separator.color")
        if border is None or not border.isValid():
            return
        rect = target.rect().adjusted(0, 0, -1, -1)
        painter.setPen(QPen(QColor(border), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect, text_constants.RADIUS, text_constants.RADIUS
        )


__all__ = ["TextScrollArea"]
