"""CustomTitleBar — the window title bar (thin facade).

The class keeps the signals, sizing constants, construction, and the
bar-level wiring (corner mask, flyout sweep, drag). The window-control
buttons are a real self-contained child widget (``WindowControlsCluster``
in ``window_controls.py``) owning its own state; zones/balance live in
``zones.py``, drag in ``drag.py``, fill/paint in ``appearance.py``.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.windows.window_controls import WindowControlsHandle

from .appearance import _TitleBarAppearanceApi
from .drag import _TitleBarDragApi
from .window_controls import WindowControlsCluster
from .zones import (
    TitleAlign,
    _ensure_titlebar_label_variant,
    _zone_host,
    _TitleBarLayoutApi,
)


class CustomTitleBar(
    _TitleBarLayoutApi,
    _TitleBarDragApi,
    _TitleBarAppearanceApi,
    QWidget,
):
    """Window title bar. Mixins precede ``QWidget`` so their overrides
    (``resizeEvent``/``showEvent``/``paintEvent``/``changeEvent``/
    ``eventFilter``/mouse handlers) win the MRO; ``super()`` inside them
    still resolves to QWidget's own methods."""

    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()

    HEIGHT = 36
    BUTTON_WIDTH = 46
    ICON_SIZE = 16
    APP_ICON_SLOT = 28
    CORNER_RADIUS = 10

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "",
        icon: QIcon | None = None,
        minimize_icon: Any = None,
        maximize_icon: Any = None,
        restore_icon: Any = None,
        close_icon: Any = None,
        show_minimize: bool = True,
        show_maximize: bool = True,
        show_close: bool = True,
        defer_close_click: Any = None,
        bg_color: QColor | str | None = None,
        text_color: QColor | str | None = None,
    ):
        super().__init__(parent)
        self._defer_close_click = defer_close_click
        self._bg_color_override = QColor(bg_color) if bg_color is not None else None
        _ensure_titlebar_label_variant()
        self.setObjectName("CustomTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._maximize_icon = maximize_icon
        self._restore_icon = restore_icon
        self._app_icon_label: QLabel | None = None
        self._target_window: QWidget | None = None
        self._drag_start_global = None
        self._drag_enabled = True
        self._drag_exclusions: set[int] = set()
        self._title_align: TitleAlign = "center"
        self._title_visible = True
        self._balance_resync_scheduled = False
        self._buttons_relayout_scheduled = False
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

        self._scale = UiScale.get_instance()
        self._scale.scale_changed.connect(self.on_scale_changed)
        self._design_height = int(self.HEIGHT)
        self._design_button_width = int(self.BUTTON_WIDTH)
        self._design_icon_slot = int(self.APP_ICON_SLOT)
        self.setFixedHeight(scaled_px(self._design_height))

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Leading chrome stays flush-left. Balance spacers sit *inside* the
        # stretch pair so title centering does not shove File/Help when the
        # menu strip width changes (e.g. language switch).
        # [leading][left_balance][stretch][center][stretch][trailing][right_balance][buttons]
        self._leading_host = _zone_host(self)
        self._layout.addWidget(self._leading_host)

        self._left_balance = QWidget(self)
        self._left_balance.setFixedWidth(0)
        self._left_balance.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._layout.addWidget(self._left_balance)

        self._layout.addStretch(1)

        self._center_host = _zone_host(self)
        self._center_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        center_layout = self._center_host.layout()
        assert center_layout is not None
        self._title_label = Label(
            title,
            variant="titlebar",
            color=QColor(text_color) if text_color is not None else None,
            alignment=Qt.AlignmentFlag.AlignCenter,
            parent=self._center_host,
        )
        self._title_label.setObjectName("CustomTitleBarTitle")
        self._title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        center_layout.addWidget(self._title_label)
        self._layout.addWidget(self._center_host)

        self._layout.addStretch(1)

        self._trailing_host = _zone_host(self)
        self._layout.addWidget(self._trailing_host)

        self._balance_spacer = QWidget(self)
        self._balance_spacer.setFixedWidth(0)
        self._balance_spacer.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._layout.addWidget(self._balance_spacer)

        self._controls = WindowControlsCluster(
            self,
            minimize_icon=minimize_icon,
            maximize_icon=maximize_icon,
            restore_icon=restore_icon,
            close_icon=close_icon,
            show_minimize=show_minimize,
            show_maximize=show_maximize,
            show_close=show_close,
            defer_close_click=defer_close_click,
            design_button_width=self._design_button_width,
            design_height=self._design_height,
            icon_size=self.ICON_SIZE,
            corner_radius=self.CORNER_RADIUS,
        )
        self._controls.minimize_requested.connect(self.minimize_requested.emit)
        self._controls.maximize_toggle_requested.connect(
            self.maximize_toggle_requested.emit
        )
        self._controls.close_requested.connect(self.close_requested.emit)
        for btn in self._controls.buttons():
            self.register_drag_exclusion(btn)

        self._layout.addWidget(self._controls)
        self._controls_handle = self._controls.handle()
        self._apply_title_alignment()
        self._sync_balance_spacer()
        # Install on QApplication so we intercept key events targeting child
        # widgets (event filters only see events for the object they are
        # installed on, not descendants).
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        if icon is not None:
            self.set_icon(icon)

    def window_controls(self) -> WindowControlsHandle:
        return self._controls_handle

    # -- keyboard focus helpers --------------------------------------------

    def _focusable_buttons(self) -> list[QWidget]:
        """Visible, enabled, StrongFocus children sorted by on-screen x.

        findChildren() order reflects construction/reparent order, not
        layout position -- a button parented before being grouped into a
        sub-container can land anywhere in the QObject child list
        regardless of where it actually renders, which would make
        focus_first_button()/focus_last_button() land on the wrong end.
        """
        buttons: list[QWidget] = []
        for child in self.findChildren(QWidget):
            if (
                child.isVisible()
                and child.isEnabled()
                and child.focusPolicy() == Qt.FocusPolicy.StrongFocus
                and self.isAncestorOf(child)
                and child is not self
            ):
                buttons.append(child)
        return sorted(buttons, key=lambda w: w.mapToGlobal(w.rect().center()).x())

    def _set_child_focus(self, child: QWidget) -> None:
        """Set keyboard focus on *child* via ``setFocusProxy``.

        Qt's focus chain normally redirects ``setFocus()`` on a child
        widget to a StrongFocus ancestor.  ``setFocusProxy`` bypasses
        this by making the child the effective focus target when the
        title bar receives focus.
        """
        self.setFocusProxy(child)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.setFocusProxy(None)

    def focus_first_button(self) -> bool:
        """Focus the first focusable button in the title bar."""
        buttons = self._focusable_buttons()
        if buttons:
            self._set_child_focus(buttons[0])
            return True
        return False

    def focus_last_button(self) -> bool:
        """Focus the last focusable button in the title bar."""
        buttons = self._focusable_buttons()
        if buttons:
            self._set_child_focus(buttons[-1])
            return True
        return False

    def attach_window(self, window: QWidget) -> None:
        """Wire the controls cluster + this bar to a real window."""
        self._target_window = window
        self._controls.minimize_requested.connect(
            lambda: window.showMinimized()
        )
        self._controls.maximize_toggle_requested.connect(
            lambda: self._toggle_maximize(window)
        )
        self.close_requested.connect(window.close)
        window.installEventFilter(self)
        self._controls.refresh_window_state(window)

    @staticmethod
    def _toggle_maximize(window: QWidget) -> None:
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()

    def _hide_active_flyouts(self) -> None:
        try:
            from sli_ui_toolkit.managers import FlyoutManager

            mgr = FlyoutManager.get_instance()
            # Opening a tall in-window context menu (e.g. File with Open/Save
            # Project) can trigger a host Resize/Move while the menu is being
            # attached. Closing *all* flyouts here makes the first File/Help
            # click look like a no-op; keep context menus open.
            #
            # ``pinned=True`` flyouts (persistent HUDs, see FLYOUT_SYSTEM.md
            # "Pinned flyouts") are exempt from every other anchor-move/resize
            # auto-dismiss path in FlyoutManager (``_close_flyouts_with_moved_anchors``
            # explicitly skips them) -- this sweep must honor that same
            # contract instead of hiding them unconditionally.
            for flyout in list(getattr(mgr, "_registered_flyouts", ())):
                try:
                    if not flyout.isVisible():
                        continue
                    if getattr(flyout, "flyout_group", None) == "context_menu":
                        continue
                    if getattr(flyout, "pinned", False):
                        continue
                    flyout.hide()
                except RuntimeError:
                    mgr._registered_flyouts.discard(flyout)
                except Exception:
                    continue
            # Drop active pointer only if it was not a preserved context menu.
            active = getattr(mgr, "_active_flyout", None)
            if active is not None:
                try:
                    if (
                        not active.isVisible()
                        or getattr(active, "flyout_group", None) != "context_menu"
                    ):
                        mgr._active_flyout = None
                except Exception:
                    mgr._active_flyout = None
        except Exception:
            pass

    def eventFilter(self, obj, event):
        target_window = getattr(self, "_target_window", None)
        if obj is target_window and event.type() in (
            event.Type.WindowStateChange,
            event.Type.Resize,
            event.Type.Move,
        ):
            self._controls.refresh_window_state(target_window)
            self._apply_corner_mask()
            if event.type() in (event.Type.Resize, event.Type.Move):
                self._hide_active_flyouts()
            return super().eventFilter(obj, event)

        # Left/Right arrow navigation between focusable title bar buttons.
        # Installed on QApplication to intercept key events targeting child
        # widgets (Button, CsdMenuTrigger, etc.).
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                focused = QApplication.focusWidget()
                if focused is not None and self.isAncestorOf(focused):
                    buttons = self._focusable_buttons()
                    idx = next(
                        (i for i, b in enumerate(buttons) if b is focused), None
                    )
                    if idx is None and buttons:
                        self._set_child_focus(buttons[0])
                        return True
                    if idx is not None:
                        step = -1 if key == Qt.Key.Key_Left else 1
                        target = idx + step
                        if 0 <= target < len(buttons):
                            self._set_child_focus(buttons[target])
                            return True
                        return True

        return super().eventFilter(obj, event)


__all__ = ["CustomTitleBar", "TitleAlign"]
