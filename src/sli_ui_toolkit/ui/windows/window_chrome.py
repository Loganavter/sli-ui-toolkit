from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
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
        from sli_ui_toolkit.ui.windows import frameless

        if cfg.resize_margin is not None:
            frameless.RESIZE_MARGIN = int(cfg.resize_margin)

        # Outer resize band: the window surface extends ``band`` px beyond
        # the visible body on every side (transparent — the rounded body is
        # inset), so the frameless edge-resize zone straddles the visible
        # edge and can be grabbed from outside the body, like a native frame.
        # The app keeps thinking in content size: ``resize``/``setGeometry``
        # are re-expanded by 2*band (inside ``apply_frameless``), and the
        # layout/title-bar/body are inset by ``band`` here.
        band = 0
        if cfg.resizable:
            band = (
                int(cfg.resize_margin)
                if cfg.resize_margin is not None
                else int(frameless.RESIZE_MARGIN)
            )

        apply_frameless(window, resizable=cfg.resizable, outer_band=band or None)
        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        window.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        window.setAutoFillBackground(False)

        bg_color = resolve_window_bg_color(window, cfg.bg_token)
        if isinstance(window, QDialog):
            reapply_msgbox_transparency(window)

        paint_fn, paint_state = make_rounded_paint_event(bg_color, cfg.corner_radius)
        window.paintEvent = paint_fn.__get__(window, type(window))  # type: ignore[method-assign]
        setattr(window, "_csd_paint_state", paint_state)

        bg_layer = None
        if isinstance(window, QDialog):
            bg_layer = CsdRoundedBackground(window, paint_state)
            bg_layer.sync_geometry()
            bg_layer.show()
            bg_layer.lower()
            setattr(window, "_csd_bg_layer", bg_layer)

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
        base_layout_margins = None
        if layout is not None:
            l, t, r, b = cast("tuple[int, int, int, int]", layout.getContentsMargins())
            # The title bar lives *over* the content: the layout's top
            # margin compensates for its height. The bar scales with UiScale
            # (see CustomTitleBar.on_scale_changed), so the compensation
            # must scale with it too — otherwise the first content row ends
            # up underneath the bar. The outer resize band insets the whole
            # content by ``band`` on every side.
            base_layout_margins = (l, t, r, b)
            layout.setContentsMargins(
                l + band,
                t + scaled_px(CustomTitleBar.HEIGHT) + band,
                r + band,
                b + band,
            )
            if hasattr(window, "adjustSize"):
                window.adjustSize()

        title_bar.setGeometry(
            band,
            band,
            max(1, window.width() - 2 * band),
            scaled_px(CustomTitleBar.HEIGHT),
        )
        title_bar.show()
        title_bar.raise_()

        geom_filter = TitleBarGeometryFilter(window, title_bar)  # type: ignore[arg-type]
        window.installEventFilter(geom_filter)
        setattr(window, "_csd_geom_filter", geom_filter)
        setattr(window, "_csd_title_bar", title_bar)

        chrome = cls(
            window,
            title_bar=title_bar,
            paint_state=paint_state,
            geom_filter=geom_filter,
            bg_layer=bg_layer,
            bg_token=cfg.bg_token,
        )
        setattr(window, "_window_chrome", chrome)
        chrome._base_layout_margins = base_layout_margins
        chrome._sync_background()
        # Do not setMask the shell — binary masks destroy AA corners painted
        # by CsdRoundedBackground / the dialog paintEvent.
        window.clearMask()

        def _resync_csd_scale(_factor) -> None:
            try:
                layout = window.layout()
                if layout is None:
                    return
                base = chrome._base_layout_margins
                if base is not None:
                    l, t, r, b = base
                    layout.setContentsMargins(
                        l + band,
                        t + scaled_px(CustomTitleBar.HEIGHT) + band,
                        r + band,
                        b + band,
                    )
                title_bar.setGeometry(
                    band,
                    band,
                    max(1, window.width() - 2 * band),
                    scaled_px(CustomTitleBar.HEIGHT),
                )
                title_bar.raise_()
                window.updateGeometry()
            except RuntimeError:
                # The window was destroyed while the (process-wide) UiScale
                # signal still lives — drop the stale re-sync silently.
                return

        chrome._csd_scale_connection = UiScale.get_instance().scale_changed.connect(
            _resync_csd_scale
        )

        def _drop_csd_scale_resync() -> None:
            # Best-effort teardown: at shutdown the sender (UiScale) may
            # already be destroyed; shiboken warns instead of raising.
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    UiScale.get_instance().scale_changed.disconnect(
                        chrome._csd_scale_connection
                    )
                except (RuntimeError, TypeError):
                    pass

        window.destroyed.connect(_drop_csd_scale_resync)

        if band > 0:
            # ``apply_frameless`` already installed the geometry patch (via
            # ``frameless._patch_outer_band_geometry``); the app sized the
            # window before decorating and ``adjustSize`` may have re-clamped
            # it — expand the current surface now, or the band (and its
            # grab-from-outside zone) would not exist until the next resize.
            try:
                window._csd_outer_band_patch[0](  # type: ignore[attr-defined]
                    window.width() + 2 * band,
                    window.height() + 2 * band,
                )
            except Exception:
                pass

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
