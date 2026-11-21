"""A scrolling rich-text pane: the toolkit's replacement for a read-only `QTextEdit`.

Three kinds of host pane are the same control seen from different call sites: a release-notes pane (`setMarkdown`), a
system-information panel (`setText` with lines) and a video-information panel (`setFontPointSize` + `setText` with
HTML). All three are a word-wrapped rich-text label inside a scroll area — which the toolkit can compose but had no
widget for, so hosts kept stock `QTextEdit`s and their stylesheets alive.

`RichTextView` composes an `OverlayScrollArea` (no surface of its own) with a variant `Label`, and exposes the calls
those hosts make. The label's height follows its wrapped content width, which is what makes a `QScrollArea` actually
scroll it: with ``widgetResizable`` the scroll area fixes the width and takes the widget's minimum height, and a
QLabel-derived widget does not report a wrapped height on its own.

    view = RichTextView(parent)
    view.setMarkdown(open("CHANGELOG.md").read())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.atomic.surface_panel import SurfacePanel
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


class RichTextView(SurfacePanel):
    """Word-wrapped rich text in a scrolling viewport, on a token-painted plate.

    The plate is the pane's own look (a `surface.list` fill with a 10 px radius is what a read-only editor carried in a
    stylesheet); it is a `SurfacePanel` so the colour comes from a token and the corners are painted, never styled.
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
    ) -> None:
        super().__init__(parent, background_token=background_token, radius=radius)
        self._padding = tuple(max(0, int(value)) for value in padding)
        self._font_point_size: float | None = None
        self._readonly_requested = True
        self._size_adjust_policy = None
        self._line_wrap_mode = None
        self._v_scroll_policy = None
        self._h_scroll_policy = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._scroll = OverlayScrollArea(self, reserve_scrollbar_space=True)
        if scrollbar_width is not None:
            self._scroll.set_scrollbar_width(scrollbar_width)
        self._scroll.setWidgetResizable(True)

        self.label = Label(variant="body", word_wrap=True, selectable=True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.label.setContentsMargins(*self._padding)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._scroll.setWidget(self.label)

        layout = QVBoxLayout(self)
        # The plate's radius needs the content off its corners, and a rounded plate must not have a square child
        # painting over it - the scroll area starts inside the same inset the radius implies.
        inset = max(0, int(radius))
        layout.setContentsMargins(inset, inset, inset, inset)
        layout.setSpacing(0)
        layout.addWidget(self._scroll)

    # -- content --------------------------------------------------------

    def setText(self, text: str) -> None:  # noqa: N802 - QTextEdit spelling
        """Plain text, or HTML when it looks like HTML (the same rule `QLabel` applies)."""
        body = str(text)
        if not body.lstrip().startswith("<"):
            body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.label.setText(body)
        self._sync_height()

    def setPlainText(self, text: str) -> None:  # noqa: N802
        self.setText(str(text).replace("<", "&lt;").replace(">", "&gt;"))

    def setHtml(self, html: str) -> None:  # noqa: N802
        self.label.setText(str(html))
        self._sync_height()

    def setMarkdown(self, markdown: str) -> None:  # noqa: N802
        """Render markdown through `QTextDocument` and show the resulting HTML."""
        document = QTextDocument()
        document.setMarkdown(str(markdown))
        self.label.setText(document.toHtml())
        self._sync_height()

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
        self.label.setText(self.label.text() + "<br>" + str(text))
        self._sync_height()

    def _plain(self) -> str:
        """The visible TEXT, not the stored markup.

        A host (and the host's structural dumper) asks a text pane for its plain text; returning the HTML source made a
        migrated pane report its whole markup as content - measured as a 22 % text difference on a page that paints the
        same words.
        """
        source = self.label.text()
        if "<" not in source:
            return source
        document = QTextDocument()
        document.setHtml(source)
        return document.toPlainText()

    def toPlainText(self) -> str:  # noqa: N802
        return self._plain()

    def text(self) -> str:
        return self._plain()

    def clear(self) -> None:
        self.setText("")

    # -- styling --------------------------------------------------------

    def setFontPointSize(self, point_size: float) -> None:  # noqa: N802 - QTextEdit spelling
        """A host that sizes its pane through the editor API gets the label's face sized instead."""
        self._font_point_size = float(point_size)
        font = QFont(self.label.font())
        font.setPointSizeF(float(point_size))
        self.label.setFont(font)
        self._sync_height()

    def padding(self) -> tuple[int, int, int, int]:
        return self._padding

    def set_padding(self, padding: tuple[int, int, int, int]) -> None:
        self._padding = tuple(max(0, int(value)) for value in padding)
        self.label.setContentsMargins(*self._padding)
        self._sync_height()

    # -- geometry -------------------------------------------------------

    def _sync_height(self) -> None:
        """Give the scroll area a wrapped height to scroll.

        `widgetResizable` fixes the width to the viewport; a label does not report the height it needs at that width,
        so it would be clipped instead of scrolled. `heightForWidth` at the current viewport width is that height.
        """
        width = max(1, self._scroll.viewport().width())
        height = self.label.heightForWidth(width)
        if height > 0:
            self.label.setMinimumHeight(height)
        self.label.updateGeometry()
        self._scroll.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._sync_height()


RichTextView.widget_descriptor = None
