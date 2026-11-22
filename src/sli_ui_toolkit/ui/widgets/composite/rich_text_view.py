"""A scrolling rich-text pane: the toolkit's replacement for a read-only `QTextEdit`.

Three kinds of host pane are the same control seen from different call sites: a release-notes pane (`setMarkdown`), a
system-information panel (`setText` with lines) and a video-information panel (`setFontPointSize` + `setText` with
HTML). All three are a word-wrapped rich-text body inside a scroll area.

The body is `Text(mode="document")`: the painted engine renders it (bold/italic/colour/tables exactly as the
`QLabel` that came before — the rich path IS Qt's own `QTextDocument`), and the engine's canvas owns the caret, the
drag selection and Ctrl+C. A `QLabel`-derived pane had none of those: selected text sat in a static wash with no
blinking caret, and the caret was still there after the pane lost focus.

    view = RichTextView(parent)
    view.setMarkdown(open("CHANGELOG.md").read())

The content height comes from the ENGINE (`canvas().minimumHeight()` after the body is laid out at the viewport
width), applied to the inner widget as a FIXED height: with ``widgetResizable`` the scroll area fixes the width and
asks the widget for the height it needs, and a plain hint for an HTML body is far taller than what it paints. A pane
whose body is shorter than the viewport must report a zero scroll range — "you can scroll it into emptiness" is the
regression this contract guards (owner report 2026-11-22).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_FONT, AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.atomic.surface_panel import SurfacePanel
from sli_ui_toolkit.ui.widgets.text.text import Text
from sli_ui_toolkit.ui.widgets.text.variants import get_text_variant

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


class RichTextView(SurfacePanel):
    """Word-wrapped rich text in a scrolling viewport, on a token-painted plate.

    The plate is the pane's own look (a `surface.list` fill with a 10 px radius is what a read-only editor carried in a
    stylesheet); it is a `SurfacePanel` so the colour comes from a token and the corners are painted, never styled.
    The body inside is a painted `Text(mode="document")` surface — the engine paints the text, so no block paints a
    surface of its own over the plate.
    """

    widget_descriptor: "WidgetDescriptor | None" = None

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        padding: tuple[int, int, int, int] = (10, 5, 10, 5),
        background_token: str | None = "surface.list",
        radius: int = 10,
        scrollbar_width: int | None = None,
        link_token: str = "dialog.text",
    ) -> None:
        super().__init__(parent, background_token=background_token, radius=radius)
        self._padding: tuple[int, int, int, int] = (
            max(0, int(padding[0])),
            max(0, int(padding[1])),
            max(0, int(padding[2])),
            max(0, int(padding[3])),
        )
        self._font_point_size: float | None = None
        self._pixel_size: int | None = None
        self._readonly_requested = True
        self._size_adjust_policy = None
        self._line_wrap_mode = None
        self._v_scroll_policy = None
        self._h_scroll_policy = None
        #: the markup the engine renders; `text()`/`toPlainText()` read the
        #: painted plain text, never this source
        self._markup = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._scroll = OverlayScrollArea(self, reserve_scrollbar_space=True)
        if scrollbar_width is not None:
            self._scroll.set_scrollbar_width(scrollbar_width)
        self._scroll.setWidgetResizable(True)

        # The painted rich body. Its canvas owns the caret, the selection and
        # the height; the pane owns the scroll host and the plate. The
        # attribute keeps the name hosts read when this pane was a `QLabel`.
        self.label = Text(mode="document")
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        engine = self.label.canvas()
        assert engine is not None  # mode="document" always hosts the engine
        engine.set_rich_inset(self._padding)
        self._apply_body_font()
        #: Links are painted with this token instead of Qt's palette Link role (a stock blue a monochrome host never
        #: chose), and they are clickable: the surface hit-tests an anchor on release and `Text` opens it.
        self._link_token = str(link_token)
        self._scroll.setWidget(self.label)
        self._apply_link_color()

        layout = QVBoxLayout(self)
        # The plate's radius needs the content off its corners, and a rounded plate must not have a square child
        # painting over it - the scroll area starts inside the same inset the radius implies.
        inset = max(0, int(radius))
        layout.setContentsMargins(inset, inset, inset, inset)
        layout.setSpacing(0)
        layout.addWidget(self._scroll)
        connect_ui_metrics(
            self,
            self._on_ui_metrics_changed,
            axes=frozenset({AXIS_FONT, AXIS_SCALE}),
        )

    # -- content --------------------------------------------------------

    def setText(self, text: str) -> None:  # noqa: N802 - QTextEdit spelling
        """Plain text, or HTML when it looks like HTML (the same rule `QLabel` applies)."""
        body = str(text)
        if body.lstrip().startswith("<"):
            self._set_markup(body)
            return
        self.setPlainText(body)

    def setPlainText(self, text: str) -> None:  # noqa: N802
        body = (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        self._set_markup(body)

    def setHtml(self, html: str) -> None:  # noqa: N802
        self._set_markup(str(html))

    def setMarkdown(self, markdown: str) -> None:  # noqa: N802
        """Render markdown through `QTextDocument` and show the resulting HTML."""
        document = QTextDocument()
        document.setMarkdown(str(markdown))
        self.setHtml(document.toHtml())

    def setReadOnly(self, read_only: bool) -> None:  # noqa: N802
        """No-op: the pane is a read-only view. Present so a migrated `QTextEdit` keeps the Designer's call."""
        self._readonly_requested = bool(read_only)

    def setVerticalScrollBarPolicy(self, policy) -> None:  # noqa: N802
        """No-op: the pane's overlay bar appears when the content overflows."""
        self._v_scroll_policy = policy

    def setHorizontalScrollBarPolicy(self, policy) -> None:  # noqa: N802
        """No-op: the pane wraps text and never scrolls horizontally."""
        self._h_scroll_policy = policy

    def setSizeAdjustPolicy(self, policy) -> None:  # noqa: N802
        """No-op: the pane sizes itself from its viewport; present for a migrated `QTextEdit`/`QScrollArea` call."""
        self._size_adjust_policy = policy

    def setLineWrapMode(self, mode) -> None:  # noqa: N802
        """No-op: the content always wraps (``WidgetWidth`` is the only mode a pane needs)."""
        self._line_wrap_mode = mode

    def setStyleSheet(self, sheet: str) -> None:  # noqa: N802
        """Refuse styling the way every toolkit widget does - the look is painted, not styled."""
        if sheet and sheet.strip():
            raise ValueError("RichTextView paints its look from tokens; a stylesheet would be silently ignored")

    def verticalScrollBar(self):  # noqa: N802
        """The overlay bar, so a host that pins a pane to the bottom keeps working."""
        return self._scroll.verticalScrollBar()

    def append(self, text: str) -> None:
        """Append one line, the way a log/notes pane is fed."""
        self._set_markup(self._markup + "<br>" + str(text))

    def _apply_link_color(self) -> None:
        from sli_ui_toolkit.theme import ThemeManager

        colour = ThemeManager.get_instance().try_get_color(self._link_token)
        if colour is not None and colour.isValid():
            self.label.set_rich_link_color(QColor(colour))

    def _set_markup(self, markup: str) -> None:
        self._markup = markup
        self.label.set_html(markup)
        self._apply_link_color()
        self._sync_height()

    def toPlainText(self) -> str:  # noqa: N802
        """The visible TEXT, not the stored markup.

        A host (and the host's structural dumper) asks a text pane for its plain text; returning the HTML source made a
        migrated pane report its whole markup as content - measured as a 22 % text difference on a page that paints the
        same words.
        """
        return self.label.text()

    def text(self) -> str:
        return self.toPlainText()

    def clear(self) -> None:
        self.setText("")

    # -- styling --------------------------------------------------------

    def setFontPointSize(self, point_size: float) -> None:  # noqa: N802 - QTextEdit spelling
        """A host that sizes its pane through the editor API gets the body's face sized instead."""
        self._font_point_size = float(point_size)
        self._apply_body_font()

    def setTextPixelSize(self, pixel_size: int) -> None:  # noqa: N802
        """Size the text in PIXELS.

        A host whose design states pixel sizes (RVE: 12 px controls) cannot use `setFontPointSize`, which converts
        through the screen DPI (12 pt became 16 px and every line of a migrated pane grew) - the same trap the toolkit's
        spin boxes had with the locale.
        """
        self._pixel_size = max(1, int(pixel_size))
        self._apply_body_font()

    def padding(self) -> tuple[int, int, int, int]:
        return self._padding

    def set_padding(self, padding: tuple[int, int, int, int]) -> None:
        self._padding = (
            max(0, int(padding[0])),
            max(0, int(padding[1])),
            max(0, int(padding[2])),
            max(0, int(padding[3])),
        )
        engine = self.label.canvas()
        if engine is not None:
            engine.set_rich_inset(self._padding)
        self._sync_height()

    def _body_font(self) -> QFont:
        """The pane's body face: the ``body`` variant size, or a host-pinned one."""
        spec = get_text_variant("body")
        font = ui_font(pixel_size=self._pixel_size or spec.pixel_size)
        if self._font_point_size is not None:
            font.setPointSizeF(self._font_point_size)
        return font

    def _apply_body_font(self) -> None:
        engine = self.label.canvas()
        if engine is not None:
            engine.set_rich_font(self._body_font())
        self._sync_height()

    def _on_ui_metrics_changed(self, *_args: object) -> None:
        """A host font/scale change re-resolves the body face and the height.

        Resolved even when a host pinned a point/pixel size: the family and
        the scale factor still come from the bus, only the size is pinned.
        """
        self._apply_body_font()

    # -- geometry -------------------------------------------------------

    def _sync_height(self) -> None:
        """Give the scroll area the engine's content height, as a fixed height.

        `widgetResizable` fixes the width to the viewport, and the height has to come from the engine: the rich body
        is laid out in a `QTextDocument`, whose own `sizeHint` for an HTML body is far taller than what it paints
        (measured: 2844 px claimed, 1776 px of ink) - the pane then scrolls through pages of nothing.
        """
        engine = self.label.canvas()
        if engine is None:
            return
        width = max(1, self._scroll.viewport().width())
        # Lay the body out at the width it will actually be painted at. The
        # viewport has not been resized yet when this runs from a resize
        # event, so the deferred pass measures against the real width.
        engine.resize(width, engine.height())
        engine.relayout_rich(width)
        height = engine.minimumHeight()
        if height > 0:
            self.label.setFixedHeight(height)
        self.label.updateGeometry()
        self._scroll.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._sync_height()
        # The viewport has not been resized yet when this fires: one turn
        # later it has, and the body is measured against the width the text
        # will actually be laid out at (measuring a body against a stale
        # narrow viewport was exactly the empty-scroll defect).
        QTimer.singleShot(0, self._sync_height)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._sync_height()


RichTextView.widget_descriptor = None
