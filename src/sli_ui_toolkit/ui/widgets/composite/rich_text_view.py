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
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


class RichTextView(QWidget):
    """Word-wrapped rich text in a scrolling viewport; no stylesheet, no `QTextEdit`."""

    widget_descriptor: "WidgetDescriptor | None" = None

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        padding: tuple[int, int, int, int] = (10, 5, 10, 5),
        background_token: str | None = None,
        scrollbar_width: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._padding = tuple(max(0, int(value)) for value in padding)
        self._font_point_size: float | None = None
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

        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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

    def toPlainText(self) -> str:  # noqa: N802
        return self.label.text()

    def text(self) -> str:
        return self.label.text()

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
