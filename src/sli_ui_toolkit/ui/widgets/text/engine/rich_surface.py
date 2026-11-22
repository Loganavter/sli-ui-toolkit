"""Rich (HTML) document content for ``Text(mode="document")``.

The document engine's markdown path renders parsed help blocks; a pane that
a host fed HTML (release notes, a system/video information panel) needs the
same rich text a ``QLabel`` renders — bold/italic, colours, tables, line
breaks, the lot — plus what the label never had: a blinking caret, drag
selection and Ctrl+C.

So the content of this surface is a real ``QTextDocument``: that IS the rich
layout Qt uses behind ``QLabel`` (``QLabelPrivate`` builds one for rich
text), which is why an HTML body keeps looking exactly as it did when the
label painted it. The surface owns the caret state Qt expects for a
read-only text view (a ``QTextCursor``) and paints selection + caret through
``QAbstractTextDocumentLayout.PaintContext`` — the same pass a stock
``QTextEdit`` uses, so the caret blinks at the layout's own cursor rect
rather than at a hand-computed x.

Editing is never enabled here: the surface only moves the cursor and the
selection, never inserts or deletes.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSizeF, Qt
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QFont,
    QPalette,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)

#: Paragraph separators ``QTextCursor.selectedText`` emits (U+2029).
_PARAGRAPH_SEPARATORS = ("\u2029", "\u2028")


class RichDocumentSurface:
    """A ``QTextDocument`` body with caret + selection, drawn inside a canvas.

    Coordinates are the canvas's widget space: the document is painted at
    ``inset`` (left, top), and laid out at ``outer_width - inset.left -
    inset.right`` — the inset is the host pane's padding, so the pane keeps
    owning its own text inset instead of inheriting the engine's page pad.
    """

    def __init__(self) -> None:
        self._document = QTextDocument()
        # The pane paints its own plate and applies the padding as an inset;
        # a document margin would double it.
        self._document.setDocumentMargin(0)
        self._cursor = QTextCursor(self._document)
        self._inset: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._width = 1
        self._font: QFont | None = None
        #: False after a click past the last glyph (same rule as code mode:
        #: empty space drops the caret instead of jumping it to the nearest
        #: position); any text click re-places it.
        self._caret_placed = True

    # -- content --------------------------------------------------------

    def set_html(self, html: str) -> None:
        self._document.setHtml(str(html))
        self._cursor = QTextCursor(self._document)
        self._caret_placed = True
        self._apply_width()

    def set_font(self, font: QFont) -> None:
        """Body font for text the HTML does not style itself."""
        self._font = QFont(font)
        self._document.setDefaultFont(self._font)
        self._apply_width()

    def font(self) -> QFont:
        if self._font is not None:
            return QFont(self._font)
        return QFont(self._document.defaultFont())

    def set_inset(self, inset: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = inset
        self._inset = (
            max(0, int(left)),
            max(0, int(top)),
            max(0, int(right)),
            max(0, int(bottom)),
        )
        self._apply_width()

    def inset(self) -> tuple[int, int, int, int]:
        return self._inset

    def set_outer_width(self, width: int) -> None:
        """Lay the document out at a widget width (insets included)."""
        self._width = max(1, int(width))
        self._apply_width()

    def _text_width(self) -> int:
        left, _top, right, _bottom = self._inset
        return max(1, self._width - left - right)

    def _apply_width(self) -> None:
        self._document.setTextWidth(self._text_width())

    def content_height(self) -> int:
        """Painted height of the laid-out body, insets included."""
        _left, top, _right, bottom = self._inset
        return int(round(self._document.size().height())) + top + bottom

    def plain_text(self) -> str:
        return self._document.toPlainText()

    def document(self) -> QTextDocument:
        return self._document

    # -- caret / selection ----------------------------------------------

    def has_selection(self) -> bool:
        return self._cursor.hasSelection()

    def selected_text(self) -> str:
        text = self._cursor.selectedText()
        for separator in _PARAGRAPH_SEPARATORS:
            text = text.replace(separator, "\n")
        return text

    def clear_selection(self) -> None:
        self._cursor.clearSelection()
        self._caret_placed = True

    def select_all(self) -> None:
        self._cursor.select(QTextCursor.SelectionType.Document)
        self._caret_placed = True

    def cursor_position(self) -> int:
        return self._cursor.position()

    def caret_placed(self) -> bool:
        return self._caret_placed

    def _local(self, point) -> QPointF:
        left, top, _right, _bottom = self._inset
        return QPointF(point) - QPointF(left, top)

    def _offset_at(self, point) -> int | None:
        """Document offset under a widget-space point (``None`` off the glyphs)."""
        layout = self._document.documentLayout()
        offset = layout.hitTest(self._local(point), Qt.HitTestAccuracy.FuzzyHit)
        if offset is None or offset < 0:
            return None
        return int(offset)

    def press(self, point) -> None:
        """Place the caret / anchor a selection at a widget-space point."""
        offset = self._offset_at(point)
        self._caret_placed = offset is not None
        if offset is None:
            self._cursor.clearSelection()
            return
        self._cursor.setPosition(offset)

    def select_word_at(self, point) -> None:
        """Double-click: select the word under a widget-space point."""
        offset = self._offset_at(point)
        if offset is None:
            return
        cursor = QTextCursor(self._document)
        cursor.setPosition(offset)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        if cursor.hasSelection():
            self._cursor = cursor
            self._caret_placed = True

    def drag_to(self, point) -> None:
        """Extend the selection toward a widget-space point (drag)."""
        offset = self._offset_at(point)
        if offset is None:
            # Past the last glyph: extend to the documented end rather than
            # freezing the selection mid-drag.
            offset = self._document.characterCount() - 1
        if self._cursor.hasSelection():
            anchor = self._cursor.anchor()
        else:
            anchor = self._cursor.position()
        self._cursor.setPosition(anchor)
        self._cursor.setPosition(offset, QTextCursor.MoveMode.KeepAnchor)
        self._caret_placed = True

    # -- painting -------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        *,
        focused: bool,
        caret_on: bool,
        text_color: QColor | None,
        selection_color: QColor,
    ) -> None:
        """Draw the body, its selection and (when asked) the caret."""
        left, top, _right, _bottom = self._inset
        painter.save()
        painter.translate(left, top)
        context = QAbstractTextDocumentLayout.PaintContext()
        if text_color is not None and text_color.isValid():
            context.palette.setColor(QPalette.ColorRole.Text, text_color)
        if self._cursor.hasSelection():
            highlight = QTextCharFormat()
            highlight.setBackground(selection_color)
            selection = QAbstractTextDocumentLayout.Selection()
            selection.cursor = self._cursor
            selection.format = highlight
            # PySide6-stubs omits the public ``selections`` member (C++: a
            # QVector<Selection> on the paint context).
            context.selections = [selection]  # type: ignore[attr-defined]
        caret_visible = (
            focused and caret_on and self._caret_placed and not self._cursor.hasSelection()
        )
        if caret_visible:
            context.cursorPosition = self._cursor.position()
        self._document.documentLayout().draw(painter, context)
        painter.restore()

    def size_hint(self) -> QSizeF:
        return self._document.size()
