"""Unified painted text display widget (P1: plain mode).

``Text`` is one ``QWidget`` configured by keyword arguments or a frozen
``TextConfig``. ``mode="plain"`` is the ``Label`` replacement; ``document`` and
``code`` are reserved for P2 and raise ``NotImplementedError`` until then.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRect, QSize, Qt, QTextBoundaryFinder, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
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
from sli_ui_toolkit.ui.managers.ui_font import UiFont, apply_text_color, ui_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale
from sli_ui_toolkit.ui.widgets.atomic.label_context_menu import (
    open_label_context_menu,
)
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import (
    draw_marquee_text,
    ensure_marquee_driver,
    text_overflows,
)
from sli_ui_toolkit.ui.widgets.text.plain import (
    build_layout,
    hit_test,
    selection_rects,
)
from sli_ui_toolkit.ui.widgets.text.variants import TextVariantSpec, get_text_variant

_PLAIN = "plain"
_P2_MODES = ("document", "code")
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
        }


def _require_plain_mode(mode: str) -> None:
    if mode == _PLAIN:
        return
    if mode in _P2_MODES:
        raise NotImplementedError(
            f'Text mode "{mode}" is not implemented yet (P2); use mode="plain"'
        )
    raise ValueError(f'unknown Text mode {mode!r}; expected "plain"')


class Text(QWidget):
    """Painted text display. Plain mode matches ``Label`` typography and behavior."""

    selectionChanged = Signal()

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
        config: TextConfig | None = None,
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

        _require_plain_mode(mode)
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._mode = mode
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
        self._selectable = False
        self._sel_anchor = 0
        self._sel_cursor = 0
        self._dragging = False
        self._applying_style = False

        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        UiFont.get_instance().font_changed.connect(self._apply_style)
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)
        self._apply_style()
        if selectable:
            self.setSelectable(True)

    def mode(self) -> str:
        return self._mode

    def text(self) -> str:
        return self._display_text

    def setText(self, text: str) -> None:
        self._original_text = text
        self._clear_selection()
        self._update_display_text()
        self.updateGeometry()
        self.update()

    def get_original_text(self) -> str:
        return self._original_text

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
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.unsetCursor()
            self._clear_selection()

    def isSelectable(self) -> bool:
        return self._selectable

    def hasSelectedText(self) -> bool:
        start, end = self._selection_bounds()
        return start != end

    def selectedText(self) -> str:
        start, end = self._selection_bounds()
        return self._display_text[start:end]

    def setSelection(self, start: int, length: int) -> None:
        text_length = len(self._display_text)
        if start < 0 or start > text_length or length <= 0:
            self._clear_selection()
            return
        self._set_selection_range(start, min(text_length, start + length))

    def selectAll(self) -> None:
        self.setSelection(0, len(self._display_text))

    def minimumSizeHint(self):
        if self._word_wrap:
            size = self._widest_word_size()
        else:
            size = self._text_size(-1, 0)
        if self._minimum_width() > 0:
            size.setWidth(self._minimum_width())
        return size

    def sizeHint(self):
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
        super().mouseMoveEvent(event)

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
        if self._selectable and self._display_text:
            # Menu helper is annotated QLabel but only uses the selection API Text mirrors.
            open_label_context_menu(self, event.globalPos())  # type: ignore[arg-type]
            event.accept()
            return
        super().contextMenuEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_display_text()

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

    def _on_scale_changed(self, _factor: float) -> None:
        self._apply_style()

    def _on_theme_changed(self) -> None:
        """Theme flip: recolor only — skip font/geometry rebuild."""
        if self._applying_style:
            return
        self._applying_style = True
        try:
            spec = get_text_variant(self._variant_name)
            apply_text_color(self, self._resolve_color(spec))
            self.update()
        finally:
            self._applying_style = False

    def _apply_style(self) -> None:
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
