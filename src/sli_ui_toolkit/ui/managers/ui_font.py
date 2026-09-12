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
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.managers.ui_scale import UiScale


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
        if isinstance(app, QApplication):
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
        """Copy of the current UI face (size from the application font).

        The inherited size is scaled by ``UiScale``: the application font
        itself always stays at the design size, and scaling happens here at
        resolution time. ``resolve()`` / ``rebase()`` build on this, so
        every UI text path ends up multiplied exactly once.
        """
        app = QApplication.instance()
        if isinstance(app, QApplication):
            font = QFont(app.font())
        else:
            font = QFont()
        family = self.family()
        if family:
            font.setFamily(family)
        factor = UiScale.get_instance().factor()
        if factor != 1.0:
            if font.pixelSize() > 0:
                font.setPixelSize(UiScale.get_instance().scaled_px(font.pixelSize()))
            else:
                font.setPointSizeF(font.pointSizeF() * factor)
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
        """Build a font from the UI face with optional local overrides.

        ``pixel_size`` / ``point_size`` are **design values** — they are
        multiplied by the current ``UiScale`` factor here (exactly once),
        so callers pass the 1.0-baseline size and never touch the factor
        themselves. ``rebase()`` passes source-font sizes through here too;
        its sources are design-sized (the application font is never scaled
        in place), so the multiply applies to them exactly once as well.
        """
        scale = UiScale.get_instance()
        font = self.base_font()
        if family:
            font.setFamily(family)
        if pixel_size is not None:
            font.setPixelSize(scale.scaled_px(pixel_size))
        elif point_size is not None:
            font.setPointSizeF(float(point_size) * scale.factor())
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
        """``setFont(resolve(...))`` on ``widget`` and return the font used.

        Also keeps ``widget`` in sync with any *future* real font change
        (``font_changed``) using these same ``overrides`` -- not just the
        one baked in by this call. ``resolve()`` reads
        ``QApplication.font()`` at the exact moment it runs, and
        ``QWidget.setFont()`` marks ``WA_SetFont``, so Qt never
        retroactively re-cascades a later ``ApplicationFontChange`` onto a
        widget on its own. A widget constructed before the host finishes
        its own startup font correction (``FontManager.apply_from_state()``
        in Improve-ImgSLI, or equivalent) would otherwise bake in whatever
        transient system-fallback font was active at that moment and never
        recover -- confirmed live via a plain ``QLabel`` stuck on a 10pt
        fallback face while the app's real UI font (12pt) was already/about
        to be set moments later in that same startup sequence, previously
        "fixed" only by accident (an unrelated full-widget-tree
        unpolish+polish pass happening to run for a different reason).
        ``Label`` already covers itself the same way internally (see its
        own ``font_changed``-connected ``_apply_style``) -- this generalizes
        the same protection to any other ``apply()`` caller, a bare
        ``QLabel`` included, so callers don't each need their own
        `font_changed` plumbing.

        Safe against ``widget`` being destroyed later: disconnects itself
        via ``widget.destroyed`` rather than leaving a dangling connection
        to a freed C++ object."""
        font = self.resolve(**overrides)
        widget.setFont(font)

        def _resync() -> None:
            widget.setFont(self.resolve(**overrides))

        connection = self.font_changed.connect(_resync)
        scale = UiScale.get_instance()
        scale_connection = scale.scale_changed.connect(_resync)

        def _cleanup() -> None:
            # Best-effort teardown: at interpreter/app shutdown the
            # connection may already be gone (sender destroyed first), and
            # shiboken emits a RuntimeWarning instead of raising — silence
            # the harmless noise.
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    self.font_changed.disconnect(connection)
                except (RuntimeError, TypeError):
                    pass
                try:
                    scale.scale_changed.disconnect(scale_connection)
                except (RuntimeError, TypeError):
                    pass

        widget.destroyed.connect(_cleanup)
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


def rebase_family(font: QFont | None = None) -> QFont:
    """Force the UI family onto ``font``, preserving its size exactly.

    ``rebase_font`` treats the source size as design space and multiplies it
    by the UiScale factor; fonts that are *already* scale-resolved
    (``paint_font()``/``ui_font()`` results, or live widget metrics such as
    ``getItemFont()``) must not be scaled a second time — this is the
    size-preserving, family-only variant for those.
    """
    result = QFont(font if font is not None else QFont())
    family = UiFont.get_instance().family()
    if family:
        result.setFamily(family)
    return result


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
    palette = QPalette(app.palette()) if isinstance(app, QApplication) else QPalette(widget.palette())
    palette.setColor(QPalette.ColorRole.WindowText, color)
    palette.setColor(QPalette.ColorRole.Text, color)
    widget.setPalette(palette)
    widget.setAttribute(Qt.WidgetAttribute.WA_SetPalette, True)


# Fudge added by measure_text_width so panels sized from it never clip glyphs.
_TEXT_WIDTH_FUDGE = 8


def measure_text_width(fm: QFontMetrics, text: str) -> int:
    """Layout-safe text width: ``max(horizontalAdvance, boundingRect) + 8px``.

    Plain ``horizontalAdvance`` under-measures some UI fonts (kerning,
    hinting, wide glyphs like "…"), so a panel sized exactly to it clips the
    painted text. This is the toolkit's text-width normalizer — rows, menu
    items and flyout cells should size from it (see ``ButtonRow.size`` /
    ``ContextMenuRow``), not from raw ``QFontMetrics``.
    """
    if not text:
        return 0
    return max(fm.horizontalAdvance(text), fm.boundingRect(text).width()) + _TEXT_WIDTH_FUDGE


__all__ = [
    "UiFont",
    "apply_text_color",
    "apply_ui_font",
    "measure_text_width",
    "paint_font",
    "rebase_font",
    "ui_font",
]
