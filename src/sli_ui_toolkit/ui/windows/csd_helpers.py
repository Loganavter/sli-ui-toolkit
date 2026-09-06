from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from .custom_title_bar import CustomTitleBar
from .rounded_body import (
    apply_bottom_rounded_mask,
    apply_rounded_window_mask,
    apply_top_rounded_mask,
    paint_rounded_window_background,
)


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
        from sli_ui_toolkit.ui.windows.frameless.geometry import resolve_csd_band

        band = resolve_csd_band(dialog)
        self.setGeometry(
            band,
            band,
            max(1, dialog.width() - 2 * band),
            max(1, dialog.height() - 2 * band),
        )

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


def _mask_edge_hosts(dialog: QWidget, radius: float, squared: bool) -> None:
    """Systematic CSD corner contract: clip every direct child that reaches
    a rounded corner zone to that corner's silhouette.

    The window's rounded corners stay transparent only while no opaque
    child paints its square corners over them (the inspector bug: an opaque
    tab pane left a rectangular corner inside the rounded window). Instead
    of trusting each host to apply the masks itself, inspect every direct
    child's rect against the window's four corner zones here — masking a
    transparent parent clips its whole subtree, so "reaches a corner zone"
    is the only condition that matters. Children spanning both the top and
    the bottom corners get the full silhouette mask.
    """
    from PySide6.QtWidgets import QWidget as _QWidget

    width = int(dialog.width())
    height = int(dialog.height())
    if width <= 0 or height <= 0:
        return
    tolerance = max(2, int(radius))
    title_bar = getattr(dialog, "_csd_title_bar", None)
    bg_layer = getattr(dialog, "_csd_bg_layer", None)
    for child in dialog.findChildren(
        _QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
    ):
        if child.isWindow() or not child.isVisibleTo(dialog):
            continue
        if child is title_bar or child is bg_layer:
            # These paint the rounded silhouette themselves (AA) — a binary
            # mask on them would destroy the antialiased edge.
            continue
        rect = child.geometry()
        touches_top = rect.top() <= tolerance
        touches_bottom = rect.bottom() >= height - tolerance
        touches_left = rect.left() <= tolerance
        touches_right = rect.right() >= width - tolerance
        top = (touches_top and touches_left) or (touches_top and touches_right)
        bottom = (touches_bottom and touches_left) or (
            touches_bottom and touches_right
        )
        if not top and not bottom:
            continue
        if top and bottom:
            apply_rounded_window_mask(child, radius=radius, squared=squared)
        elif top:
            apply_top_rounded_mask(child, radius=radius, squared=squared)
        else:
            apply_bottom_rounded_mask(child, radius=radius, squared=squared)


def _sync_csd_layout_margins(dialog: QWidget) -> None:
    """Collapse the outer-band layout inset in maximized/fullscreen.

    Mirrors ``MainWindow._sync_csd_content_band``: the root layout insets
    content by the outer resize band (so the visible body sits inside the
    transparent grab margin). In maximized/fullscreen the band is gone and
    keeping the inset leaves a strip of window background around the content.
    """
    chrome = getattr(dialog, "_window_chrome", None)
    base = getattr(chrome, "_base_layout_margins", None) if chrome is not None else None
    if base is None:
        return
    layout = dialog.layout()
    if layout is None:
        return
    from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
    from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar
    from sli_ui_toolkit.ui.windows.frameless.geometry import resolve_csd_band

    band = resolve_csd_band(dialog)
    try:
        l, t, r, b = base  # type: ignore[misc]
        layout.setContentsMargins(
            l + band,
            t + scaled_px(CustomTitleBar.HEIGHT) + band,
            r + band,
            b + band,
        )
        layout.invalidate()
        layout.activate()
    except Exception:
        pass


def sync_csd_chrome(dialog: QWidget) -> None:
    """Re-fit CSD background and title bar to the current size.

    Intentionally does **not** ``setMask`` the top-level shell: binary masks
    destroy the antialiased corner painted by :class:`CsdRoundedBackground`.
    Opaque content hosts that reach a corner zone are masked automatically
    by :func:`_mask_edge_hosts`.
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
    _sync_csd_layout_margins(dialog)
    bg_layer = getattr(dialog, "_csd_bg_layer", None)
    if bg_layer is not None:
        bg_layer.sync_geometry()
        bg_layer.lower()
        bg_layer.update()
    title_bar = getattr(dialog, "_csd_title_bar", None)
    if title_bar is not None:
        from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
        from sli_ui_toolkit.ui.windows.frameless.geometry import resolve_csd_band

        band = resolve_csd_band(dialog)
        title_bar.setGeometry(
            band,
            band,
            max(1, width - 2 * band),
            scaled_px(CustomTitleBar.HEIGHT),
        )
        title_bar.raise_()
        # Force the bar's paint synchronously: after a live scale change the
        # geometry may heal on a later tick while the stale frame stays on
        # screen (translucent-window repaint quirk on some compositors).
        try:
            title_bar.repaint()
        except Exception:
            pass
    state = getattr(dialog, "_csd_paint_state", None)
    if state is not None:
        _mask_edge_hosts(
            dialog,
            radius=float(state.get("radius", 10)),
            squared=bool(dialog.isMaximized() or dialog.isFullScreen()),
        )
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
