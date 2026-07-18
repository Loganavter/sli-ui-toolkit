from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from PySide6.QtCore import QEvent, QPoint, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent, QPainter, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from sli_ui_toolkit.ui.windows.rounded_body import paint_top_rounded_background

from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.text_labels import (
    Label,
    LabelVariantSpec,
    register_label_variant,
)
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.windows.window_controls import WindowControlsHandle

TitleAlign = Literal["center", "leading"]
TitleBarZone = Literal["leading", "trailing", "center"]


def resolve_titlebar_color(token: str, *, fallback: str = "Window") -> QColor:
    """Resolve a title-bar palette token with a safe fallback chain."""
    tm = ThemeManager.get_instance()
    color = tm.try_get_color(token)
    if color is not None and color.isValid():
        return color
    color = tm.try_get_color(fallback)
    if color is not None and color.isValid():
        return color
    return tm.get_color("WindowText" if token.endswith(".text") else "Window")


def _ensure_titlebar_label_variant() -> None:
    # Always (re)register: get_label_variant() silently falls back to "body"
    # when a name is missing, so a KeyError guard never ran and the title
    # stayed at body size (12px) regardless of this spec.
    register_label_variant(
        LabelVariantSpec(
            "titlebar",
            pixel_size=16,
            color_token="titlebar.text",
        )
    )


def _zone_host(parent: QWidget) -> QWidget:
    host = QWidget(parent)
    host.setObjectName("TitleBarZoneHost")
    host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    host.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    host.setAutoFillBackground(False)
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return host


class CustomTitleBar(QWidget):
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
    ):
        super().__init__(parent)
        _ensure_titlebar_label_variant()
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._maximize_icon = maximize_icon
        self._restore_icon = restore_icon
        self._app_icon_label: QLabel | None = None
        self._target_window: QWidget | None = None
        self._drag_start_global: QPoint | None = None
        self._drag_enabled = True
        self._drag_exclusions: set[int] = set()
        self._title_align: TitleAlign = "center"
        self._title_visible = True
        self._balance_resync_scheduled = False
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

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

        self._buttons_container = QWidget(self)
        self._buttons_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._buttons_container.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self._buttons_container.setAttribute(
            Qt.WidgetAttribute.WA_NoSystemBackground, True
        )
        self._buttons_container.setAutoFillBackground(False)
        buttons_layout = QHBoxLayout(self._buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(0)

        if show_minimize:
            self._min_btn = self._mk_button(minimize_icon, "min")
            self._min_btn.clicked.connect(self.minimize_requested.emit)
            buttons_layout.addWidget(self._min_btn)
            self.register_drag_exclusion(self._min_btn)
        else:
            self._min_btn = None

        if show_maximize:
            self._max_btn = self._mk_button(maximize_icon, "max")
            self._max_btn.clicked.connect(self.maximize_toggle_requested.emit)
            buttons_layout.addWidget(self._max_btn)
            self.register_drag_exclusion(self._max_btn)
        else:
            self._max_btn = None

        if show_close:
            self._close_btn = self._mk_button(close_icon, "close")
            self._close_btn.clicked.connect(self.close_requested.emit)
            buttons_layout.addWidget(self._close_btn)
            self.register_drag_exclusion(self._close_btn)
        else:
            self._close_btn = None

        control_count = sum(
            1 for btn in (self._min_btn, self._max_btn, self._close_btn) if btn is not None
        )
        if control_count:
            cluster_w = control_count * self.BUTTON_WIDTH
            self._buttons_container.setFixedWidth(cluster_w)
            self._buttons_container.setMinimumWidth(cluster_w)
            self._buttons_container.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )

        self._layout.addWidget(self._buttons_container)
        self._controls_handle = WindowControlsHandle(
            min_btn=self._min_btn,
            max_btn=self._max_btn,
            close_btn=self._close_btn,
            container=self._buttons_container,
        )
        self._apply_title_alignment()
        self._sync_balance_spacer()

        if icon is not None:
            self.set_icon(icon)

    def set_icon(self, icon: QIcon | None) -> None:
        """Show a leading app icon (draggable with the title bar chrome)."""
        if icon is None or icon.isNull():
            if self._app_icon_label is not None:
                self._app_icon_label.hide()
                self._sync_balance_spacer()
                self._schedule_balance_resync()
            return

        if self._app_icon_label is None:
            label = QLabel(self._leading_host)
            label.setObjectName("CustomTitleBarAppIcon")
            label.setFixedSize(self.APP_ICON_SLOT, self.HEIGHT)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Keep drag on the icon slot — it is chrome, not a control.
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._app_icon_label = label
            self._zone_layout("leading").insertWidget(0, label)

        pixmap = icon.pixmap(self.ICON_SIZE, self.ICON_SIZE)
        self._app_icon_label.setPixmap(pixmap)
        self._app_icon_label.show()
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def _stretch_indices(self) -> tuple[int, int]:
        # [leading][left_balance][stretch][center][stretch][trailing][right_balance][buttons]
        return (2, 4)

    def _apply_title_alignment(self) -> None:
        before_idx, after_idx = self._stretch_indices()
        if self._title_align == "center":
            self._layout.setStretch(before_idx, 1)
            self._layout.setStretch(after_idx, 1)
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self._layout.setStretch(before_idx, 0)
            self._layout.setStretch(after_idx, 1)
            self._title_label.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

    def _zone_layout(self, zone: TitleBarZone) -> QHBoxLayout:
        host = {
            "leading": self._leading_host,
            "trailing": self._trailing_host,
            "center": self._center_host,
        }[zone]
        layout = host.layout()
        assert layout is not None
        return layout

    def _clear_zone(self, zone: TitleBarZone) -> None:
        layout = self._zone_layout(zone)
        keep = {self._title_label}
        if zone == "leading" and self._app_icon_label is not None:
            keep.add(self._app_icon_label)
        for index in reversed(range(layout.count())):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or widget in keep:
                continue
            layout.takeAt(index)
            # hide + detach immediately: deleteLater alone leaves the old
            # TitleBarMenuStrip painting until the next event-loop turn
            # (ghost «Справка» between File and Help on first show).
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()

    def _set_zone_widget(self, zone: TitleBarZone, widget: QWidget | None) -> None:
        if zone == "center" and widget is None:
            self._clear_zone("center")
            layout = self._zone_layout("center")
            if layout.indexOf(self._title_label) < 0:
                layout.addWidget(self._title_label)
            self._title_label.setVisible(self._title_visible)
            return

        self._clear_zone(zone)
        if widget is None:
            if zone == "center":
                layout = self._zone_layout("center")
                if layout.indexOf(self._title_label) < 0:
                    layout.addWidget(self._title_label)
                self._title_label.setVisible(self._title_visible)
            return
        layout = self._zone_layout(zone)
        layout.addWidget(widget)
        if zone != "center":
            self.register_drag_exclusion(widget)

    def set_leading(self, widget: QWidget | None) -> None:
        self._set_zone_widget("leading", widget)
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def set_trailing(self, widget: QWidget | None) -> None:
        self._set_zone_widget("trailing", widget)
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def set_center(self, widget: QWidget | None) -> None:
        self._set_zone_widget("center", widget)

    def set_title(self, title: str, *, align: TitleAlign | None = None) -> None:
        self._title_label.setText(title)
        if align is not None:
            self.set_title_alignment(align)
        else:
            self._sync_balance_spacer()
            self._schedule_balance_resync()

    def set_title_alignment(self, align: TitleAlign) -> None:
        self._title_align = align
        self._apply_title_alignment()
        self._sync_balance_spacer()
        self._schedule_balance_resync()

    def set_title_visible(self, visible: bool) -> None:
        self._title_visible = visible
        self._title_label.setVisible(visible)

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag_enabled = enabled

    def register_drag_exclusion(self, widget: QWidget) -> None:
        self._drag_exclusions.add(id(widget))

    def window_controls(self) -> WindowControlsHandle:
        return self._controls_handle

    def add_widget(self, widget: QWidget, *, zone: TitleBarZone = "leading") -> QWidget:
        layout = self._zone_layout(zone)
        layout.addWidget(widget)
        self.register_drag_exclusion(widget)
        self._sync_balance_spacer()
        self._schedule_balance_resync()
        return widget

    def add_button(self, button: Button, *, zone: TitleBarZone = "leading") -> Button:
        self.add_widget(button, zone=zone)
        return button

    def add_buttons(
        self, buttons: Sequence[Button], *, zone: TitleBarZone = "leading"
    ) -> QWidget:
        row = _zone_host(self)
        row_layout = row.layout()
        assert row_layout is not None
        for button in buttons:
            row_layout.addWidget(button)
            self.register_drag_exclusion(button)
        layout = self._zone_layout(zone)
        if layout.count() == 0:
            layout.addWidget(row)
            self.register_drag_exclusion(row)
        else:
            for button in buttons:
                layout.addWidget(button)
            row.deleteLater()
        self._sync_balance_spacer()
        self._schedule_balance_resync()
        return row

    def set_menu_strip(self, strip: QWidget) -> None:
        self.set_leading(strip)

    def _chrome_side_widths(self) -> tuple[int, int]:
        leading = self._zone_content_width(self._leading_host)
        trailing = self._zone_content_width(self._trailing_host)
        buttons = self._controls_handle.size_hint_width()
        return leading, trailing + buttons

    @staticmethod
    def _zone_content_width(host: QWidget) -> int:
        """Width of zone chrome, even before the host sizeHint catches up."""
        hint = max(host.sizeHint().width(), host.minimumSizeHint().width())
        if hint > 0:
            return hint
        layout = host.layout()
        if layout is None:
            return max(host.width(), 0)
        total = layout.contentsMargins().left() + layout.contentsMargins().right()
        visible = 0
        for index in range(layout.count()):
            item = layout.itemAt(index)
            child = item.widget() if item is not None else None
            if child is None or child.isHidden():
                continue
            visible += 1
            total += max(
                child.sizeHint().width(),
                child.minimumSizeHint().width(),
                child.width(),
            )
        if visible > 1:
            total += max(0, layout.spacing()) * (visible - 1)
        return max(total, host.width(), 0)

    def _schedule_balance_resync(self) -> None:
        """Re-measure chrome after the next layout pass.

        ``set_menu_strip`` / language rebuilds often sync while the new leading
        strip still reports ``sizeHint().width() == 0``. A left pad matching
        the window buttons then sticks after the strip lays out, shoving the
        centered title off-center.

        While the bar is still hidden, run sync immediately — a deferred pass
        after the first show paint leaves a ghost of translucent menu labels.
        """
        if self._title_align != "center":
            return
        if not self.isVisible():
            self._sync_balance_spacer()
            return
        if self._balance_resync_scheduled:
            return
        self._balance_resync_scheduled = True

        def _run() -> None:
            self._balance_resync_scheduled = False
            try:
                import shiboken6

                if not shiboken6.isValid(self):
                    return
            except Exception:
                pass
            self._sync_balance_spacer()
            # Translucent ghost triggers do not erase themselves on move.
            self.repaint()

        QTimer.singleShot(0, _run)

    def _sync_balance_spacer(self) -> None:
        if self._title_align != "center":
            self._left_balance.setFixedWidth(0)
            self._balance_spacer.setFixedWidth(0)
            return
        left, right = self._chrome_side_widths()
        if left < right:
            self._left_balance.setFixedWidth(right - left)
            self._balance_spacer.setFixedWidth(0)
        else:
            self._left_balance.setFixedWidth(0)
            self._balance_spacer.setFixedWidth(left - right)
        # setFixedWidth alone does not always reflow an already-laid-out
        # title bar (deferred language resync); force the stretch pair to
        # recompute so the title stays visually centered.
        self._layout.invalidate()
        self._layout.activate()
        self.updateGeometry()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_balance_spacer()
        self._apply_corner_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_corner_mask()

    def _apply_corner_mask(self) -> None:
        from sli_ui_toolkit.ui.windows.rounded_body import (
            apply_top_trailing_rounded_mask,
        )

        # Title bar paints its own AA rounded fill — a full-bar setMask would
        # stair-case that edge. Only clip the control cluster so the close
        # button cannot poke through the top-right arc.
        self.clearMask()
        window = self._target_window if self._target_window is not None else self.window()
        squared = bool(
            window is not None
            and (window.isMaximized() or window.isFullScreen())
        )
        buttons = getattr(self, "_buttons_container", None)
        if buttons is not None:
            apply_top_trailing_rounded_mask(
                buttons,
                radius=float(self.CORNER_RADIUS),
                squared=squared,
            )

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            color = resolve_titlebar_color("titlebar.background", fallback="Window")
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
        super().paintEvent(event)

    def _on_theme_changed(self, *_args) -> None:
        self.update()
        self._title_label.update()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
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

    def attach_window(self, window: QWidget) -> None:
        self._target_window = window
        self.minimize_requested.connect(self._on_minimize)
        self.maximize_toggle_requested.connect(self._on_toggle_maximize)
        self.close_requested.connect(window.close)
        window.installEventFilter(self)
        self._refresh_maximize_icon()
        self._refresh_close_button_shape()

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
            self._max_btn.setIcon(icon)

    def _refresh_close_button_shape(self) -> None:
        if self._close_btn is None or self._target_window is None:
            return
        w = self._target_window
        squared = w.isMaximized() or w.isFullScreen()
        radii = (0, 0, 0, 0) if squared else (0, self.CORNER_RADIUS, 0, 0)
        if self._close_btn._corner_radii_px != radii:
            self._close_btn._corner_radii_px = radii
            self._close_btn.update()

    def _hide_active_flyouts(self) -> None:
        try:
            from sli_ui_toolkit.managers import FlyoutManager

            mgr = FlyoutManager.get_instance()
            # Opening a tall in-window context menu (e.g. File with Open/Save
            # Project) can trigger a host Resize/Move while the menu is being
            # attached. Closing *all* flyouts here makes the first File/Help
            # click look like a no-op; keep context menus open.
            for flyout in list(getattr(mgr, "_registered_flyouts", ())):
                try:
                    if not flyout.isVisible():
                        continue
                    if getattr(flyout, "flyout_group", None) == "context_menu":
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
            self._refresh_maximize_icon()
            self._refresh_close_button_shape()
            self._apply_corner_mask()
            if event.type() in (event.Type.Resize, event.Type.Move):
                self._hide_active_flyouts()
        return super().eventFilter(obj, event)

    def _is_draggable_at(self, pos: QPoint) -> bool:
        if not self._drag_enabled or self._target_window is None:
            return False
        child = self.childAt(pos)
        if child is None:
            return True
        widget = child
        while widget is not None and widget is not self:
            if id(widget) in self._drag_exclusions:
                return False
            if isinstance(widget, Button) and widget.isEnabled() and widget.isVisible():
                return False
            if (
                widget is not self._balance_spacer
                and widget is not self._left_balance
                and not widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                and widget.isEnabled()
                and widget.isVisible()
                and widget.parentWidget() is not self._buttons_container
                and widget is not self._title_label
            ):
                if widget.objectName() != "TitleBarZoneHost":
                    return False
            widget = widget.parentWidget()
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._is_draggable_at(event.position().toPoint())
        ):
            self._drag_start_global = event.globalPosition().toPoint()
        else:
            self._drag_start_global = None
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
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._target_window is not None
            and self._is_draggable_at(event.position().toPoint())
        ):
            self._on_toggle_maximize()
        super().mouseDoubleClickEvent(event)
