"""Native Qt help document view (TOC chrome + unified body canvas)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.ui.widgets.composite.help_document.blocks import (
    HeadingBlock,
    HelpBlock,
    blocks_to_plain_text,
    collect_heading_anchors,
    parse_help_blocks,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.canvas import (
    HelpDocumentBodyCanvas,
    markdown_for_selection,
)

AssetResolver = Callable[[str], str | Path | QPixmap | None]


class HelpDocumentView(QWidget):
    """Scroll-friendly document with unified body selection.

    Emit ``linkActivated(href)`` for ``help://…``, ``#anchor``, and http(s).
    External http(s) are also opened via ``QDesktopServices`` unless
    ``open_external_links`` is False.
    """

    linkActivated = Signal(str)
    textContextMenuRequested = Signal(QPoint)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        resolve_asset: AssetResolver | None = None,
        open_external_links: bool = True,
        show_toc: bool = True,
        toc_title: str = "On this page",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HelpDocumentView")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._theme = ThemeManager.get_instance()
        self._resolve_asset = resolve_asset
        self._open_external_links = open_external_links
        self._show_toc = show_toc
        self._toc_title = toc_title
        self._blocks: tuple[HelpBlock, ...] = ()
        self._source_markdown: str = ""

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(20, 16, 20, 24)
        self._root.setSpacing(10)

        self._canvas = HelpDocumentBodyCanvas(self)
        self._root.addWidget(self._canvas, 1)
        self._canvas.linkActivated.connect(self._on_link)
        self._canvas.textContextMenuRequested.connect(self.textContextMenuRequested)
        self._canvas.set_asset_resolver(resolve_asset)

        self._theme.theme_changed.connect(self._repolish)

    def set_asset_resolver(self, resolver: AssetResolver | None) -> None:
        self._resolve_asset = resolver
        self._canvas.set_asset_resolver(resolver)

    def set_toc_title(self, title: str) -> None:
        self._toc_title = str(title)

    def set_show_toc(self, enabled: bool) -> None:
        self._show_toc = bool(enabled)

    def clear(self) -> None:
        self._blocks = ()
        self._source_markdown = ""
        toc = self.findChild(QFrame, "HelpDocumentToc")
        if toc is not None:
            toc.deleteLater()
        self._canvas.set_blocks(())

    def set_markdown(self, markdown: str) -> None:
        self._source_markdown = markdown
        self.set_blocks(parse_help_blocks(markdown))

    def source_markdown(self) -> str:
        """Original page markdown (for copy-as-Markdown)."""
        return self._source_markdown

    def plain_text(self) -> str:
        """Flattened page text (for copy when selection does not span widgets)."""
        if self._canvas.plain_text():
            return self._canvas.plain_text()
        return blocks_to_plain_text(self._blocks)

    def selected_plain_text(self) -> str:
        return self._canvas.selected_plain_text()

    def selected_markdown(self) -> str:
        source = self._source_markdown
        selected = self.selected_plain_text()
        if not source:
            return self.plain_text() if not selected else selected
        if not selected:
            return source
        return markdown_for_selection(selected, source)

    def select_all_text(self) -> None:
        """Select all text on the page."""
        self._canvas.select_all_text()

    def clear_selection(self) -> None:
        self._canvas.clear_selection()

    def set_blocks(self, blocks: tuple[HelpBlock, ...] | list[HelpBlock]) -> None:
        self._blocks = tuple(blocks)
        toc = self.findChild(QFrame, "HelpDocumentToc")
        if toc is not None:
            toc.deleteLater()
        if self._show_toc:
            self._maybe_add_toc()
        self._canvas.set_blocks(self._blocks)
        if self._root.indexOf(self._canvas) < 0:
            self._root.addWidget(self._canvas, 1)
        self._repolish()

    def scroll_to_anchor(self, anchor: str) -> QWidget | None:
        """Return the widget for ``anchor`` so a parent scroll area can ensure visible."""
        return self._canvas.anchor_widget(anchor)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._canvas.relayout()

    def _maybe_add_toc(self) -> None:
        h3_items = [
            (a, t)
            for a, t in collect_heading_anchors(self._blocks)
            if any(
                isinstance(b, HeadingBlock) and b.level == 3 and b.anchor == a
                for b in self._blocks
            )
        ]
        if len(h3_items) < 2:
            return
        frame = QFrame(self)
        frame.setObjectName("HelpDocumentToc")
        frame.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(
            Label(
                self._toc_title,
                variant="caption",
                bold=True,
                pixel_size=13,
                parent=frame,
            )
        )
        for anchor, title in h3_items:
            link = _LinkLabel(title, f"#{anchor}", parent=frame)
            link.clicked.connect(self._on_link)
            layout.addWidget(link, 0, Qt.AlignmentFlag.AlignTop)
        # Canvas is added in __init__; TOC must stay above body content.
        self._root.insertWidget(0, frame, 0, Qt.AlignmentFlag.AlignTop)

    def _on_link(self, href: str) -> None:
        self.linkActivated.emit(href)
        if self._open_external_links and href.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(href))

    def _repolish(self, *_args) -> None:
        toc = self.findChild(QFrame, "HelpDocumentToc")
        if toc is not None:
            sep = self._theme.try_get_color("help.separator")
            if sep is None or not sep.isValid():
                sep = self._theme.get_color("dialog.border")
            toc.setStyleSheet(
                "QFrame#HelpDocumentToc {"
                f"border: 1px solid {sep.name()};"
                "border-radius: 8px;"
                "background: transparent;"
                "}"
            )


class _LinkLabel(Label):
    clicked = Signal(str)

    def __init__(self, text: str, href: str, parent: QWidget | None = None) -> None:
        super().__init__(
            text,
            pixel_size=14,
            color_token="accent",
            word_wrap=False,
            elide=True,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            parent=parent,
        )
        self._href = href
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._href)
        super().mouseReleaseEvent(event)
