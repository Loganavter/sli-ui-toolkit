"""In-window selection rubber-band (not QRubberBand / Qt.Popup)."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.overlays.in_window_overlay import (
    TopLevelInWindowOverlay,
)


class MarqueeBandOverlay(TopLevelInWindowOverlay):
    """Pointer-transparent selection rectangle on the host window overlay.

    Same stacking model as ``DragDropOverlay``: in-window child, no
    ``grabMouse`` (Wayland only allows grabs on ``Qt.Popup``). Pair with
    ``MarqueeBandGesture`` for drag tracking.
    """

    def __init__(self, parent: QWidget):
        super().__init__(
            parent,
            close_on_background=False,
            close_on_escape=False,
            close_on_deactivate=False,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._accent = QColor("#0078D4")
        #: Host override flag: ``set_accent()`` pins an explicit color that
        #: theme switches must not clobber; otherwise the accent re-resolves
        #: from the active palette on every ``theme_changed``.
        self._accent_custom = False
        self._active = False
        self._refresh_accent_from_theme()
        try:
            from sli_ui_toolkit.theme import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass

    def _refresh_accent_from_theme(self) -> None:
        try:
            from sli_ui_toolkit.theme import ThemeManager

            color = QColor(ThemeManager.get_instance().get_color("accent"))
            if color.isValid():
                self._accent = color
        except Exception:
            pass

    def _on_theme_changed(self, *_args) -> None:
        if not self._accent_custom:
            self._refresh_accent_from_theme()
        if self.isVisible():
            self.update()

    def set_accent(self, color: QColor) -> None:
        self._accent = QColor(color)
        self._accent_custom = True
        if self.isVisible():
            self.update()

    def accent(self) -> QColor:
        return QColor(self._accent)

    def set_band(self, rect: QRect | None) -> None:
        """Show ``rect`` in parent-local coordinates, or hide when empty/None.

        No-op when the band is already visible at the same geometry: the
        gesture drives this per mousemove (100+/s), and a redundant
        setGeometry + raise + repaint on every event makes the band edge
        judder against compositor paint frames. Stacking is established on
        show — but sibling flyouts (context menus explicitly restack
        themselves above everything on open) can cover the band
        afterwards, so the no-op path still re-raises when this widget is
        no longer topmost. That restack needs no repaint.
        """
        if rect is None or not rect.isValid() or rect.isEmpty():
            self._active = False
            self.hide()
            return
        if self._active and self.isVisible() and self.geometry() == rect:
            self._ensure_stacking()
            return
        self._active = True
        self.setGeometry(rect)
        self.raise_()
        self.show()
        self.update()

    def _ensure_stacking(self) -> None:
        """Re-raise only when a sibling got above the band (no repaint)."""
        try:
            parent = self.parentWidget()
            if parent is None:
                return
            siblings = parent.children()
            if siblings and siblings[-1] is not self:
                self.raise_()
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if not self._active or not self.isVisible():
            return
        painter = QPainter(self)
        fill = QColor(self._accent)
        fill.setAlpha(48)
        border = QColor(self._accent)
        border.setAlpha(200)
        painter.fillRect(self.rect(), fill)
        painter.setPen(QPen(border, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
