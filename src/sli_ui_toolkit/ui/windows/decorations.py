"""Apply client-side decorations to a top-level dialog.

The dialog keeps its existing layout and content. A frameless, translucent
background is installed, a :class:`CustomTitleBar` is added above the
existing layout, and the dialog's own ``paintEvent`` is monkey-patched to
draw a rounded background — same approach the host app's main window uses
so dialogs render with identical shape and shadowing semantics.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QDialog

from .custom_title_bar import CustomTitleBar
from .frameless import apply_frameless


DEFAULT_CORNER_RADIUS = 10


def _make_rounded_paint_event(bg_color: QColor, radius: int):
    """Return a paintEvent function bound at call-time to draw a rounded bg.

    Mirrors the main window's paintEvent (top corners only rounded, AA fill,
    no border). Stored values are read by reference so callers can mutate
    ``bg_color`` via :func:`set_dialog_bg_color`.
    """

    state = {"color": QColor(bg_color), "radius": int(radius)}

    def paint_event(self, event):  # noqa: ARG001 — Qt API
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(state["color"])
            rect = QRectF(self.rect())
            is_max = self.isMaximized()
            is_full = self.isFullScreen()
            r = 0.0 if (is_max or is_full) else float(state["radius"])
            path = QPainterPath()
            if r <= 0.0:
                path.addRect(rect)
            else:
                w, h = rect.width(), rect.height()
                path.moveTo(0.0, h)
                path.lineTo(0.0, r)
                path.arcTo(0.0, 0.0, 2 * r, 2 * r, 180.0, -90.0)
                path.lineTo(w - r, 0.0)
                path.arcTo(w - 2 * r, 0.0, 2 * r, 2 * r, 90.0, -90.0)
                path.lineTo(w, h)
                path.closeSubpath()
            painter.drawPath(path)
        finally:
            painter.end()

    return paint_event, state


def set_dialog_bg_color(dialog: QDialog, color: QColor) -> None:
    state = getattr(dialog, "_csd_paint_state", None)
    if state is not None:
        state["color"] = QColor(color)
        dialog.update()


class _TitleBarGeometryFilter(QObject):
    def __init__(self, dialog: QDialog, title_bar: CustomTitleBar):
        super().__init__(dialog)
        self._dialog = dialog
        self._title_bar = title_bar

    def eventFilter(self, obj, event):
        if obj is self._dialog and event.type() in (
            QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.WindowStateChange,
        ):
            self._title_bar.setGeometry(
                0, 0, self._dialog.width(), CustomTitleBar.HEIGHT
            )
            self._title_bar.raise_()
            self._dialog.update()
        return False


def decorate_dialog(
    dialog: QDialog,
    *,
    title: str = "",
    minimize_icon: Any = None,
    maximize_icon: Any = None,
    restore_icon: Any = None,
    close_icon: Any = None,
    show_minimize: bool = False,
    show_maximize: bool = False,
    show_close: bool = True,
    bg_color: QColor | None = None,
    corner_radius: int = DEFAULT_CORNER_RADIUS,
) -> CustomTitleBar:
    """Install CSD on ``dialog`` and return the inserted title bar."""

    apply_frameless(dialog)
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    dialog.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    dialog.setAutoFillBackground(False)

    if bg_color is None:
        bg_color = QColor(dialog.palette().color(dialog.backgroundRole()))
        if not bg_color.isValid() or bg_color.alpha() == 0:
            bg_color = QColor("#1e1e1e")

    # QMessageBox / styled dialogs paint their own panel via QStyle. Suppress
    # it with an explicit stylesheet so the dialog's own background is fully
    # transparent and only our paintEvent draws the rounded shape.
    try:
        from PySide6.QtWidgets import QMessageBox
        if isinstance(dialog, QMessageBox):
            existing = dialog.styleSheet() or ""
            patch = "QMessageBox { background: transparent; }"
            if patch not in existing:
                dialog.setStyleSheet((existing + "\n" + patch).strip())
    except Exception:
        pass

    # Monkey-patch the dialog's paintEvent. This mirrors the main window's
    # approach (paintEvent override on QMainWindow subclass) so dialogs draw
    # exactly the same rounded shape — no helper child widget that the
    # native QDialog/QMessageBox panel could leak past.
    paint_fn, paint_state = _make_rounded_paint_event(bg_color, corner_radius)
    dialog.paintEvent = paint_fn.__get__(dialog, type(dialog))
    dialog._csd_paint_state = paint_state

    title_bar = CustomTitleBar(
        parent=dialog,
        title=title or dialog.windowTitle(),
        minimize_icon=minimize_icon,
        maximize_icon=maximize_icon,
        restore_icon=restore_icon,
        close_icon=close_icon,
        show_minimize=show_minimize,
        show_maximize=show_maximize,
        show_close=show_close,
    )
    title_bar.attach_window(dialog)

    layout = dialog.layout()
    if layout is not None:
        l, t, r, b = layout.getContentsMargins()
        layout.setContentsMargins(l, t + CustomTitleBar.HEIGHT, r, b)
        dialog.adjustSize()

    title_bar.setGeometry(0, 0, dialog.width(), CustomTitleBar.HEIGHT)
    title_bar.show()
    title_bar.raise_()

    geom_filter = _TitleBarGeometryFilter(dialog, title_bar)
    dialog.installEventFilter(geom_filter)
    dialog._csd_geom_filter = geom_filter
    dialog._csd_title_bar = title_bar

    return title_bar
