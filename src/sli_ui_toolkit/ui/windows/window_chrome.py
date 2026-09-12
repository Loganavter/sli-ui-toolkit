from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.windows.csd_helpers import (
    CsdRoundedBackground,
    TitleBarGeometryFilter,
    reapply_msgbox_transparency,
)
from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar
from sli_ui_toolkit.ui.windows.frameless import apply_frameless
from sli_ui_toolkit.ui.windows.rounded_body import (
    DEFAULT_CORNER_RADIUS,
    make_rounded_paint_event,
    resolve_window_bg_color,
)


@dataclass(slots=True)
class WindowChromeConfig:
    title: str = ""
    title_bar: CustomTitleBar | None = None
    corner_radius: int = DEFAULT_CORNER_RADIUS
    bg_token: str = "Window"
    resizable: bool = True
    resize_margin: int | None = None
    show_minimize: bool = False
    show_maximize: bool = False
    show_close: bool = True
    minimize_icon: Any = None
    maximize_icon: Any = None
    restore_icon: Any = None
    close_icon: Any = None


class WindowChrome:
    """Install client-side window decorations on a top-level widget."""

    def __init__(
        self,
        window: QWidget,
        *,
        title_bar: CustomTitleBar,
        paint_state: dict,
        geom_filter: QObject,
        bg_layer: CsdRoundedBackground | None = None,
        bg_token: str = "Window",
    ) -> None:
        self._window = window
        self._title_bar = title_bar
        self._paint_state = paint_state
        self._geom_filter = geom_filter
        self._bg_layer = bg_layer
        self._bg_token = bg_token
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        window.destroyed.connect(self._disconnect_theme)

    @classmethod
    def install(cls, window: QWidget, *, config: WindowChromeConfig | None = None) -> WindowChrome:
        cfg = config or WindowChromeConfig()
        if cfg.resize_margin is not None:
            from sli_ui_toolkit.ui.windows import frameless

            frameless.RESIZE_MARGIN = int(cfg.resize_margin)

        apply_frameless(window, resizable=cfg.resizable)
        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        window.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        window.setAutoFillBackground(False)

        bg_color = resolve_window_bg_color(window, cfg.bg_token)
        if isinstance(window, QDialog):
            reapply_msgbox_transparency(window)

        paint_fn, paint_state = make_rounded_paint_event(bg_color, cfg.corner_radius)
        window.paintEvent = paint_fn.__get__(window, type(window))  # type: ignore[method-assign]
        window._csd_paint_state = paint_state

        bg_layer = None
        if isinstance(window, QDialog):
            bg_layer = CsdRoundedBackground(window, paint_state)
            bg_layer.sync_geometry()
            bg_layer.show()
            bg_layer.lower()
            window._csd_bg_layer = bg_layer

        if cfg.title_bar is not None:
            title_bar = cfg.title_bar
        else:
            title_bar = CustomTitleBar(
                parent=window,
                title=cfg.title or window.windowTitle(),
                minimize_icon=cfg.minimize_icon,
                maximize_icon=cfg.maximize_icon,
                restore_icon=cfg.restore_icon,
                close_icon=cfg.close_icon,
                show_minimize=cfg.show_minimize,
                show_maximize=cfg.show_maximize,
                show_close=cfg.show_close,
            )
        title_bar.attach_window(window)

        layout = window.layout()
        if layout is not None:
            l, t, r, b = layout.getContentsMargins()
            layout.setContentsMargins(l, t + CustomTitleBar.HEIGHT, r, b)
            if hasattr(window, "adjustSize"):
                window.adjustSize()

        title_bar.setGeometry(0, 0, window.width(), CustomTitleBar.HEIGHT)
        title_bar.show()
        title_bar.raise_()

        geom_filter = TitleBarGeometryFilter(window, title_bar)  # type: ignore[arg-type]
        window.installEventFilter(geom_filter)
        window._csd_geom_filter = geom_filter
        window._csd_title_bar = title_bar

        chrome = cls(
            window,
            title_bar=title_bar,
            paint_state=paint_state,
            geom_filter=geom_filter,
            bg_layer=bg_layer,
            bg_token=cfg.bg_token,
        )
        window._window_chrome = chrome
        chrome._sync_background()
        # Do not setMask the shell — binary masks destroy AA corners painted
        # by CsdRoundedBackground / the dialog paintEvent.
        window.clearMask()
        return chrome

    def title_bar(self) -> CustomTitleBar:
        return self._title_bar

    def set_background_token(self, token: str) -> None:
        self._bg_token = token
        self._sync_background()

    def set_background_color(self, color: QColor) -> None:
        self._paint_state["color"] = QColor(color)
        self._window.update()
        if self._bg_layer is not None:
            self._bg_layer.update()

    def _sync_background(self) -> None:
        color = resolve_window_bg_color(self._window, self._bg_token)
        self.set_background_color(color)

    def _on_theme_changed(self, *_args) -> None:
        self._sync_background()

    def _disconnect_theme(self, *_args) -> None:
        try:
            self._theme_manager.theme_changed.disconnect(self._on_theme_changed)
        except Exception:
            pass


def set_window_bg_color(window: QWidget, color: QColor) -> None:
    chrome = getattr(window, "_window_chrome", None)
    if chrome is not None:
        chrome.set_background_color(color)
        return
    state = getattr(window, "_csd_paint_state", None)
    if state is not None:
        state["color"] = QColor(color)
        window.update()
        bg_layer = getattr(window, "_csd_bg_layer", None)
        if bg_layer is not None:
            bg_layer.update()
