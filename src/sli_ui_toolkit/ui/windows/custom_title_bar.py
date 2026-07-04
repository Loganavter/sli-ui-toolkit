from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from sli_ui_toolkit.ui.widgets.buttons import Button


def _system_titlebar_font():
    font = QApplication.font()
    font.setPointSizeF(font.pointSizeF() * 1.0)
    return font


class CustomTitleBar(QWidget):
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()

    HEIGHT = 36
    BUTTON_WIDTH = 46
    ICON_SIZE = 16

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
    ):
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._maximize_icon = maximize_icon
        self._restore_icon = restore_icon
        self._target_window: QWidget | None = None
        self._drag_start_global: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._left_spacer = QWidget(self)
        self._left_spacer.setFixedWidth(0)
        self._left_spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._left_spacer)

        layout.addStretch(1)
        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("CustomTitleBarTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setFont(_system_titlebar_font())
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._title_label)
        layout.addStretch(1)

        self._buttons_container = QWidget(self)
        self._buttons_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        buttons_layout = QHBoxLayout(self._buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(0)

        if show_minimize:
            self._min_btn = self._mk_button(minimize_icon, "min")
            self._min_btn.clicked.connect(self.minimize_requested.emit)
            buttons_layout.addWidget(self._min_btn)
        else:
            self._min_btn = None

        if show_maximize:
            self._max_btn = self._mk_button(maximize_icon, "max")
            self._max_btn.clicked.connect(self.maximize_toggle_requested.emit)
            buttons_layout.addWidget(self._max_btn)
        else:
            self._max_btn = None

        if show_close:
            self._close_btn = self._mk_button(close_icon, "close")
            self._close_btn.clicked.connect(self.close_requested.emit)
            buttons_layout.addWidget(self._close_btn)
        else:
            self._close_btn = None

        layout.addWidget(self._buttons_container)
        self._sync_left_spacer()

    def _sync_left_spacer(self) -> None:
        hint = self._buttons_container.sizeHint().width()
        self._left_spacer.setFixedWidth(max(hint, 0))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_left_spacer()

    CORNER_RADIUS = 10

    def _mk_button(self, icon: Any, role: str) -> Button:
        corner_radii = (0, self.CORNER_RADIUS, 0, 0) if role == "close" else (0, 0, 0, 0)
        btn = Button(
            icon if icon is not None else QIcon(),
            variant="ghost",
            size=(self.BUTTON_WIDTH, self.HEIGHT),
            icon_size=self.ICON_SIZE,
            corner_radii=corner_radii,
            parent=self,
        )
        btn.setObjectName("CustomTitleBarButton")
        btn.setProperty("titlebarRole", role)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        return btn

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def attach_window(self, window: QWidget) -> None:
        self._target_window = window
        self.minimize_requested.connect(self._on_minimize)
        self.maximize_toggle_requested.connect(self._on_toggle_maximize)
        self.close_requested.connect(window.close)
        window.installEventFilter(self)
        self._refresh_maximize_icon()

    def _on_minimize(self) -> None:
        if self._target_window is not None:
            self._target_window.showMinimized()

    def _on_toggle_maximize(self) -> None:
        w = self._target_window
        if w is None:
            return
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def _refresh_maximize_icon(self) -> None:
        if self._max_btn is None or self._target_window is None:
            return
        is_max = self._target_window.isMaximized()
        icon = self._restore_icon if is_max else self._maximize_icon
        if icon is not None:
            self._max_btn._icon_unchecked = icon
            self._max_btn._icon_checked = icon
            self._max_btn.update()

    def eventFilter(self, obj, event):
        if obj is self._target_window and event.type() in (
            event.Type.WindowStateChange,
            event.Type.Resize,
        ):
            self._refresh_maximize_icon()
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._target_window is not None:
            self._drag_start_global = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        w = self._target_window
        if (
            self._drag_start_global is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and w is not None
        ):
            handle = w.windowHandle()
            if handle is not None:
                try:
                    handle.startSystemMove()
                    self._drag_start_global = None
                    return
                except Exception:
                    pass

            current = event.globalPosition().toPoint()
            delta = current - self._drag_start_global
            self._drag_start_global = current
            if w.isMaximized():
                w.showNormal()
            w.move(w.pos() + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_global = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._target_window is not None:
            self._on_toggle_maximize()
        super().mouseDoubleClickEvent(event)
