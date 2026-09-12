from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from .custom_title_bar import CustomTitleBar
from .rounded_body import paint_rounded_window_background


class CsdRoundedBackground(QWidget):
    """Child layer that paints the antialiased rounded dialog body.

    Must stay translucent: a binary ``setMask`` on the shell would destroy the
    AA edge, so this layer is what actually shapes the visible corners.
    """

    def __init__(self, dialog: QDialog, paint_state: dict[str, Any]):
        super().__init__(dialog)
        self._paint_state = paint_state
        self.setObjectName("CsdRoundedBackground")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAutoFillBackground(False)

    def sync_geometry(self) -> None:
        dialog = self.parentWidget()
        if dialog is None:
            return
        self.setGeometry(0, 0, dialog.width(), dialog.height())

    def paintEvent(self, event):  # noqa: ARG001 — Qt API
        dialog = self.parentWidget()
        squared = False
        if dialog is not None:
            squared = dialog.isMaximized() or dialog.isFullScreen()
        painter = QPainter(self)
        try:
            paint_rounded_window_background(
                painter,
                QRectF(self.rect()),
                color=self._paint_state["color"],
                radius=float(self._paint_state["radius"]),
                squared=squared,
            )
        finally:
            painter.end()


def sync_csd_chrome(dialog: QWidget) -> None:
    """Re-fit CSD background and title bar to the current size.

    Intentionally does **not** ``setMask`` the top-level shell: binary masks
    destroy the antialiased corner painted by :class:`CsdRoundedBackground`.
    Opaque content hosts that reach the edge should use
    ``apply_bottom_rounded_mask`` themselves (see main window).
    """
    if dialog is None:
        return
    try:
        width = int(dialog.width())
        height = int(dialog.height())
    except Exception:
        return
    if width <= 0 or height <= 0:
        return
    if getattr(dialog, "_csd_paint_state", None) is None and getattr(
        dialog, "_csd_title_bar", None
    ) is None:
        return
    bg_layer = getattr(dialog, "_csd_bg_layer", None)
    if bg_layer is not None:
        bg_layer.sync_geometry()
        bg_layer.lower()
        bg_layer.update()
    title_bar = getattr(dialog, "_csd_title_bar", None)
    if title_bar is not None:
        title_bar.setGeometry(0, 0, width, CustomTitleBar.HEIGHT)
        title_bar.raise_()
    # Drop any stale shell mask from older toolkit builds / maximize toggles.
    try:
        dialog.clearMask()
    except Exception:
        pass
    if hasattr(dialog, "update"):
        dialog.update()


class TitleBarGeometryFilter(QObject):
    def __init__(self, dialog: QDialog, title_bar: CustomTitleBar):
        super().__init__(dialog)
        self._dialog = dialog
        self._title_bar = title_bar

    def eventFilter(self, obj, event):
        dialog = getattr(self, "_dialog", None)
        title_bar = getattr(self, "_title_bar", None)
        if dialog is not None and title_bar is not None and obj is dialog and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
        ):
            sync_csd_chrome(dialog)
            on_show = getattr(dialog, "_csd_on_show", None)
            if event.type() == QEvent.Type.Show and callable(on_show):
                on_show()
        return False


def _transparent_msgbox_stylesheet(existing: str) -> str:
    rules = (
        "QMessageBox { background: transparent; border: none; }",
        "QMessageBox QLabel { background: transparent; color: palette(WindowText); }",
        "QMessageBox QPushButton { background: palette(Button); color: palette(ButtonText); }",
    )
    merged = existing or ""
    for rule in rules:
        if rule not in merged:
            merged = (merged + "\n" + rule).strip()
    return merged


def reapply_msgbox_transparency(dialog: QDialog) -> None:
    """Keep QMessageBox panels transparent after palette/QSS refresh."""
    try:
        if isinstance(dialog, QMessageBox):
            dialog.setStyleSheet(
                _transparent_msgbox_stylesheet(dialog.styleSheet() or "")
            )
    except Exception:
        pass
