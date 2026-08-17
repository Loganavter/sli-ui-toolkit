"""CustomTitleBar appearance — fill, title color, rounded paint, theme.

The bar paints its own anti-aliased top-rounded fill (``paint_top_rounded_background``);
colors resolve through ``resolve_titlebar_color`` so a missing token falls
back safely. Font/theme changes trigger zone repaints and a balance resync.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.windows.rounded_body import paint_top_rounded_background

from .zones import resolve_titlebar_color


class _TitleBarAppearanceApi:
    """Mixin: fill / title color overrides, the rounded paint, theme hooks.

    Not a QWidget itself — mixed into CustomTitleBar; relies on instance
    attributes assigned in ``CustomTitleBar.__init__`` (``_bg_color_override``,
    ``_title_label``, ``_target_window``, zone hosts) and on QWidget methods
    (update, rect). Calls the layout mixin's ``_sync_balance_spacer`` /
    ``_schedule_balance_resync``.
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real assignments live in CustomTitleBar.__init__ (widget.py), the
    # sibling mixins, or QWidget itself. Plain annotations only (no
    # `= value`); QWidget-provided names are ``Any``.
    _bg_color_override: QColor | None
    _title_label: Any
    _target_window: Any
    CORNER_RADIUS: int
    update: Any
    rect: Any
    window: Any
    findChildren: Any
    _sync_balance_spacer: Any
    _schedule_balance_resync: Any
    _leading_host: Any
    _trailing_host: Any
    _center_host: Any

    def set_background_color(self, color: QColor | str | None) -> None:
        """Override the title bar fill. ``None`` reverts to the theme token."""
        self._bg_color_override = QColor(color) if color is not None else None
        self.update()

    def set_title_color(self, color: QColor | str | None) -> None:
        """Override the title text color. ``None`` reverts to the theme token."""
        self._title_label.setTextColor(QColor(color) if color is not None else None)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            color = (
                self._bg_color_override
                if self._bg_color_override is not None
                else resolve_titlebar_color("titlebar.background", fallback="Window")
            )
            window = self._target_window if self._target_window is not None else self.window()
            squared = bool(
                window is not None
                and (window.isMaximized() or window.isFullScreen())
            )
            paint_top_rounded_background(
                painter,
                QRectF(self.rect()),
                color=color,
                radius=float(self.CORNER_RADIUS),
                squared=squared,
            )
        finally:
            painter.end()
        QWidget.paintEvent(self, event)  # type: ignore[arg-type]

    def _on_theme_changed(self, *_args) -> None:
        self.update()
        self._title_label.update()

    def changeEvent(self, event) -> None:
        QWidget.changeEvent(self, event)  # type: ignore[arg-type]
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        ):
            # Title Label re-applies itself; menu triggers need a repaint so
            # TextContent picks up the new QApplication.font() family.
            self._title_label.update()
            for zone in (
                getattr(self, "_leading_host", None),
                getattr(self, "_trailing_host", None),
                getattr(self, "_center_host", None),
            ):
                if zone is None:
                    continue
                zone.update()
                for child in zone.findChildren(QWidget):
                    child.update()
            self.update()
            # Menu strip buttons re-measure on font change; balance must follow.
            self._sync_balance_spacer()
            self._schedule_balance_resync()
