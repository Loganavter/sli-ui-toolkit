"""CustomLineEdit — painted single-line text input.

The field renders its own text through the toolkit painter pipeline
(``ui_font`` / ``QPainter.drawText`` / ``QFontMetrics``) and implements its
own editing (caret, selection, clipboard, undo, IME, horizontal scroll) on a
single content line.

Public surface is the standard line-edit API call sites expect: ``text``/
``setText``, ``textChanged``/``textEdited``/``editingFinished``/
``returnPressed``, ``setPlaceholderText``, ``setValidator``,
``setEchoMode``, ``setClearButtonEnabled``, ``setReadOnly``, ``setMaxLength``,
``selectAll``/``selectionStart``/``selectedText``/``setSelection``,
``copy``/``cut``/``paste``/``undo``/``redo``, ``cursorPosition``.
``EchoMode`` uses the standard integer values.

Opt-in submit preset (``submit_preset=True`` / ``setSubmitPreset``): the
standard single-shot submit-field contract — ``Tab`` on an empty field accepts
the placeholder as starting text (cursor at the end, no selection),
``Enter`` emits ``submitted`` with ``text().strip() or placeholderText()``
and resets the view to the start. Off by default: plain fields keep exact
``QLineEdit`` behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal, cast

from PySide6.QtCore import (
    QEvent,
    QMargins,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFontMetrics,
    QGuiApplication,
    QInputMethodEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QValidator,
    QWheelEvent,
)
import time

from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.managers.ui_font import apply_text_color, apply_ui_font
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.helpers import (
    UnderlineConfig,
    apply_editable_text_behavior,
    draw_bottom_underline,
)

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor  # noqa: F401

TextAlignment = Qt.AlignmentFlag | Literal["left", "center", "right"]

_UNDO_LIMIT = 100
_WORD_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)
_MULTI_CLICK_INTERVAL_MS = 900
_MULTI_CLICK_DISTANCE_PX = 8


class EchoMode:
    """Echo-mode constants (standard integer values)."""

    Normal = 0
    NoEcho = 1
    Password = 2
    PasswordEchoOnEdit = 3


class CustomLineEdit(QWidget):
    """Painted single-line text input."""

    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar["WidgetDescriptor"]

    textChanged = Signal(str)
    textEdited = Signal(str)
    editingFinished = Signal()
    returnPressed = Signal()
    selectionChanged = Signal()
    #: Submit-preset submit (see ``setSubmitPreset``): the resolved text —
    #: ``text().strip()``, or the placeholder when the field is empty.
    submitted = Signal(str)

    EchoMode = EchoMode

    RADIUS = 6
    # Horizontal inset only — vertical room comes from HEIGHT so descenders
    # (у, р, g, y) are not clipped.
    H_PADDING = 8
    V_PADDING = 0
    HEIGHT = 32
    # Caret blink period (half on / half off).
    BLINK_MS = 500
    CLEAR_BUTTON_EDGE = 16
    # Wheel scroll step: pixels of horizontal travel per wheel-delta unit
    # (one notch = 120 units ≈ 24 px).
    WHEEL_PX_PER_DELTA = 0.2

    def __init__(
        self,
        parent=None,
        *,
        alignment: TextAlignment = Qt.AlignmentFlag.AlignLeft,
        underline_color: QColor | None = None,
        underline_thickness: float | None = None,
        focused_underline_color: QColor | None = None,
        focused_underline_thickness: float | None = None,
        submit_preset: bool = False,
    ):
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._underline_color = underline_color
        self._underline_thickness = self._normalize_thickness(underline_thickness)
        self._focused_underline_color = focused_underline_color
        self._focused_underline_thickness = self._normalize_thickness(
            focused_underline_thickness
        )

        self._text = ""
        self._cursor = 0
        self._anchor: int | None = None
        self._press_pos: QPointF | None = None
        self._dragging = False
        self._click_count = 0
        self._last_click_time = 0.0
        self._last_click_x = 0.0
        self._last_click_y = 0.0
        self._margins = [
            scaled_px(self.H_PADDING),
            self.V_PADDING,
            scaled_px(self.H_PADDING),
            self.V_PADDING,
        ]
        self._alignment = self._normalize_alignment(alignment)
        self._placeholder = ""
        self._echo_mode = EchoMode.Normal
        self._read_only = False
        self._max_length = 32767
        self._validator: QValidator | None = None
        self._clear_button_enabled = False
        self._clear_button_hover = False
        self._h_offset = 0
        self._undo: list[tuple[str, int]] = []
        self._redo: list[tuple[str, int]] = []
        self._text_on_focus = ""
        self._submit_preset = bool(submit_preset)

        self._caret_on = True
        self._blink = QTimer(self)
        self._blink.setInterval(self.BLINK_MS)
        self._blink.timeout.connect(self._toggle_caret)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setFixedHeight(scaled_px(self.HEIGHT))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setProperty("custom-line-edit", True)
        self.setProperty("class", "primary")
        apply_editable_text_behavior(self)
        apply_ui_font(self)
        self._apply_theme_style()
        try:
            self.theme_manager.theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        try:
            UiScale.get_instance().scale_changed.connect(self.on_scale_changed)
        except Exception:
            pass

    # -- fonts / scale / theme ---------------------------------------------

    def on_scale_changed(self, _factor: float) -> None:
        self._set_hmargins(self._margins[0], self._margins[2])
        self.setFixedHeight(scaled_px(self.HEIGHT))
        self.updateGeometry()
        self.update()

    def _set_hmargins(self, left: int, right: int) -> None:
        self._margins[0] = int(left)
        self._margins[2] = int(right)

    def _on_theme_changed(self):
        self._apply_theme_style()
        self.update()

    def _apply_theme_style(self):
        text = self.theme_manager.get_color("dialog.text")
        apply_text_color(self, text)
        self.update()

    def fontMetrics(self) -> QFontMetrics:  # noqa: N802
        return QFontMetrics(self.font())

    # -- state (standard line-edit API) -------------------------------------

    def text(self) -> str:
        return self._text

    def displayText(self) -> str:  # noqa: N802
        return self._text

    def setText(self, text: str | None) -> None:
        new = "" if text is None else str(text)
        self._apply_text(new, cursor=len(new), notify=True, edited=False)

    def clear(self) -> None:
        self.setText("")

    def insert(self, text: str) -> None:
        if self._read_only or not text:
            return
        self._insert_user(str(text))

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        self._placeholder = str(text or "")
        self.update()

    def placeholderText(self) -> str:  # noqa: N802
        return self._placeholder

    def setEchoMode(self, mode: int) -> None:  # noqa: N802
        self._echo_mode = int(mode)
        self.update()

    def echoMode(self) -> int:  # noqa: N802
        return self._echo_mode

    def setReadOnly(self, read_only: bool) -> None:  # noqa: N802
        self._read_only = bool(read_only)
        self.setCursor(
            Qt.CursorShape.ArrowCursor if self._read_only else Qt.CursorShape.IBeamCursor
        )
        self.update()

    def isReadOnly(self) -> bool:  # noqa: N802
        return self._read_only

    def setMaxLength(self, length: int) -> None:  # noqa: N802
        self._max_length = max(0, int(length))

    def maxLength(self) -> int:  # noqa: N802
        return self._max_length

    def setValidator(self, validator: QValidator | None) -> None:  # noqa: N802
        self._validator = validator

    def validator(self) -> QValidator | None:  # noqa: N802
        return self._validator

    def _validate_state(self, text: str, pos: int) -> QValidator.State:
        if self._validator is None:
            return QValidator.State.Acceptable
        result = self._validator.validate(text, pos)
        return cast("tuple[QValidator.State, str, int]", result)[0]

    def hasAcceptableInput(self) -> bool:  # noqa: N802
        return self._validate_state(self._text, 0) == QValidator.State.Acceptable

    def setClearButtonEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._clear_button_enabled = bool(enabled)
        self.update()

    def isClearButtonEnabled(self) -> bool:  # noqa: N802
        return self._clear_button_enabled

    # -- submit preset (standard single-shot submit-field contract) -------------

    def setSubmitPreset(self, enabled: bool) -> None:  # noqa: N802
        """Enable the submit preset: Tab-accept + submit-on-Enter.

        With the preset on, ``Tab`` on an empty field accepts the
        placeholder as starting text (cursor at the end, no selection) and
        ``Enter`` emits :attr:`submitted` with ``text().strip()`` (or the
        placeholder when empty), then resets the view to the start.
        Off by default — plain fields keep exact ``QLineEdit`` behavior.
        """
        self._submit_preset = bool(enabled)

    set_submit_preset = setSubmitPreset

    def isSubmitPreset(self) -> bool:  # noqa: N802
        return self._submit_preset

    is_submit_preset = isSubmitPreset

    def _accept_placeholder(self) -> bool:
        """Preset Tab path: adopt the placeholder as starting text.

        Returns True when adopted (caller accepts the event); False when
        there is nothing to adopt (no preset / non-empty / no placeholder —
        Tab keeps its default focus-travel meaning).
        """
        if not self._submit_preset or self._read_only:
            return False
        if self._text.strip() or not self._placeholder:
            return False
        self._apply_text(self._placeholder, cursor=len(self._placeholder), notify=True, edited=False)
        return True

    def _submit_resolved(self) -> None:
        """Preset Enter path: emit the resolved text, rewind the view."""
        self.submitted.emit(self._text.strip() or self._placeholder)
        # Rewind so the text's start is visible after submit (the view
        # otherwise stays pinned to the end where the caret was).
        self.setCursorPosition(0)

    # -- alignment ----------------------------------------------------------

    def setTextAlignment(self, alignment: Qt.AlignmentFlag | str) -> None:
        """Set text alignment using Qt flags or 'left' / 'center' / 'right'."""
        self._alignment = self._normalize_alignment(alignment)
        self.update()

    def textAlignment(self) -> Qt.AlignmentFlag:
        return self._alignment

    def set_text_alignment(self, alignment: Qt.AlignmentFlag | str) -> None:
        self.setTextAlignment(alignment)

    def text_alignment(self) -> Qt.AlignmentFlag:
        return self.textAlignment()

    def setAlignment(self, alignment: Qt.AlignmentFlag | str) -> None:  # noqa: N802
        self.setTextAlignment(alignment)

    def alignment(self) -> Qt.AlignmentFlag:
        return self._alignment

    # -- margins ------------------------------------------------------------

    def setTextMargins(self, left: int, top: int, right: int, bottom: int) -> None:  # noqa: N802
        self._margins = [int(left), int(top), int(right), int(bottom)]
        self.update()

    def textMargins(self) -> QMargins:  # noqa: N802
        return QMargins(*self._margins)

    # -- caret / selection --------------------------------------------------

    def cursorPosition(self) -> int:  # noqa: N802
        return self._cursor

    def setCursorPosition(self, pos: int) -> None:  # noqa: N802
        self._cursor = max(0, min(len(self._text), int(pos)))
        self._clear_selection()
        self._reset_blink()
        self._ensure_caret_visible()
        self.update()

    def selectedText(self) -> str:  # noqa: N802
        bounds = self._selection_bounds()
        if bounds is None:
            return ""
        return self._text[bounds[0] : bounds[1]]

    def hasSelectedText(self) -> bool:  # noqa: N802
        return self._selection_bounds() is not None

    def selectionStart(self) -> int:  # noqa: N802
        bounds = self._selection_bounds()
        return -1 if bounds is None else bounds[0]

    def selectionEnd(self) -> int:  # noqa: N802
        bounds = self._selection_bounds()
        return -1 if bounds is None else bounds[1]

    def selectionLength(self) -> int:  # noqa: N802
        bounds = self._selection_bounds()
        return 0 if bounds is None else bounds[1] - bounds[0]

    def setSelection(self, start: int, length: int) -> None:  # noqa: N802
        start = max(0, min(len(self._text), int(start)))
        end = max(start, min(len(self._text), start + int(length)))
        if end == start:
            self._clear_selection()
            return
        self._anchor = start
        self._cursor = end
        self._sync_selection_state()
        self.update()

    def selectAll(self) -> None:  # noqa: N802
        if not self._text:
            return
        self.setSelection(0, len(self._text))

    def deselect(self) -> None:  # noqa: N802
        self._clear_selection()
        self.update()

    # -- clipboard / undo ---------------------------------------------------

    def copy(self) -> None:
        selected = self.selectedText()
        if selected:
            QGuiApplication.clipboard().setText(selected)

    def cut(self) -> None:
        if self._read_only:
            return
        selected = self.selectedText()
        if not selected:
            return
        QGuiApplication.clipboard().setText(selected)
        self._commit_undo()
        self._replace_selection("")
        self._after_edit(edited=True)

    def paste(self) -> None:
        if self._read_only:
            return
        clip = QGuiApplication.clipboard().text()
        if clip:
            self._insert_user(clip.replace("\n", " "))

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append((self._text, self._cursor))
        text, cursor = self._undo.pop()
        self._apply_text(text, cursor=cursor, notify=True, edited=False)

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append((self._text, self._cursor))
        text, cursor = self._redo.pop()
        self._apply_text(text, cursor=cursor, notify=True, edited=False)

    def backspace(self) -> None:
        self._edit_backspace()

    def del_(self) -> None:
        self._edit_delete()

    # -- underline (unchanged public surface) -------------------------------

    def setUnderlineColor(self, color: QColor | None) -> None:  # noqa: N802
        self._underline_color = color
        self.setProperty("underlineColor", color)
        self.update()

    set_underline_color = setUnderlineColor

    def underlineColor(self) -> QColor | None:  # noqa: N802
        return self._underline_color

    def setUnderlineThickness(self, thickness: float | None) -> None:  # noqa: N802
        self._underline_thickness = self._normalize_thickness(thickness)
        self.setProperty("underlineThicknessPx", self._underline_thickness)
        self.update()

    set_underline_thickness = setUnderlineThickness

    def underlineThickness(self) -> float | None:  # noqa: N802
        return self._underline_thickness

    def setFocusedUnderlineColor(self, color: QColor | None) -> None:  # noqa: N802
        self._focused_underline_color = color
        self.setProperty("focusedUnderlineColor", color)
        self.update()

    def focusedUnderlineColor(self) -> QColor | None:  # noqa: N802
        return self._focused_underline_color

    def setFocusedUnderlineThickness(self, thickness: float | None) -> None:  # noqa: N802
        self._focused_underline_thickness = self._normalize_thickness(thickness)
        self.setProperty("focusedUnderlineThicknessPx", self._focused_underline_thickness)
        self.update()

    def focusedUnderlineThickness(self) -> float | None:  # noqa: N802
        return self._focused_underline_thickness

    # -- size hints ---------------------------------------------------------

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, scaled_px(self.HEIGHT))

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        basis = self._text or self._placeholder or "x"
        width = fm.horizontalAdvance(basis) + self._margins[0] + self._margins[2] + 4
        return QSize(max(scaled_px(40), width), scaled_px(self.HEIGHT))

    # -- geometry helpers ---------------------------------------------------

    def _content_rect(self) -> QRect:
        left = self._margins[0]
        right = self.width() - self._margins[2]
        clear_w = self._clear_button_reserve()
        right -= clear_w
        if right < left:
            right = left
        top = self._margins[1]
        bottom = self.height() - self._margins[3]
        return QRect(left, top, max(0, right - left), max(0, bottom - top))

    def _clear_button_reserve(self) -> int:
        if not self._show_clear_button():
            return 0
        return scaled_px(self.CLEAR_BUTTON_EDGE) + scaled_px(4)

    def _show_clear_button(self) -> bool:
        return self._clear_button_enabled and bool(self._text) and not self._read_only

    def _clear_button_rect(self) -> QRect:
        size = scaled_px(self.CLEAR_BUTTON_EDGE)
        right = self.width() - self._margins[2] - scaled_px(2)
        x = right - size
        y = (self.height() - size) // 2
        return QRect(x, y, size, size)

    # -- paint --------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        radius = scaled_px(self.RADIUS)
        rounded = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)

        bg = self.theme_manager.get_color("surface.background")
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rounded, radius, radius)

        panel = self._content_rect()
        painter.setClipRect(QRect(0, 0, self.width(), self.height()))
        self._paint_selection(painter, panel)
        self._paint_text(painter, panel)
        self._paint_caret(painter, panel)
        self._paint_clear_button(painter)

        # Border + underline on top (flat cap, sub-pixel thin).
        thin = QColor(self.theme_manager.get_color("input.border.thin"))
        alpha = max(8, int(thin.alpha() * 0.66))
        thin.setAlpha(alpha)
        pen = QPen(thin)
        pen.setWidthF(0.66)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rounded, radius, radius)

        if self.hasFocus():
            cfg = UnderlineConfig(
                color=(
                    self._focused_underline_color
                    or self.theme_manager.get_color("accent")
                ),
                alpha=120,
                thickness=self._focused_underline_thickness or 1.5,
                arc_radius=float(self.RADIUS),
                vertical_offset=0.0,
            )
        else:
            cfg = UnderlineConfig(
                color=self._underline_color,
                alpha=60,
                thickness=self._underline_thickness or 1.0,
                arc_radius=float(self.RADIUS),
                vertical_offset=0.0,
            )
        draw_bottom_underline(painter, rect, self.theme_manager, cfg)
        painter.end()

    def _paint_selection(self, painter: QPainter, rect: QRect) -> None:
        bounds = self._selection_bounds()
        if bounds is None or not self.hasFocus():
            return
        lo, hi = bounds
        start_x = self._text_start_x(rect)
        fm = self.fontMetrics()
        x0 = start_x + fm.horizontalAdvance(self._display_text()[:lo])
        x1 = start_x + fm.horizontalAdvance(self._display_text()[:hi])
        accent = QColor(self.theme_manager.get_color("accent"))
        accent.setAlpha(90)
        line = self._text_line_rect(rect)
        painter.fillRect(QRect(int(x0), line.top(), int(x1 - x0), line.height()), accent)

    def _paint_text(self, painter: QPainter, rect: QRect) -> None:
        fm = self.fontMetrics()
        shown = self._display_text_painted()
        if shown:
            color = QColor(self.theme_manager.get_color("dialog.text"))
            if not self.isEnabled():
                color.setAlpha(130)
            painter.setFont(self.font())
            painter.setPen(color)
            start_x = self._text_start_x(rect)
            y = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2
            painter.drawText(QPointF(start_x, y), shown)
        elif self._placeholder and not self._text and not self._read_only:
            color = QColor(self.theme_manager.get_color("dialog.text"))
            color.setAlpha(120)
            painter.setFont(self.font())
            painter.setPen(color)
            start_x = self._text_start_x(rect, for_width=fm.horizontalAdvance(self._placeholder))
            y = rect.top() + (rect.height() + fm.ascent() - fm.descent()) // 2
            painter.drawText(QPointF(start_x, y), self._placeholder)

    def _paint_caret(self, painter: QPainter, rect: QRect) -> None:
        if not self.hasFocus() or self._read_only or self._selection_bounds() is not None:
            return
        if not self._caret_on:
            return
        fm = self.fontMetrics()
        start_x = self._text_start_x(rect)
        cx = start_x + fm.horizontalAdvance(self._text[: self._cursor])
        color = QColor(self.theme_manager.get_color("dialog.text"))
        line = self._text_line_rect(rect)
        painter.fillRect(
            QRect(int(cx), line.top(), max(1, scaled_px(1)), line.height()), color
        )

    def _paint_clear_button(self, painter: QPainter) -> None:
        if not self._show_clear_button():
            return
        if not (self._clear_button_hover or self.hasFocus()):
            return
        btn = self._clear_button_rect()
        accent = QColor(self.theme_manager.get_color("accent"))
        ink = QColor(self.theme_manager.get_color("dialog.text"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        wash = QColor(accent)
        wash.setAlpha(40 if self._clear_button_hover else 22)
        painter.setBrush(wash)
        painter.drawEllipse(btn)
        pen = QPen(ink)
        pen.setWidthF(1.4)
        painter.setPen(pen)
        m = btn.adjusted(5, 5, -5, -5)
        painter.drawLine(m.topLeft(), m.bottomRight())
        painter.drawLine(m.topRight(), m.bottomLeft())

    # -- text positioning ---------------------------------------------------

    def _display_text(self) -> str:
        return self._text

    def _display_text_painted(self) -> str:
        if self._echo_mode in (EchoMode.Password, EchoMode.NoEcho):
            if self._echo_mode == EchoMode.NoEcho and not self.hasFocus():
                return ""
            return "\u2022" * len(self._text)
        return self._text

    def _max_text_width(self, rect: QRect) -> int:
        return rect.width()

    def _text_start_x(self, rect: QRect, *, for_width: int | None = None) -> float:
        fm = self.fontMetrics()
        full = fm.horizontalAdvance(self._display_text_painted() or self._placeholder)
        total = full if for_width is None else for_width
        avail = rect.width()
        if total <= avail:
            self._h_offset = 0
            if self._alignment & Qt.AlignmentFlag.AlignHCenter:
                return rect.left() + (avail - total) / 2.0
            if self._alignment & Qt.AlignmentFlag.AlignRight:
                return rect.left() + (avail - total)
            return float(rect.left())
        # Overflows: left-align and scroll to keep the caret visible.
        return float(rect.left()) - self._h_offset

    def _caret_x(self, rect: QRect) -> float:
        fm = self.fontMetrics()
        return self._text_start_x(rect) + fm.horizontalAdvance(self._display_text_painted()[: self._cursor])

    def _ensure_caret_visible(self) -> None:
        rect = self._content_rect()
        fm = self.fontMetrics()
        total = fm.horizontalAdvance(self._display_text_painted())
        if total <= rect.width():
            self._h_offset = 0
            return
        caret = fm.horizontalAdvance(self._display_text_painted()[: self._cursor])
        left = self._h_offset
        right = left + rect.width()
        if caret < left:
            self._h_offset = caret
        elif caret > right - 2:
            self._h_offset = caret - rect.width() + 2
        self._h_offset = max(0, min(self._h_offset, total - rect.width()))

    # -- selection model ----------------------------------------------------

    def _selection_bounds(self) -> tuple[int, int] | None:
        if self._anchor is None:
            return None
        if self._anchor == self._cursor:
            return None
        return (min(self._anchor, self._cursor), max(self._anchor, self._cursor))

    def _text_line_rect(self, rect: QRect) -> QRect:
        """Text-height band centred in *rect* (caret/selection, not full height)."""
        fm = self.fontMetrics()
        line_h = fm.ascent() + fm.descent()
        y = rect.top() + (rect.height() - line_h) // 2
        return QRect(rect.left(), y, rect.width(), line_h)

    def _clear_selection(self) -> None:
        self._anchor = None
        self.selectionChanged.emit()

    def _sync_selection_state(self) -> None:
        self.selectionChanged.emit()

    def _word_range(self, pos: int) -> tuple[int, int]:
        line = self._text
        start = end = max(0, min(len(line), pos))
        while start > 0 and line[start - 1] in _WORD_CHARS:
            start -= 1
        while end < len(line) and line[end] in _WORD_CHARS:
            end += 1
        if start == end and end < len(line):
            end += 1
        return (start, end)

    def _press_chain(self, x: float, y: float) -> int:
        now = time.monotonic()
        interval = _MULTI_CLICK_INTERVAL_MS / 1000.0
        near = (
            abs(x - self._last_click_x) <= _MULTI_CLICK_DISTANCE_PX
            and abs(y - self._last_click_y) <= _MULTI_CLICK_DISTANCE_PX
        )
        if near and now - self._last_click_time <= interval:
            self._click_count += 1
            if self._click_count > 3:
                self._click_count = 1
        else:
            self._click_count = 1
        self._last_click_time = now
        self._last_click_x = x
        self._last_click_y = y
        return self._click_count

    def _replace_selection(self, insert: str) -> None:
        bounds = self._selection_bounds()
        if bounds is None:
            self._clear_selection()
            return
        lo, hi = bounds
        self._text = self._text[:lo] + insert + self._text[hi:]
        self._cursor = lo + len(insert)
        self._clear_selection()

    # -- editing ------------------------------------------------------------

    def _accept_candidate(self, candidate: str, cursor: int) -> bool:
        if len(candidate) > self._max_length:
            return False
        if self._validate_state(candidate, cursor) == QValidator.State.Invalid:
            return False
        return True

    def _apply_text(self, new: str, *, cursor: int, notify: bool, edited: bool) -> None:
        if new == self._text and cursor == self._cursor:
            return
        self._text = new
        self._cursor = max(0, min(len(new), cursor))
        self._clear_selection()
        if notify:
            self.textChanged.emit(self._text)
        if edited:
            self.textEdited.emit(self._text)
        self._reset_blink()
        self._ensure_caret_visible()
        self.update()

    def _commit_undo(self) -> None:
        self._undo.append((self._text, self._cursor))
        if len(self._undo) > _UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()

    def _after_edit(self, *, edited: bool) -> None:
        if edited:
            self.textEdited.emit(self._text)
        self.textChanged.emit(self._text)
        self._reset_blink()
        self._ensure_caret_visible()
        self.update()

    def _insert_user(self, text: str) -> None:
        if self._read_only or not text:
            return
        self._commit_undo()
        bounds = self._selection_bounds()
        if bounds is not None:
            lo, hi = bounds
            base = self._text[:lo] + self._text[hi:]
            cursor = lo
            self._clear_selection()
        else:
            base = self._text
            cursor = self._cursor
        candidate = base[:cursor] + text + base[cursor:]
        if not self._accept_candidate(candidate, cursor + len(text)):
            return
        self._text = candidate
        self._cursor = cursor + len(text)
        self._after_edit(edited=True)

    def _edit_backspace(self) -> None:
        if self._read_only:
            return
        if self._selection_bounds() is not None:
            self._commit_undo()
            self._replace_selection("")
            self._after_edit(edited=True)
            return
        if self._cursor == 0:
            return
        self._commit_undo()
        new = self._text[: self._cursor - 1] + self._text[self._cursor :]
        self._text = new
        self._cursor -= 1
        self._after_edit(edited=True)

    def _edit_delete(self) -> None:
        if self._read_only:
            return
        if self._selection_bounds() is not None:
            self._commit_undo()
            self._replace_selection("")
            self._after_edit(edited=True)
            return
        if self._cursor >= len(self._text):
            return
        self._commit_undo()
        self._text = self._text[: self._cursor] + self._text[self._cursor + 1 :]
        self._after_edit(edited=True)

    def _move_caret(self, delta: int, *, extend: bool) -> None:
        new = max(0, min(len(self._text), self._cursor + delta))
        if extend:
            if self._anchor is None:
                self._anchor = self._cursor
            self._cursor = new
            self._sync_selection_state()
        else:
            self._cursor = new
            self._clear_selection()
        self._reset_blink()
        self._ensure_caret_visible()
        self.update()

    def _set_selection(self, anchor: int, cursor: int) -> None:
        self._anchor = max(0, min(len(self._text), anchor))
        self._cursor = max(0, min(len(self._text), cursor))
        self._sync_selection_state()
        self._reset_blink()
        self._ensure_caret_visible()
        self.update()

    def _set_caret(self, pos: int, *, extend: bool) -> None:
        pos = max(0, min(len(self._text), pos))
        if extend:
            if self._anchor is None:
                self._anchor = self._cursor
            self._cursor = pos
            self._sync_selection_state()
        else:
            self._cursor = pos
            self._clear_selection()
        self._reset_blink()
        self._ensure_caret_visible()
        self.update()

    # -- blink --------------------------------------------------------------

    def _reset_blink(self) -> None:
        self._caret_on = True
        if self.hasFocus():
            self._blink.start()

    def _toggle_caret(self) -> None:
        self._caret_on = not self._caret_on
        self.update()

    # -- position <-> index -------------------------------------------------

    def _index_at(self, x: float) -> int:
        rect = self._content_rect()
        start_x = self._text_start_x(rect)
        fm = self.fontMetrics()
        text = self._display_text_painted()
        width = 0.0
        for i, ch in enumerate(text):
            advance = fm.horizontalAdvance(ch)
            if x < start_x + width + advance / 2.0:
                return i
            width += advance
        return len(text)

    # -- events -------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._show_clear_button():
            if self._clear_button_rect().contains(event.position().toPoint()):
                self.clear()
                event.accept()
                return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        point = event.position()
        pos = self._index_at(point.x())
        chain = self._press_chain(point.x(), point.y())
        self._press_pos = point
        self._dragging = False
        if chain >= 3:
            self._set_selection(0, len(self._text))
        elif chain == 2:
            rng = self._word_range(pos)
            self._set_selection(rng[0], rng[1])
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._set_caret(pos, extend=True)
        else:
            self._cursor = pos
            self._clear_selection()
            self._reset_blink()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._clear_button_enabled and self._show_clear_button():
            hover = self._clear_button_rect().contains(event.position().toPoint())
            if hover != self._clear_button_hover:
                self._clear_button_hover = hover
                self.update()
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_pos is not None:
            if not self._dragging:
                if (event.position() - self._press_pos).manhattanLength() < 4:
                    return
                self._dragging = True
                if self._anchor is None:
                    self._anchor = self._cursor
            pos = self._index_at(event.position().x())
            self._cursor = pos
            self._sync_selection_state()
            self._ensure_caret_visible()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._press_pos = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self._index_at(event.position().x())
            chain = self._press_chain(event.position().x(), event.position().y())
            if chain >= 3:
                rng = (0, len(self._text))
            else:
                rng = self._word_range(pos)
            self._set_selection(rng[0], rng[1])
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Scroll overflowed text horizontally (``QLineEdit`` parity).

        A vertical wheel moves the line sideways; a horizontal (or
        pixel-scrolling) delta pans directly. When the text fits — or the
        offset is already at the bound in the scroll direction — the event
        is ignored so an enclosing scroller can take it.
        """
        rect = self._content_rect()
        total = self.fontMetrics().horizontalAdvance(self._display_text_painted())
        span = total - rect.width()
        if span <= 0:
            event.ignore()
            return
        delta = event.pixelDelta()
        if delta.isNull():
            delta = event.angleDelta()
        step = delta.x() if delta.x() else delta.y()
        if not step:
            event.ignore()
            return
        new_offset = max(0, min(span, self._h_offset - int(round(step * self.WHEEL_PX_PER_DELTA))))
        if new_offset == self._h_offset:
            event.ignore()
            return
        self._h_offset = new_offset
        self.update()
        event.accept()

    def event(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ShortcutOverride:
            if self._claims_shortcut(event):
                event.accept()
                return True
        return super().event(event)

    def _claims_shortcut(self, event) -> bool:
        # Plain printable input must be claimed too: otherwise a window-level
        # single-letter shortcut (e.g. "e") wins the ShortcutOverride and the
        # character is never typed into the focused field.
        if self._is_typing_key(event):
            return True
        if event.key() in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            return True
        return any(
            event.matches(seq)
            for seq in (
                QKeySequence.StandardKey.Copy,
                QKeySequence.StandardKey.Paste,
                QKeySequence.StandardKey.Cut,
                QKeySequence.StandardKey.Undo,
                QKeySequence.StandardKey.Redo,
                QKeySequence.StandardKey.SelectAll,
            )
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy()
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.selectAll()
            return
        if event.matches(QKeySequence.StandardKey.Paste) and not self._read_only:
            self.paste()
            return
        if event.matches(QKeySequence.StandardKey.Cut) and not self._read_only:
            self.cut()
            return
        if event.matches(QKeySequence.StandardKey.Undo) and not self._read_only:
            self.undo()
            return
        if event.matches(QKeySequence.StandardKey.Redo) and not self._read_only:
            self.redo()
            return
        if key == Qt.Key.Key_Left:
            self._move_caret(-1, extend=shift)
        elif key == Qt.Key.Key_Right:
            self._move_caret(1, extend=shift)
        elif key == Qt.Key.Key_Home:
            self._set_caret(0, extend=shift)
        elif key == Qt.Key.Key_End:
            self._set_caret(len(self._text), extend=shift)
        elif key == Qt.Key.Key_Backspace:
            self._edit_backspace()
        elif key == Qt.Key.Key_Delete:
            self._edit_delete()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.returnPressed.emit()
            self.editingFinished.emit()
            if self._submit_preset:
                self._submit_resolved()
            QTimer.singleShot(0, self.clearFocus)
        elif key == Qt.Key.Key_Escape:
            self.clearFocus()
        elif key == Qt.Key.Key_Tab and self._accept_placeholder():
            pass
        elif self._is_typing_key(event):
            self._insert_user(event.text())
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _is_typing_key(self, event: QKeyEvent) -> bool:
        if self._read_only:
            return False
        modifiers = event.modifiers() & ~(
            Qt.KeyboardModifier.KeypadModifier | Qt.KeyboardModifier.GroupSwitchModifier
        )
        return (
            modifiers in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier)
            and event.key() != Qt.Key.Key_Shift
            and bool(event.text())
            and (event.text().isprintable() or event.text() == "\t")
        )

    def inputMethodEvent(self, event: QInputMethodEvent) -> None:  # noqa: N802
        if not self._read_only and event.commitString():
            self._insert_user(event.commitString())
        event.accept()

    def inputMethodQuery(self, query):  # noqa: N802
        rect = self._content_rect()
        if query == Qt.InputMethodQuery.ImCursorRectangle:
            x = self._caret_x(rect)
            y = rect.top() + (rect.height() - self.fontMetrics().height()) // 2
            return QRect(int(x), int(y), max(1, scaled_px(1)), self.fontMetrics().height())
        if query == Qt.InputMethodQuery.ImFont:
            return self.font()
        if query == Qt.InputMethodQuery.ImSurroundingText:
            return self._text
        if query == Qt.InputMethodQuery.ImCursorPosition:
            return self._cursor
        if query == Qt.InputMethodQuery.ImAnchorPosition:
            return self._anchor if self._anchor is not None else self._cursor
        return super().inputMethodQuery(query)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        self._text_on_focus = self._text
        self._caret_on = True
        self._blink.start()
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        self._blink.stop()
        self._clear_button_hover = False
        super().focusOutEvent(event)
        self.editingFinished.emit()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._ensure_caret_visible()
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._clear_button_hover:
            self._clear_button_hover = False
            self.update()
        super().leaveEvent(event)

    # -- helper -------------------------------------------------------------

    @staticmethod
    def _normalize_thickness(thickness: float | None) -> float | None:
        return None if thickness is None else max(0.0, float(thickness))

    def _normalize_alignment(self, alignment: Qt.AlignmentFlag | str) -> Qt.AlignmentFlag:
        if isinstance(alignment, str):
            normalized = alignment.strip().lower().replace("-", "_")
            if normalized in {"left", "start", "leading"}:
                horizontal = Qt.AlignmentFlag.AlignLeft
            elif normalized in {"center", "centre", "middle"}:
                horizontal = Qt.AlignmentFlag.AlignHCenter
            elif normalized in {"right", "end", "trailing"}:
                horizontal = Qt.AlignmentFlag.AlignRight
            else:
                raise ValueError(
                    "alignment must be a Qt alignment or one of: left, center, right"
                )
            return horizontal | Qt.AlignmentFlag.AlignVCenter
        if alignment & (
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignJustify
        ):
            return alignment | Qt.AlignmentFlag.AlignVCenter
        return alignment | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


CustomLineEdit.inspect_spec = InspectSpec(
    family="CustomLineEdit",
    state=(
        SpecField("text", "text"),
        SpecField("placeholder", "placeholderText"),
        SpecField("alignment", "textAlignment"),
        SpecField("underline_color", "underlineColor"),
        SpecField("underline_thickness", "underlineThickness"),
        SpecField("focused_underline_color", "focusedUnderlineColor"),
        SpecField("focused_underline_thickness", "focusedUnderlineThickness"),
    ),
    token_family=("surface.background", "input.border.thin", "dialog.text", "accent"),
    docs="docs/user/INPUTS_API.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

CustomLineEdit.widget_descriptor = WidgetDescriptor(
    family=CustomLineEdit.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(CustomLineEdit.inspect_spec, "config", ()),
        state=CustomLineEdit.inspect_spec.state,
        token_family=getattr(CustomLineEdit.inspect_spec, "token_family", ()),
        regions=getattr(CustomLineEdit.inspect_spec, "regions", False),
        layers=getattr(CustomLineEdit.inspect_spec, "layers", False),
        docs=getattr(CustomLineEdit.inspect_spec, "docs", ""),
    ),
)
