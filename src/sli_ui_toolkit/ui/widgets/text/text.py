"""Unified painted text display widget.

``Text`` is one ``QWidget`` configured by keyword arguments or a frozen
``TextConfig``. ``mode="plain"`` is the ``Label`` replacement; ``document``
hosts the markdown help engine and ``code`` the editable painted buffer.
Hosts compose scrolling, TOC and the image lightbox *outside* the widget
(``docs/dev/TEXT_UNIFICATION.md`` §1/§4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, QTextBoundaryFinder, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDesktopServices,
    QFontMetrics,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPalette,
    QRegion,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.i18n import get_current_language, translator_for
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.managers.ui_font import apply_text_color, ui_font
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_FONT, AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.widgets.atomic.label_context_menu import (
    open_label_context_menu,
)
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import (
    draw_marquee_text,
    ensure_marquee_driver,
    text_overflows,
)
from sli_ui_toolkit.ui.widgets.text.engine.canvas import TextCanvasCore
from sli_ui_toolkit.ui.widgets.text.engine.document_canvas import markdown_for_selection
from sli_ui_toolkit.ui.widgets.text.plain import (
    build_layout,
    hit_glyph,
    hit_test,
    selection_rects,
)
from sli_ui_toolkit.ui.widgets.text.variants import TextVariantSpec, get_text_variant

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor

_PLAIN = "plain"
_ENGINE_MODES = ("document", "code")
_NO_WRAP_EXTENT = 1 << 20


@dataclass(frozen=True)
class TextConfig:
    """Declarative ``Text`` configuration (alternative to keyword arguments)."""

    text: str = ""
    mode: str = _PLAIN
    variant: str = "body"
    family: str | None = None
    pixel_size: int | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike_out: bool | None = None
    color: QColor | None = None
    color_token: str | None = None
    alignment: Qt.AlignmentFlag = (
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
    )
    elide: bool | None = None
    marquee: bool | None = None
    minimum_width: int | None = None
    expanding: bool | None = None
    word_wrap: bool | None = None
    selectable: bool = False
    editable: bool = False
    resolve_asset: Any = None
    open_external_links: bool = True
    text_key: str | None = None

    def to_kwargs(self) -> dict[str, Any]:
        """Field values keyed by the ``Text.__init__`` kwarg they override."""
        return {
            "text": self.text,
            "mode": self.mode,
            "variant": self.variant,
            "family": self.family,
            "pixel_size": self.pixel_size,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "strike_out": self.strike_out,
            "color": self.color,
            "color_token": self.color_token,
            "alignment": self.alignment,
            "elide": self.elide,
            "marquee": self.marquee,
            "minimum_width": self.minimum_width,
            "expanding": self.expanding,
            "word_wrap": self.word_wrap,
            "selectable": self.selectable,
            "editable": self.editable,
            "resolve_asset": self.resolve_asset,
            "open_external_links": self.open_external_links,
            "text_key": self.text_key,
        }


def _require_mode(mode: str) -> None:
    if mode == _PLAIN or mode in _ENGINE_MODES:
        return
    raise ValueError(f'unknown Text mode {mode!r}; expected "plain", "document" or "code"')


class Text(QWidget):
    """Painted text display. Plain mode matches ``Label`` typography and behavior."""

    selectionChanged = Signal()
    textChanged = Signal()
    linkActivated = Signal(str)
    imageActivated = Signal(str)
    #: right-click, global position (emitted in every mode)
    textContextMenuRequested = Signal(QPoint)

    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar[WidgetDescriptor]

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        mode: str = _PLAIN,
        variant: str = "body",
        family: str | None = None,
        pixel_size: int | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strike_out: bool | None = None,
        color: QColor | None = None,
        color_token: str | None = None,
        alignment: Qt.AlignmentFlag = (
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        ),
        elide: bool | None = None,
        marquee: bool | None = None,
        minimum_width: int | None = None,
        expanding: bool | None = None,
        word_wrap: bool | None = None,
        selectable: bool = False,
        editable: bool = False,
        resolve_asset: Any = None,
        open_external_links: bool = True,
        config: TextConfig | None = None,
        # Appended AFTER ``config`` so an existing positional ``config=`` call
        # site keeps its slot (new params are append-only).
        text_key: str | None = None,
    ):
        if config is not None:
            text = config.text
            mode = config.mode
            variant = config.variant
            family = config.family
            pixel_size = config.pixel_size
            bold = config.bold
            italic = config.italic
            underline = config.underline
            strike_out = config.strike_out
            color = config.color
            color_token = config.color_token
            alignment = config.alignment
            elide = config.elide
            marquee = config.marquee
            minimum_width = config.minimum_width
            expanding = config.expanding
            word_wrap = config.word_wrap
            selectable = config.selectable
            editable = config.editable
            resolve_asset = config.resolve_asset
            open_external_links = config.open_external_links
            text_key = config.text_key

        _require_mode(mode)
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._mode = mode
        self._engine: TextCanvasCore | None = None
        self._variant_name = variant
        self._family_override = family
        self._pixel_size_override = pixel_size
        self._bold_override = bold
        self._italic_override = italic
        self._underline_override = underline
        self._strike_out_override = strike_out
        self._color_override = QColor(color) if color is not None else None
        self._color_token_override = color_token
        self._elide_override = elide
        self._marquee_enabled = bool(marquee) if marquee is not None else False
        self._minimum_width_override = minimum_width
        self._expanding_override = expanding
        self._word_wrap = bool(word_wrap) if word_wrap is not None else False
        self._alignment = alignment
        self._original_text = text
        self._display_text = text
        self._text_key: str | None = None
        self._selectable = False
        self._sel_anchor = 0
        self._sel_cursor = 0
        self._dragging = False
        self._hover_ibeam: bool | None = None
        self._applying_style = False
        self._resolve_asset = resolve_asset
        self._open_external_links = bool(open_external_links)
        #: markdown the document content was last set from (``set_blocks``
        #: carries no source, so it clears this instead of lying)
        self._source_markdown: str = text if mode == "document" else ""
        self._panel_fill = False
        #: document wheel policy: at the host scroll edge, forward the wheel
        #: to the next scroller (True) or keep it (False) — see
        #: ``set_wheel_edge_forwarding``
        self._wheel_edge_forwarding = True

        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        # One subscription: both font and scale must re-resolve the text
        # style (``_apply_style`` reads ``ui_font()`` per call).
        connect_ui_metrics(
            self, self._on_scale_changed, axes=frozenset({AXIS_FONT, AXIS_SCALE})
        )
        if mode in _ENGINE_MODES:
            self._build_engine(mode, text, editable, resolve_asset)
        self._apply_style()
        if selectable and self._engine is None:
            self.setSelectable(True)
        if text_key is not None:
            self.setTextKey(text_key)

    def _build_engine(
        self, mode: str, text: str, editable: bool, resolve_asset: Any
    ) -> None:
        """Host the painted engine (``TextCanvasCore``) as the single child that
        fills this widget. Scrolling stays with the host."""
        engine = TextCanvasCore("" if mode == "document" else text)
        engine.setParent(self)
        self._engine = engine
        engine.changed.connect(self.textChanged)
        engine.linkActivated.connect(self._on_engine_link)
        engine.imageActivated.connect(self.imageActivated)
        engine.selectionChanged.connect(self.selectionChanged)
        engine.contentHeightChanged.connect(self._on_engine_content_height)
        if mode == "document":
            engine.set_document(text, resolve_asset=resolve_asset)
            # The wheel-at-edge policy must see the event before the engine's
            # default (ignoring) handler — see ``_wheel_at_host_edge``.
            engine.installEventFilter(self)
        elif editable:
            engine.set_editing(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        engine.setGeometry(self.rect())

    def _engine_for(self, mode: str) -> TextCanvasCore:
        if self._engine is None or self._mode != mode:
            raise RuntimeError(f'operation requires mode="{mode}", not "{self._mode}"')
        return self._engine

    def mode(self) -> str:
        return self._mode

    def text(self) -> str:
        if self._engine is not None:
            return self._engine.plain_text()
        return self._display_text

    def setText(self, text: str) -> None:
        if self._engine is not None:
            if self._mode == "document":
                self._source_markdown = text
                self._engine.set_document(text, resolve_asset=self._resolve_asset)
            else:
                self._engine.set_text(text)
            self.update()
            return
        self._original_text = text
        self._clear_selection()
        self._update_display_text()
        self.updateGeometry()
        self.update()

    def get_original_text(self) -> str:
        return self._original_text

    # -------- public API: declarative translation key --------

    def setTextKey(self, key: str | None) -> None:
        """Attach (or clear) a translation key; the key wins over the literal."""
        self._text_key = key
        if key is not None:
            self.retranslate(get_current_language())

    def set_translator(self, tr_func, *, defer_when_hidden: bool = False) -> None:
        """Duck-typed protocol hook used by ``bind_translator``/``install_translator``."""
        self._sli_translator = tr_func
        self._sli_defer_when_hidden = defer_when_hidden

    def retranslate(self, lang: str) -> None:
        """Re-resolve ``text_key`` through ``translator_for(self)`` at *lang*."""
        if self._text_key is None:
            return
        self.setText(translator_for(self)(self._text_key, lang))

    def invalidate_size_cache(self) -> None:
        self.updateGeometry()

    def variant(self) -> str:
        return self._variant_name

    def setVariant(self, variant: str) -> None:
        self._variant_name = str(variant or "body")
        self._apply_style()

    def setTextColor(self, color: QColor | None) -> None:
        self._color_override = QColor(color) if color is not None else None
        self._apply_style()

    def setColorToken(self, token: str | None) -> None:
        self._color_token_override = token
        self._apply_style()

    def setPixelSize(self, size: int | None) -> None:
        self._pixel_size_override = max(1, int(size)) if size is not None else None
        self._apply_style()

    def setFamily(self, family: str | None) -> None:
        self._family_override = family
        self._apply_style()

    def setBold(self, enabled: bool | None) -> None:
        self._bold_override = enabled
        self._apply_style()

    def setItalic(self, enabled: bool | None) -> None:
        self._italic_override = enabled
        self._apply_style()

    def setUnderline(self, enabled: bool | None) -> None:
        self._underline_override = enabled
        self._apply_style()

    def setStrikeOut(self, enabled: bool | None) -> None:
        self._strike_out_override = enabled
        self._apply_style()

    def alignment(self) -> Qt.AlignmentFlag:
        return self._alignment

    def setAlignment(self, alignment: Qt.AlignmentFlag) -> None:
        self._alignment = alignment
        self.updateGeometry()
        self.update()

    def wordWrap(self) -> bool:
        return self._word_wrap

    def setWordWrap(self, on: bool) -> None:
        self._word_wrap = bool(on)
        policy = self.sizePolicy()
        policy.setVerticalPolicy(self._vertical_policy())
        policy.setHeightForWidth(self._word_wrap)
        self.setSizePolicy(policy)
        self._update_display_text()
        self.updateGeometry()
        self.update()

    def setElide(self, enabled: bool | None) -> None:
        self._elide_override = enabled
        self._apply_style()

    def setMinimumWidth(self, width: int) -> None:
        self._minimum_width_override = max(0, int(width))
        super().setMinimumWidth(width)
        self.updateGeometry()

    def setMarquee(self, enabled: bool) -> None:
        self._marquee_enabled = bool(enabled)
        if self._marquee_enabled:
            ensure_marquee_driver(self)
        else:
            driver = getattr(self, "_marquee_driver", None)
            if driver is not None:
                driver.set_active(False)
        self._update_display_text()
        self.update()

    def marquee(self) -> bool:
        return bool(getattr(self, "_marquee_enabled", False))

    def setSelectable(self, enabled: bool) -> None:
        self._selectable = bool(enabled)
        if self._selectable:
            self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            self.setMouseTracking(True)
            self._hover_ibeam = None
            self._update_hover_cursor(QPointF(-1, -1))
        else:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.setMouseTracking(False)
            self._hover_ibeam = None
            self.unsetCursor()
            self._clear_selection()

    def isSelectable(self) -> bool:
        return self._selectable

    def hasSelectedText(self) -> bool:
        if self._engine is not None:
            return bool(self._engine.selected_plain_text())
        start, end = self._selection_bounds()
        return start != end

    def selectedText(self) -> str:
        if self._engine is not None:
            return self._engine.selected_plain_text()
        start, end = self._selection_bounds()
        return self._display_text[start:end]

    def selected_plain_text(self) -> str:
        return self.selectedText()

    def selected_markdown(self, source_markdown: str) -> str:
        """Document mode: the source-markdown slice covering the selection."""
        self._engine_for("document")
        return markdown_for_selection(self.selected_plain_text(), source_markdown)

    def select_all_text(self) -> None:
        self.selectAll()

    def clear_selection(self) -> None:
        if self._engine is not None:
            self._engine.reset_selection()
            return
        self._clear_selection()

    def setSelection(self, start: int, length: int) -> None:
        text_length = len(self._display_text)
        if start < 0 or start > text_length or length <= 0:
            self._clear_selection()
            return
        self._set_selection_range(start, min(text_length, start + length))

    def selectAll(self) -> None:
        if self._engine is not None:
            self._engine.select_all_text()
            return
        self.setSelection(0, len(self._display_text))

    def set_markdown(self, markdown: str, *, resolve_asset: Any = None) -> None:
        """Document mode: replace the content with markdown blocks."""
        engine = self._engine_for("document")
        if resolve_asset is not None:
            self._resolve_asset = resolve_asset
        self._source_markdown = markdown
        engine.set_document(markdown, resolve_asset=self._resolve_asset)

    def source_markdown(self) -> str:
        """Document mode: the markdown the content was last set from.

        Empty after ``set_blocks`` — parsed blocks carry no source, and
        returning a stale page would make copy-as-Markdown lie.
        """
        return self._source_markdown

    def plain_text(self) -> str:
        """Full flattened text in every mode (document: block text, no markup).

        Same value ``text()`` reports for engine modes; named after the
        ``HelpDocumentView`` accessor callers migrate from.
        """
        return self.text()

    def anchor_y(self, anchor: str) -> int | None:
        """Document mode: content y of a heading anchor (``None`` if absent)."""
        return self._engine_for("document").anchor_y(anchor)

    def scroll_to_anchor(self, anchor: str) -> int | None:
        """Document mode: y a host scroll area should scroll to for ``anchor``.

        Same coordinate space and anchor ids as :meth:`anchor_y` (widget
        space, heading ids parsed from the markdown); ``None`` when the
        anchor is unknown. The host scrolls — ``Text`` never does.
        """
        return self.anchor_y(anchor)

    def is_editing(self) -> bool:
        return self._engine is not None and self._engine.is_editing()

    def set_editing(self, editing: bool) -> None:
        """Code mode: switch the painted buffer between read and edit."""
        self._engine_for("code").set_editing(bool(editing))

    def set_line_number_start(self, start: int | None) -> None:
        self._engine_for("code").set_line_number_start(start)

    def set_blocks(self, blocks) -> None:
        """Document mode: replace the content with parsed help blocks."""
        self._engine_for("document").set_blocks(
            blocks, resolve_asset=self._resolve_asset
        )
        self._source_markdown = ""

    def set_resolve_asset(self, resolver: Any) -> None:
        """Asset resolver for inline images (ctor kwarg and setter agree)."""
        self._resolve_asset = resolver
        if self._engine is not None and self._mode == "document":
            self._engine.set_asset_resolver(resolver)

    def set_asset_resolver(self, resolver: Any) -> None:
        """Alias of :meth:`set_resolve_asset` (``HelpDocumentView`` spelling)."""
        self.set_resolve_asset(resolver)

    def set_open_external_links(self, enabled: bool) -> None:
        self._open_external_links = bool(enabled)

    def set_panel_fill(self, enabled: bool) -> None:
        """Paint the theme surface behind the engine content (default off).

        The host document page reads as a panel instead of showing the
        stock scroll-area ``Window`` substrate through the transparent
        painted body. Engine modes only — plain mode keeps ``Label``'s
        background contract (the host widget's own surface).
        """
        enabled = bool(enabled)
        if enabled == self._panel_fill:
            return
        self._panel_fill = enabled
        self.update()

    @property
    def panel_fill(self) -> bool:
        """Whether the theme surface is painted behind engine content."""
        return self._panel_fill

    def size_hint_from_content(self) -> QSize:
        """Document mode: painted content size at the current width.

        Height covers the full painted extent (top and bottom padding
        included) — the value a host scroll area needs to size the page
        without waiting for a layout round-trip.
        """
        engine = self._engine_for("document")
        width = self.width()
        if width <= 1:
            width = engine.sizeHint().width()
        return QSize(width, engine.minimumHeight())

    def set_wheel_edge_forwarding(self, enabled: bool) -> None:
        """Document mode: who owns the wheel once the host is at its edge.

        ``enabled`` (default) leaves the edge wheel unswallowed, so the
        host scroll area chains it to the next scroller (nested dialogs,
        outer pages). Disable it when the document must keep the wheel
        even at its edge instead of scrolling something behind it.
        """
        self._wheel_edge_forwarding = bool(enabled)

    def scroll_to_text(self, query: str) -> int | None:
        """Document mode: highlight the first match of ``query`` and return
        the widget-space y to scroll to (``None`` when absent)."""
        return self._engine_for("document").scroll_to_text(query)

    def _on_engine_link(self, href: str) -> None:
        self.linkActivated.emit(href)
        if self._open_external_links and href.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(href))

    def _on_engine_content_height(self) -> None:
        if self._engine is not None:
            self.setMinimumHeight(self._engine.minimumHeight())
        self.updateGeometry()

    def minimumSizeHint(self):
        if self._engine is not None:
            return QSize(0, self._engine.minimumHeight())
        if self._word_wrap:
            size = self._widest_word_size()
        else:
            size = self._text_size(-1, 0)
        if self._minimum_width() > 0:
            size.setWidth(self._minimum_width())
        return size

    def sizeHint(self):
        if self._engine is not None:
            return QSize(0, self._engine.minimumHeight())
        size = self._text_size(-1, 0)
        if self._uses_elide():
            width = max(
                QFontMetrics(self.font()).horizontalAdvance(self._original_text) + 10,
                self._minimum_width(),
            )
            size.setWidth(width)
        return size

    def hasHeightForWidth(self) -> bool:
        return self._word_wrap

    def heightForWidth(self, width: int) -> int:
        flags = int(Qt.TextFlag.TextWordWrap) if self._word_wrap else 0
        return self._text_size(max(0, width), flags).height()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._engine is not None:
            if self._panel_fill:
                painter = QPainter(self)
                painter.fillRect(self.rect(), self._panel_color())
                painter.end()
            return
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self._display_text
        if self._marquee_enabled and text_overflows(
            QFontMetrics(self.font()), self._original_text, rect.width()
        ):
            marquee = ensure_marquee_driver(self)
            marquee.set_active(True)
            painter.setFont(self.font())
            painter.setPen(self.palette().color(self.foregroundRole()))
            draw_marquee_text(painter, rect, self._original_text, marquee.phase)
            painter.end()
            return

        idle_marquee = getattr(self, "_marquee_driver", None)
        if idle_marquee is not None:
            idle_marquee.set_active(False)

        flags = self._text_flags()
        start, end = self._selection_bounds()
        if not text or start == end:
            self.style().drawItemText(
                painter,
                rect,
                flags,
                self.palette(),
                self.isEnabled(),
                text,
                self.foregroundRole(),
            )
            painter.end()
            return

        layout = self._layout(rect.width())
        origin = QPointF(rect.x(), self._text_top(rect, flags))
        highlight = self.palette().color(QPalette.ColorRole.Highlight)
        regions = QRegion()
        for sel in selection_rects(layout, start, end, origin):
            painter.fillRect(sel, highlight)
            regions = regions.united(QRegion(sel.toAlignedRect()))

        painter.setClipRegion(QRegion(rect).subtracted(regions))
        self.style().drawItemText(
            painter,
            rect,
            flags,
            self.palette(),
            self.isEnabled(),
            text,
            self.foregroundRole(),
        )
        selected_palette = QPalette(self.palette())
        selected_palette.setColor(
            QPalette.ColorRole.WindowText,
            self.palette().color(QPalette.ColorRole.HighlightedText),
        )
        painter.setClipRegion(regions)
        self.style().drawItemText(
            painter,
            rect,
            flags,
            selected_palette,
            self.isEnabled(),
            text,
            QPalette.ColorRole.WindowText,
        )
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._selectable and event.button() == Qt.MouseButton.LeftButton:
            position = self._hit(event.position())
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._extend_selection_to(position)
            else:
                self._set_selection_range(position, position)
            self._dragging = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging and self._selectable:
            self._extend_selection_to(self._hit(event.position()))
            event.accept()
            return
        if self._selectable:
            self._update_hover_cursor(event.position())
        super().mouseMoveEvent(event)

    def _update_hover_cursor(self, position: QPointF) -> None:
        """I-beam iff the pointer is over a glyph, Arrow otherwise."""
        rect = self.contentsRect()
        layout = self._layout(rect.width())
        origin = QPointF(rect.x(), self._text_top(rect, self._text_flags()))
        local = QPointF(position.x() - origin.x(), position.y() - origin.y())
        want_beam = self._display_text != "" and hit_glyph(layout, local)
        if want_beam == self._hover_ibeam:
            return
        self._hover_ibeam = want_beam
        self.setCursor(
            Qt.CursorShape.IBeamCursor if want_beam else Qt.CursorShape.ArrowCursor
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._selectable and event.button() == Qt.MouseButton.LeftButton:
            start, end = self._word_bounds(self._hit(event.position()))
            self._set_selection_range(start, end)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if not self._selectable or not self._display_text:
            super().keyPressEvent(event)
            return
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        key = event.key()
        if ctrl and key == Qt.Key.Key_A:
            self.selectAll()
        elif ctrl and key in (Qt.Key.Key_C, Qt.Key.Key_Insert):
            if self.hasSelectedText():
                QGuiApplication.clipboard().setText(self.selectedText())
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
            cursor = self._sel_cursor
            length = len(self._display_text)
            if key == Qt.Key.Key_Left:
                cursor = max(0, cursor - 1)
            elif key == Qt.Key.Key_Right:
                cursor = min(length, cursor + 1)
            elif key == Qt.Key.Key_Home:
                cursor = 0
            else:
                cursor = length
            if shift:
                self._extend_selection_to(cursor)
            else:
                self._set_selection_range(cursor, cursor)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self.textContextMenuRequested.emit(event.globalPos())
        if self._selectable and self._display_text:
            # Menu helper is annotated QLabel but only uses the selection API Text mirrors.
            open_label_context_menu(self, event.globalPos())  # type: ignore[arg-type]
            event.accept()
            return
        super().contextMenuEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._engine is not None:
            self._engine.setGeometry(self.rect())
            return
        self._update_display_text()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        """Document mode: apply the wheel-edge policy before the engine's
        default (ignoring) handler runs."""
        if (
            obj is self._engine
            and self._mode == "document"
            and event.type() == QEvent.Type.Wheel
            and not self._wheel_edge_forwarding
            and self._wheel_at_host_edge(event)
        ):
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def _wheel_at_host_edge(self, event) -> bool:
        """True when the host scroll area cannot move the way the wheel asks."""
        from PySide6.QtWidgets import QScrollArea

        widget: QWidget | None = self.parentWidget()
        while widget is not None and not isinstance(widget, QScrollArea):
            widget = widget.parentWidget()
        if widget is None:
            return False
        bar = widget.verticalScrollBar()
        if bar is None:
            return False
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            return False
        return bar.value() <= bar.minimum() if delta > 0 else bar.value() >= bar.maximum()

    def hideEvent(self, event) -> None:  # noqa: N802
        driver = getattr(self, "_marquee_driver", None)
        if driver is not None:
            driver.set_active(False)
        super().hideEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        et = event.type()
        if et == QEvent.Type.ApplicationFontChange:
            self._apply_style()
            return
        # Reparent / style polish can wipe WA_SetPalette text colors.
        if et in (QEvent.Type.ParentChange, QEvent.Type.StyleChange):
            self._apply_style()

    def _on_scale_changed(self, *_args: object) -> None:
        self._apply_style()

    def _on_theme_changed(self) -> None:
        """Theme flip: recolor only — skip font/geometry rebuild."""
        if self._engine is not None:
            self._engine.set_text_color(self._explicit_color())
            if self._panel_fill:
                self.update()
            return
        if self._applying_style:
            return
        self._applying_style = True
        try:
            spec = get_text_variant(self._variant_name)
            apply_text_color(self, self._resolve_color(spec))
            self.update()
        finally:
            self._applying_style = False

    def _apply_engine_style(self) -> None:
        """Engine modes: typography and explicit color reach the painted engine.

        Variant ``pixel_size``/``bold`` apply in code mode (its default size is
        the variant's); document mode takes only explicit ``pixel_size``/
        ``family`` because its body size is the document design size. Color is
        explicit-only (``color``/``color_token``): the variant's token would
        otherwise recolor the engine's default foreground.
        """
        engine = self._engine
        if engine is None:
            return
        if self._mode == "document":
            engine.set_body_style(
                pixel_size=self._pixel_size_override, family=self._family_override
            )
        else:
            spec = get_text_variant(self._variant_name)
            engine.set_font_style(
                family=self._family_override,
                pixel_size=(
                    self._pixel_size_override
                    if self._pixel_size_override is not None
                    else spec.pixel_size
                ),
                bold=(
                    spec.bold if self._bold_override is None else bool(self._bold_override)
                ),
                italic=bool(self._italic_override),
                underline=bool(self._underline_override),
                strike_out=bool(self._strike_out_override),
            )
        engine.set_text_color(self._explicit_color())

    def _explicit_color(self) -> QColor | None:
        if self._color_override is not None:
            return QColor(self._color_override)
        if self._color_token_override:
            return self.theme_manager.try_get_color(self._color_token_override)
        return None

    def _panel_color(self) -> QColor:
        """Theme surface behind the engine content (palette window fallback)."""
        color = self.theme_manager.try_get_color("surface.background")
        if color is not None and color.isValid():
            return QColor(color)
        return QColor(self.palette().window().color())

    def _apply_style(self) -> None:
        if self._engine is not None:
            self._apply_engine_style()
            return
        if self._applying_style:
            return
        self._applying_style = True
        try:
            spec = get_text_variant(self._variant_name)
            font = ui_font(
                family=self._family_override,
                pixel_size=(
                    self._pixel_size_override
                    if self._pixel_size_override is not None
                    else spec.pixel_size
                ),
                bold=(
                    spec.bold
                    if self._bold_override is None
                    else bool(self._bold_override)
                ),
                italic=bool(self._italic_override),
                underline=bool(self._underline_override),
                strike_out=bool(self._strike_out_override),
            )
            # Color via palette — never setStyleSheet("color:…") (Qt then ignores setFont).
            apply_text_color(self, self._resolve_color(spec))
            self.setFont(font)

            horizontal = (
                QSizePolicy.Policy.Expanding
                if self._expanding()
                else QSizePolicy.Policy.Preferred
            )
            policy = QSizePolicy(horizontal, self._vertical_policy())
            policy.setHeightForWidth(self._word_wrap)
            self.setSizePolicy(policy)

            minimum_width = self._minimum_width()
            if minimum_width > 0:
                super().setMinimumWidth(minimum_width)

            self._update_display_text()
            self.updateGeometry()
            self.update()
        finally:
            self._applying_style = False

    def _resolve_color(self, spec: TextVariantSpec) -> QColor | None:
        if self._color_override is not None:
            return QColor(self._color_override)

        token = self._color_token_override or spec.color_token
        color = self.theme_manager.try_get_color(token)
        if color is not None:
            return color

        fallback = self.theme_manager.try_get_color("WindowText")
        return fallback if fallback is not None else None

    def _vertical_policy(self) -> QSizePolicy.Policy:
        if self._word_wrap:
            return QSizePolicy.Policy.Preferred
        return QSizePolicy.Policy.Fixed

    def _minimum_width(self) -> int:
        if self._minimum_width_override is not None:
            return max(0, int(self._minimum_width_override))
        return max(0, get_text_variant(self._variant_name).minimum_width)

    def _expanding(self) -> bool:
        if self._expanding_override is not None:
            return bool(self._expanding_override)
        return get_text_variant(self._variant_name).expanding

    def _uses_elide(self) -> bool:
        if self._elide_override is not None:
            return bool(self._elide_override)
        return get_text_variant(self._variant_name).elide

    def _update_display_text(self) -> None:
        # Marquee owns overflow presentation — never elide while it is on.
        if self._marquee_enabled or not self._uses_elide() or not self._original_text:
            self._display_text = self._original_text
            return

        available_width = self.width() - 10
        if available_width <= 0:
            return

        metrics = QFontMetrics(self.font())
        if metrics.horizontalAdvance(self._original_text) <= available_width:
            self._display_text = self._original_text
        else:
            self._display_text = metrics.elidedText(
                self._original_text,
                Qt.TextElideMode.ElideRight,
                available_width,
            )

    def _text_flags(self) -> int:
        flags = int(self._alignment)
        if self._word_wrap:
            flags |= int(Qt.TextFlag.TextWordWrap)
        return flags

    def _text_size(self, width: int, flags: int) -> QSize:
        metrics = QFontMetrics(self.font())
        extent = width if width >= 0 else _NO_WRAP_EXTENT
        bounds = metrics.boundingRect(
            QRect(0, 0, extent, _NO_WRAP_EXTENT), flags, self._display_text
        )
        return QSize(bounds.width(), bounds.height())

    def _widest_word_size(self) -> QSize:
        metrics = QFontMetrics(self.font())
        widest = 0
        for word in self._display_text.split():
            bounds = metrics.boundingRect(
                QRect(0, 0, _NO_WRAP_EXTENT, _NO_WRAP_EXTENT), 0, word
            )
            widest = max(widest, bounds.width())
        return QSize(widest, metrics.height())

    def _text_top(self, rect: QRect, flags: int) -> float:
        item = self.style().itemTextRect(
            QFontMetrics(self.font()), rect, flags, self.isEnabled(), self._display_text
        )
        return float(item.y())

    def _layout(self, width: int):
        return build_layout(
            self._display_text,
            self.font(),
            width,
            self._word_wrap,
            self._alignment,
        )

    def _hit(self, position: QPointF) -> int:
        rect = self.contentsRect()
        flags = self._text_flags()
        layout = self._layout(rect.width())
        origin = QPointF(rect.x(), self._text_top(rect, flags))
        local = QPointF(position.x() - origin.x(), position.y() - origin.y())
        return max(0, min(len(self._display_text), hit_test(layout, local)))

    def _word_bounds(self, position: int) -> tuple[int, int]:
        text = self._display_text
        if not text:
            return 0, 0
        finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Word, text)
        finder.setPosition(min(position, len(text) - 1))
        start = finder.toPreviousBoundary()
        end = finder.toNextBoundary()
        if start < 0:
            start = 0
        if end < 0:
            end = len(text)
        return start, end

    def _selection_bounds(self) -> tuple[int, int]:
        return (
            min(self._sel_anchor, self._sel_cursor),
            max(self._sel_anchor, self._sel_cursor),
        )

    def _set_selection_range(self, anchor: int, cursor: int) -> None:
        before = (self._sel_anchor, self._sel_cursor)
        self._sel_anchor = anchor
        self._sel_cursor = cursor
        if before != (anchor, cursor):
            self.selectionChanged.emit()
        self.update()

    def _extend_selection_to(self, position: int) -> None:
        self._set_selection_range(self._sel_anchor, position)

    def _clear_selection(self) -> None:
        self._set_selection_range(0, 0)


Text.inspect_spec = InspectSpec(
    family="Text",
    state=(
        SpecField("text", "get_original_text"),
        SpecField("mode", "mode"),
        SpecField("variant", "variant"),
        SpecField("marquee", "marquee"),
    ),
    token_family=("dialog.text",),
    docs="docs/user/LABELS_API.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor  # noqa: E402

Text.widget_descriptor = WidgetDescriptor(
    family=Text.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(Text.inspect_spec, "config", ()),
        state=Text.inspect_spec.state,
        token_family=getattr(Text.inspect_spec, "token_family", ()),
        regions=getattr(Text.inspect_spec, "regions", False),
        layers=getattr(Text.inspect_spec, "layers", False),
        docs=getattr(Text.inspect_spec, "docs", ""),
    ),
)
