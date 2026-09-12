"""Window controls cluster — a real widget owning the min/max/close buttons.

``WindowControlsCluster`` is a self-contained child widget: it owns the
button container, creates the three control buttons, places them at
deterministic slots (no layout timing involved — each slot depends only on
the design width and the count of *existing* controls), rescales them with
the UiScale factor, and refreshes maximize/restore icons from the target
window's state. The title bar only wires its signals and delegates; it
keeps the corner mask and the flyout sweep (bar-level concerns).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.windows.window_controls import WindowControlsHandle


class WindowControlsCluster(QWidget):
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()

    def __init__(
        self,
        parent=None,
        *,
        minimize_icon: Any = None,
        maximize_icon: Any = None,
        restore_icon: Any = None,
        close_icon: Any = None,
        show_minimize: bool = True,
        show_maximize: bool = True,
        show_close: bool = True,
        defer_close_click: Any = None,
        design_button_width: int = 46,
        design_height: int = 36,
        icon_size: int = 16,
        corner_radius: int = 10,
    ):
        super().__init__(parent)
        self._defer_close_click = defer_close_click
        self._maximize_icon = maximize_icon
        self._restore_icon = restore_icon
        self._design_button_width = int(design_button_width)
        self._design_height = int(design_height)
        self._icon_size = int(icon_size)
        self._corner_radius = int(corner_radius)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        buttons_layout = QHBoxLayout(self)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(0)

        self._min_btn: Button | None
        self._max_btn: Button | None
        self._close_btn: Button | None

        if show_minimize:
            self._min_btn = self._make_button(minimize_icon, "min")
            self._min_btn.clicked.connect(self.minimize_requested.emit)
        else:
            self._min_btn = None

        if show_maximize:
            self._max_btn = self._make_button(maximize_icon, "max")
            self._max_btn.clicked.connect(self.maximize_toggle_requested.emit)
        else:
            self._max_btn = None

        if show_close:
            self._close_btn = self._make_button(close_icon, "close")
            self._close_btn.clicked.connect(self.close_requested.emit)
        else:
            self._close_btn = None

        self._control_count = sum(
            1 for btn in (self._min_btn, self._max_btn, self._close_btn) if btn is not None
        )
        self._buttons: tuple[Button, ...] = tuple(
            btn for btn in (self._min_btn, self._max_btn, self._close_btn) if btn is not None
        )
        if self._control_count:
            self._resize_to_current()

    # -- buttons -----------------------------------------------------------

    def buttons(self) -> tuple[Button, ...]:
        """The existing control buttons, in (min, max, close) order."""
        return self._buttons

    def handle(self) -> WindowControlsHandle:
        return WindowControlsHandle(
            min_btn=self._min_btn,
            max_btn=self._max_btn,
            close_btn=self._close_btn,
            container=self,
        )

    def _make_button(self, icon: Any, role: str) -> Button:
        corner_radii = (0, self._corner_radius, 0, 0) if role == "close" else (0, 0, 0, 0)
        btn = Button(
            icon if icon is not None else QIcon(),
            variant="ghost",
            size=(self._design_button_width, self._design_height),
            icon_size=self._icon_size,
            corner_radii=corner_radii,
            # Closing tears down the window (session save, plugin teardown,
            # etc.) — let the press ripple finish first if the host asked
            # for that via defer_close_click. Min/maximize stay instant.
            defer_click=self._defer_close_click if role == "close" else None,
            parent=self,
        )
        btn.setObjectName("CustomTitleBarButton")
        btn.setProperty("titlebarRole", role)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        return btn

    # -- sizing ------------------------------------------------------------

    def set_design(
        self, button_width: int, height: int, corner_radius: int
    ) -> None:
        """Re-fit the cluster to the current scale factor and bar height."""
        self._design_button_width = int(button_width)
        self._corner_radius = int(corner_radius)
        self._resize_to_current()

    def _resize_to_current(self) -> None:
        cluster_w = self._control_count * scaled_px(self._design_button_width)
        height = scaled_px(self._design_height)
        self.setFixedWidth(cluster_w)
        self.setMinimumWidth(cluster_w)
        self.setFixedHeight(height)
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._layout_buttons()

    def _layout_buttons(self) -> None:
        """Place the control buttons at deterministic slots.

        The buttons resize in their OWN scale_changed handlers, which run
        after the bar's (subscription order) — a layout-based container
        re-activates in between and can compute slots from the previous
        factor's button sizes, leaving stale hit/hover zones under the
        rescaled visuals (observed: 1.0 -> 1.5 placed them at 17/80/143
        inside a 207px container). The slot of each button depends only on
        the design width, so place them explicitly and repaint — no layout
        timing involved.
        """
        width = scaled_px(self._design_button_width)
        height = scaled_px(self._design_height)
        slot = 0
        for btn in self._buttons:
            # Slot counter counts only the EXISTING controls — a dialog that
            # shows just the close button must place it at slot 0, not at
            # its index in the (min, max, close) enumeration (which would
            # put it outside the 1-control container and mask it away).
            btn.setGeometry(slot * width, 0, width, height)
            slot += 1
            btn.update()
        self.update()

    # -- window state ------------------------------------------------------

    def refresh_window_state(self, window) -> None:
        """Re-apply maximize icon + close-button corner shape for ``window``."""
        if self._max_btn is not None and window is not None:
            is_max = window.isMaximized()
            icon = self._restore_icon if is_max else self._maximize_icon
            if icon is not None:
                self._max_btn.setIcon(icon)

        if self._close_btn is None or window is None:
            return
        squared = window.isMaximized() or window.isFullScreen()
        radii = (0, 0, 0, 0) if squared else (0, self._corner_radius, 0, 0)
        if self._close_btn._corner_radii_px != radii:
            self._close_btn._corner_radii_px = radii
            self._close_btn.update()
