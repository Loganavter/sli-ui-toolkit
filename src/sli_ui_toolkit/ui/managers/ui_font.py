"""Single source of truth for toolkit UI typefaces.

Why this exists
---------------
Qt has two traps that make widgets silently fall back to the system face:

1. ``QFont()`` / ``QApplication.font()`` / copying ``widget.font()`` after the
   widget was first resolved *before* the host swapped ``QApplication.font()``
   bakes the old family.
2. Any stylesheet on a text widget (even ``color: …`` only) makes Qt
   **ignore** ``setFont()`` when painting.

``UiFont`` is the toolkit-side answer (mirrors ``ThemeManager`` for color).

**Dogma:** toolkit paint / label / metrics code must not call ``QFont()`` or
``QApplication.font()`` for UI text. Use:

* ``ui_font(...)`` — resolve from the pinned UI face
* ``rebase_font(existing)`` — keep size/weight from a caller font, force UI family
* ``paint_font(widget)`` — UI family + size hints from a widget
* ``apply_text_color`` — color via palette, never color-only QSS

Host wiring (Improve-ImgSLI ``FontManager``)::

    from sli_ui_toolkit.managers import UiFont
    app.setFont(new_font)
    UiFont.get_instance().set_family(new_font.family())
    UiFont.get_instance().sync_from_application()
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget


class UiFont(QObject):
    """Process-wide UI typeface resolver for toolkit widgets."""

    _instance: Optional["UiFont"] = None
    font_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._family_override: str | None = None
        self._event_filter_installed = False

    @classmethod
    def get_instance(cls) -> "UiFont":
        if cls._instance is None:
            cls._instance = UiFont()
        return cls._instance

    def family(self) -> str:
        """Active UI family (override, else ``QApplication.font()``)."""
        if self._family_override:
            return self._family_override
        app = QApplication.instance()
        if app is not None:
            family = app.font().family()
            if family:
                return family
        return QFont().family()

    def set_family(self, family: str | None) -> None:
        """Pin a face (e.g. after the host loads a builtin TTF).

        Pass ``None`` to follow ``QApplication.font()`` again.
        """
        normalized = (family or "").strip() or None
        if normalized == self._family_override:
            return
        self._family_override = normalized
        self._emit_changed()

    def sync_from_application(self) -> None:
        """Notify listeners after the host's ``app.setFont(...)``."""
        self._install_event_filter()
        self._emit_changed()

    def base_font(self) -> QFont:
        """Copy of the current UI face (size from the application font)."""
        app = QApplication.instance()
        if app is not None:
            font = QFont(app.font())
        else:
            font = QFont()
        family = self.family()
        if family:
            font.setFamily(family)
        return font

    def resolve(
        self,
        *,
        pixel_size: int | None = None,
        point_size: int | float | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strike_out: bool | None = None,
        family: str | None = None,
        weight: int | None = None,
    ) -> QFont:
        """Build a font from the UI face with optional local overrides."""
        font = self.base_font()
        if family:
            font.setFamily(family)
        if pixel_size is not None:
            font.setPixelSize(max(1, int(pixel_size)))
        elif point_size is not None:
            font.setPointSizeF(float(point_size))
        if bold is not None:
            font.setBold(bool(bold))
        if italic is not None:
            font.setItalic(bool(italic))
        if underline is not None:
            font.setUnderline(bool(underline))
        if strike_out is not None:
            font.setStrikeOut(bool(strike_out))
        if weight is not None:
            font.setWeight(QFont.Weight(int(weight)))
        return font

    def rebase(self, source: QFont | None = None, **overrides) -> QFont:
        """Keep size/style from ``source``, but force the UI family.

        Use this when a caller hands you a ``QFont`` that may still carry a
        baked system face from before the host applied the builtin font.
        """
        kwargs = dict(overrides)
        if source is not None:
            if kwargs.get("pixel_size") is None and source.pixelSize() > 0:
                kwargs["pixel_size"] = source.pixelSize()
            elif kwargs.get("point_size") is None and source.pointSizeF() > 0:
                kwargs["point_size"] = source.pointSizeF()
            if kwargs.get("bold") is None:
                kwargs["bold"] = source.bold()
            if kwargs.get("italic") is None:
                kwargs["italic"] = source.italic()
            if kwargs.get("underline") is None:
                kwargs["underline"] = source.underline()
            if kwargs.get("strike_out") is None:
                kwargs["strike_out"] = source.strikeOut()
        return self.resolve(**kwargs)

    def paint_font(self, widget: QWidget | None = None, **overrides) -> QFont:
        """Font for custom painters: UI family + size/weight hints from a widget."""
        source = widget.font() if widget is not None else None
        merged = dict(overrides)
        if widget is not None and bool(widget.property("sliBold")):
            merged["bold"] = True
        return self.rebase(source, **merged)

    def apply(self, widget: QWidget, **overrides) -> QFont:
        """``setFont(resolve(...))`` on ``widget`` and return the font used."""
        font = self.resolve(**overrides)
        widget.setFont(font)
        return font

    def eventFilter(self, obj, event):  # noqa: N802 — Qt API
        if event.type() == QEvent.Type.ApplicationFontChange:
            self._emit_changed()
        return False

    def _install_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._event_filter_installed = True

    def _emit_changed(self) -> None:
        self._install_event_filter()
        self.font_changed.emit()


def ui_font(**overrides) -> QFont:
    """Resolve a UI font — preferred entry point for paint / layout code."""
    return UiFont.get_instance().resolve(**overrides)


def rebase_font(source: QFont | None = None, **overrides) -> QFont:
    """Force UI family onto an existing font (or build a fresh UI font)."""
    return UiFont.get_instance().rebase(source, **overrides)


def paint_font(widget: QWidget | None = None, **overrides) -> QFont:
    """Painter helper: UI family + size/weight hints from ``widget``."""
    return UiFont.get_instance().paint_font(widget, **overrides)


def apply_ui_font(widget: QWidget, **overrides) -> QFont:
    """Apply ``ui_font(**overrides)`` onto ``widget``."""
    return UiFont.get_instance().apply(widget, **overrides)


def apply_text_color(widget: QWidget, color: QColor | None) -> None:
    """Set text color via palette; clear color-only stylesheets.

    Never use ``setStyleSheet("color:…")`` on toolkit text widgets — Qt then
    ignores ``setFont()`` when painting.

    Starts from the application palette so Window/Base roles track the active
    theme; only WindowText/Text are overridden. Re-call after reparent —
    Qt can wipe ``WA_SetPalette`` colors on ``ParentChange``.
    """
    sheet = widget.styleSheet() or ""
    if sheet.strip():
        stripped = sheet.strip().rstrip(";")
        if stripped.lower().startswith("color:") and "{" not in stripped:
            widget.setStyleSheet("")
    if color is None or not color.isValid():
        return
    app = QApplication.instance()
    palette = QPalette(app.palette()) if app is not None else QPalette(widget.palette())
    palette.setColor(QPalette.ColorRole.WindowText, color)
    palette.setColor(QPalette.ColorRole.Text, color)
    widget.setPalette(palette)
    widget.setAttribute(Qt.WidgetAttribute.WA_SetPalette, True)


__all__ = [
    "UiFont",
    "apply_text_color",
    "apply_ui_font",
    "paint_font",
    "rebase_font",
    "ui_font",
]
