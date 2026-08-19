"""ContextMenu shell widget (BaseFlyout subclass)."""

from __future__ import annotations

import logging
import math
from typing import Callable, Iterable, Literal, Sequence

logger = logging.getLogger(__name__)

import shiboken6 as sip

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QEventLoop,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.config import get_context_menu_surface, get_flyout_timings
from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.widgets.buttons.feedback import get_ripple_duration_ms
from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.ui.popup_surface import (
    bind_popup_transient_parent,
    clamp_popup_rect,
    configure_popup_widget,
    place_popup_at_global,
    popup_contains_global,
    screen_available_rect,
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout import (
    AnimationAxis,
    BaseFlyout,
    aligned_flyout_rect,
    resolve_flyout_animation,
    slide_start_delta,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSeparator,
    ContextMenuSection,
    _SectionTitle,
    _entry_visible,
    _trim_flat_separators,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import (
    ContextMenuRow,
    SectionTitleRow,
    SeparatorRow,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu import submenu as submenu_ops


class ContextMenu(BaseFlyout):
    """Theme-aware context menu built from declarative entries.

    Default surface is in-window (same overlay as other flyouts). Pass
    ``surface="popup"`` for right-click menus that must stack above
    ``UnifiedFlyout`` as a frameless Qt popup. Button-anchored menus should
    keep the default and use ``show_aligned``.
    """

    actionTriggered = Signal(str, object)
    aboutToHide = Signal()

    CONTENT_RADIUS = 6
    # Identity tag for host ``GroupShowPolicy`` rules — no behavior by itself.
    flyout_group = "context_menu"

    # Class-level set of currently visible in-window ContextMenus.
    # The host app checks this on Escape to close the topmost menu before
    # its own global keyboard handler consumes the event.
    _visible_menus: set["ContextMenu"] = set()

    @classmethod
    def close_visible(cls) -> bool:
        """Close the most-recently-shown visible in-window menu.

        Returns True if a menu was closed (caller should accept the event).
        """
        for menu in reversed(list(cls._visible_menus)):
            if menu.isVisible():
                menu.hide()
                return True
        return False

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        entries: Iterable[ContextMenuEntry] | None = None,
        on_triggered: Callable[[str, object], None] | None = None,
        _is_submenu: bool = False,
        surface: Literal["in_window", "popup"] | None = None,
    ):
        # These must exist before BaseFlyout.__init__ runs: attaching the
        # widget to its overlay layer can call hide() on self as a side
        # effect, and hide()/close_submenu() read these attributes.
        self._open_submenu: ContextMenu | None = None
        self._submenu_owner_row: ContextMenuRow | None = None
        self._owner_menu: ContextMenu | None = None
        self._is_submenu = _is_submenu
        self._surface = surface if surface is not None else get_context_menu_surface()
        self._logical_parent = parent
        # Cursor-positioned popup fade-out state (popup_at). Popups are
        # top-levels, so they don't route hide() through BaseFlyout's in-window
        # fade path; this tracks the deferred fade-out so aboutToHide /
        # deleteLater fire only after the widget is actually hidden.
        self._popup_fade_anim: QVariantAnimation | None = None
        self._popup_fade_in_progress = False
        # Popup menus must never attach to the host OverlayLayer: attach +
        # setParent(None) reorders overlay children and can shove open flyouts
        # off their geometry. Keep the QWidget parent so Wayland gets a
        # transient parent (parentless popups are compositor-centered).
        super().__init__(parent, attach_overlay=not (self._surface == "popup"))
        self._on_triggered = on_triggered
        self._rows: list[ContextMenuRow] = []
        # Menus must not steal window activation (Wayland / QRhi).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if self.is_popup_surface():
            configure_popup_widget(self)
            bind_popup_transient_parent(self, parent)
        elif _is_submenu:
            self.flyout_manager.unregister_flyout(self)
        # Ensure destroyed widgets are removed from the class-level registry
        # so that close_visible() never operates on a dangling pointer.
        self.destroyed.connect(lambda: self._visible_menus.discard(self))
        if entries is not None:
            self.set_entries(entries)

    def is_popup_surface(self) -> bool:
        return self._surface == "popup"

    def row_for_action(self, action_id: str) -> QWidget | None:
        """Return the live row widget for ``action_id``, if present."""
        if not action_id:
            return None
        for row in self._rows:
            if getattr(row, "action_id", None) == action_id:
                return row
        return None

    # -------- entries --------

    def set_entries(self, entries: Iterable[ContextMenuEntry]) -> None:
        submenu_ops.close_submenu(self)
        # Take widgets out of the layout once, then destroy. Calling
        # deleteLater on both ``_rows`` and layout items double-schedules the
        # same ContextMenuRow and races with immediate recreation under
        # Python 3.14 / Shiboken (SystemError in Button/QWidget.__init__).
        pending: list[QWidget] = []
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                pending.append(widget)
        self._rows.clear()
        for widget in pending:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        from PySide6.QtCore import QCoreApplication, QEvent

        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        flat = _trim_flat_separators(self._flatten(tuple(entries)))
        # No check-glyph gutter: current/checkable rows use background highlight only.
        check_gutter = scaled_px(12)
        for item in flat:
            self.content_layout.addWidget(self._build_row(item, check_gutter))
        self._assign_row_positions()
        self._relayout_widths()

    def _assign_row_positions(self) -> None:
        rows = list(self._rows)
        count = len(rows)
        for index, row in enumerate(rows):
            if count == 1:
                row.set_position("only")
            elif index == 0:
                row.set_position("first")
            elif index == count - 1:
                row.set_position("last")
            else:
                row.set_position("middle")

    def _relayout_widths(self) -> None:
        """Size the menu to the widest row using the current font metrics."""
        from sli_ui_toolkit.ui.managers.ui_font import ui_font

        app_font = ui_font()
        max_w = 0

        for index in range(self.content_layout.count()):
            layout_item = self.content_layout.itemAt(index)
            widget = layout_item.widget() if layout_item is not None else None
            if widget is None:
                continue
            widget.setMinimumWidth(0)
            if isinstance(widget, SectionTitleRow):
                widget.setFont(ui_font(pixel_size=11, bold=True))
            else:
                widget.setFont(app_font)

        for row in self._rows:
            row.refresh_metrics()
            max_w = max(max_w, row.sizeHint().width())

        for index in range(self.content_layout.count()):
            layout_item = self.content_layout.itemAt(index)
            widget = layout_item.widget() if layout_item is not None else None
            if widget is None:
                continue
            hint = widget.sizeHint()
            if hint.isValid():
                max_w = max(max_w, hint.width())

        if max_w <= 0:
            self.adjustSize()
            return

        for index in range(self.content_layout.count()):
            layout_item = self.content_layout.itemAt(index)
            widget = layout_item.widget() if layout_item is not None else None
            if widget is not None:
                widget.setMinimumWidth(max_w)

        self.setMinimumSize(0, 0)
        container_layout = self.container.layout()
        if container_layout is not None:
            container_layout.invalidate()
            container_layout.activate()
            self.container.updateGeometry()
        self.adjustSize()

    def _flatten(self, entries: Sequence[ContextMenuEntry]) -> list:
        flat: list = []
        for entry in entries:
            if isinstance(entry, ContextMenuSeparator):
                if entry.visible:
                    flat.append(entry)
            elif isinstance(entry, ContextMenuSection):
                visible_entries = tuple(e for e in entry.entries if _entry_visible(e))
                if not visible_entries:
                    continue
                if flat and not isinstance(flat[-1], ContextMenuSeparator):
                    flat.append(ContextMenuSeparator())
                if entry.title:
                    flat.append(_SectionTitle(entry.title))
                flat.extend(self._flatten(visible_entries))
                if not isinstance(flat[-1], ContextMenuSeparator):
                    flat.append(ContextMenuSeparator())
            elif isinstance(entry, ContextMenuAction):
                if entry.visible:
                    flat.append(entry)
        return flat

    def _build_row(self, item, check_gutter: int) -> QWidget:
        if isinstance(item, ContextMenuSeparator):
            return SeparatorRow(self.container)
        if isinstance(item, _SectionTitle):
            return SectionTitleRow(item.text, self.container)
        row = ContextMenuRow(item, check_gutter=check_gutter, parent=self.container)
        row.clicked.connect(lambda checked=False, r=row, spec=item: self._on_row_clicked(r, spec))
        row.installEventFilter(self)
        self._rows.append(row)
        return row

    def _on_row_clicked(self, row: ContextMenuRow, spec: ContextMenuAction) -> None:
        if spec.children:
            submenu_ops.toggle_submenu(self, row, spec)
            return
        if spec.defer_trigger:
            # The menu (and this row, with it) is about to be hidden --
            # normally that happens synchronously below, right as the row's
            # own click ripple starts, so it never gets to play at all.
            # Wait one ripple duration with the menu still open/visible
            # before hiding + firing, for an action whose handler opens a
            # modal dialog (see ContextMenuAction.defer_trigger).
            action_id, data = spec.action_id, spec.data
            QTimer.singleShot(
                get_ripple_duration_ms(),
                lambda: self._finish_row_click(action_id, data)
                if sip.isValid(self)  # type: ignore[attr-defined]
                else None,
            )
            return
        self._finish_row_click(spec.action_id, spec.data)

    def _finish_row_click(self, action_id: str, data: object) -> None:
        submenu_ops.close_submenu(self)
        submenu_ops.root_menu(self).hide()
        self.actionTriggered.emit(action_id, data)
        if self._on_triggered is not None:
            self._on_triggered(action_id, data)

    def _root_menu(self) -> ContextMenu:
        return submenu_ops.root_menu(self)

    def _toggle_submenu(self, row: ContextMenuRow, spec: ContextMenuAction) -> None:
        submenu_ops.toggle_submenu(self, row, spec)

    def _position_submenu(self, submenu: ContextMenu, row: ContextMenuRow) -> None:
        submenu_ops.position_submenu(self, submenu, row)

    def _close_submenu(self) -> None:
        submenu_ops.close_submenu(self)

    # -------- show/hide plumbing --------

    def _ensure_overlay_parent(self, anchor_widget: QWidget):
        if self.is_popup_surface():
            return
        super()._ensure_overlay_parent(anchor_widget)

    def show(self):
        if self._is_submenu or self.is_popup_surface():
            QWidget.show(self)
            return
        super().show()

    def restore_focus_on_hide(self) -> bool:
        return False

    def eventFilter(self, watched, event):
        # Rows are child Buttons — they receive presses before the menu widget.
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.RightButton
        ):
            submenu_ops.root_menu(self).hide()
            return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        # Second right-click lands on the menu (same cursor spot as open).
        if event.button() == Qt.MouseButton.RightButton:
            self.hide()
            event.accept()
            return
        # Left press on the translucent shadow halo (not the opaque panel)
        # must dismiss — those pixels often sit under the open cursor.
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                pos = event.position().toPoint()
            except AttributeError:
                pos = event.pos()
            if not self.container.geometry().contains(pos):
                self.hide()
                event.accept()
                return
        super().mousePressEvent(event)

    def hide(self):
        submenu_ops.close_submenu(self)
        if not self.is_popup_surface():
            self._visible_menus.discard(self)
        if self._should_popup_fade_out():
            # Popup surface shown with a fade-bearing animation: fade out
            # first, then really hide + emit aboutToHide + deleteLater once
            # the widget is off screen (see _on_popup_fade_out_finished).
            self._start_popup_fade_out()
            return
        ephemeral = self._is_submenu or self.is_popup_surface()
        if ephemeral:
            QWidget.hide(self)
        else:
            super().hide()
        self.aboutToHide.emit()
        if self.is_popup_surface() and not self._is_submenu:
            self.deleteLater()

    def contains_global(self, global_pos) -> bool:
        if self.is_popup_surface():
            if popup_contains_global(
                self, global_pos, opaque_panel=self.container
            ):
                return True
            if self._open_submenu is not None and self._open_submenu.isVisible():
                return self._open_submenu.contains_global(global_pos)
            return False
        if not self.isVisible():
            return False
        # Count only the opaque panel. The shadow margin around ``container``
        # must not trap the open-cursor position for outside-close hit tests.
        try:
            top_left = self.container.mapToGlobal(QPoint(0, 0))
            if QRect(top_left, self.container.size()).contains(global_pos):
                return True
        except RuntimeError:
            return False
        if self._open_submenu is not None and self._open_submenu.isVisible():
            return self._open_submenu.contains_global(global_pos)
        return False

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            logger.debug("[ctx-menu] Escape pressed, submenu=%s", self._open_submenu is not None)
            if self._open_submenu is not None:
                submenu_ops.close_submenu(self)
                event.accept()
                return
            self.hide()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = QApplication.focusWidget()
            logger.debug("[ctx-menu] Enter pressed, focused=%s rows=%d", type(focused).__name__ if focused else None, len(self._rows))
            if focused is not None:
                for row in self._rows:
                    if row is focused or row.isAncestorOf(focused):
                        spec = getattr(row, "_spec", None)
                        if spec is not None:
                            logger.debug("[ctx-menu] Enter -> activate row action_id=%s", spec.action_id)
                            self._on_row_clicked(row, spec)
                            event.accept()
                            return
            event.accept()
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            logger.debug("[ctx-menu] %s pressed", "Down" if key == Qt.Key.Key_Down else "Up")
            self._navigate_rows(1 if key == Qt.Key.Key_Down else -1)
            event.accept()
            return
        super().keyPressEvent(event)

    def _navigate_rows(self, step: int) -> None:
        """Move focus between visible rows."""
        if not self._rows:
            return
        focused = QApplication.focusWidget()
        idx = next((i for i, r in enumerate(self._rows) if r is focused), None)
        if idx is None:
            target = 0 if step > 0 else len(self._rows) - 1
        else:
            target = (idx + step) % len(self._rows)
        self._rows[target].setFocus(Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, obj, event):  # noqa: N802
        # Rows are child Buttons — they receive presses before the menu widget.
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.RightButton
        ):
            submenu_ops.root_menu(self).hide()
            return True
        return super().eventFilter(obj, event)

    # -------- public show API --------

    def show_aligned(
        self,
        anchor_widget,
        anchor_point="bottom-center",
        flyout_point="top-center",
        **kwargs,
    ):
        self._relayout_widths()
        if self.is_popup_surface():
            self._popup_show_aligned(
                anchor_widget,
                anchor_point=anchor_point,
                flyout_point=flyout_point,
                **kwargs,
            )
            return
        super().show_aligned(
            anchor_widget,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            **kwargs,
        )
        if not self.is_popup_surface():
            self._visible_menus.add(self)

    def _popup_show_aligned(
        self,
        anchor_widget: QWidget,
        anchor_point: str = "bottom-center",
        flyout_point: str = "top-center",
        *,
        position: str | None = None,
        offset: int = 5,
        animation: str | None = None,
        animation_duration_ms: int | None = None,
        animation_distance: int | None = None,
        animation_axis: AnimationAxis = "auto",
        easing: QEasingCurve.Type = QEasingCurve.Type.OutQuad,
    ) -> None:
        self._anchor_widget = anchor_widget
        container_layout = self.container.layout()
        if container_layout is not None:
            container_layout.invalidate()
            container_layout.activate()
            self.container.updateGeometry()
        self.adjustSize()
        flyout_size = self.size()

        anchor_rect = surface_anchor_rect(self, anchor_widget, None)
        if position is not None:
            final_rect = self._overlay_rect_relative_to_anchor(
                anchor_widget,
                flyout_size,
                position=position,
                offset=offset - self.SHADOW_RADIUS,
            )
            flyout_center = final_rect.center()
        else:
            available = screen_available_rect(self, margin=0)
            final_rect = aligned_flyout_rect(
                anchor_rect,
                flyout_size,
                anchor_point=anchor_point,
                flyout_point=flyout_point,
                offset=offset,
                shadow_radius=self.SHADOW_RADIUS,
                available=available,
            )
            # Popup coords are global; aligned_flyout_rect already clamped.
            flyout_center = final_rect.center()

        dir_x = flyout_center.x() - anchor_rect.center().x()
        dir_y = flyout_center.y() - anchor_rect.center().y()
        length = math.hypot(dir_x, dir_y)
        if length > 0:
            ux, uy = dir_x / length, dir_y / length
        else:
            ux = uy = 0.0

        mode = animation if animation is not None else (
            get_flyout_timings().default_flyout_animation or "none"
        )
        mode = mode if mode else "none"
        if mode == "none":
            self.setGeometry(final_rect)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.show()
            self.raise_()
            return

        timings = get_flyout_timings()
        duration = (
            animation_duration_ms
            if animation_duration_ms is not None
            else timings.flyout_animation_duration_ms
        )
        distance = (
            animation_distance
            if animation_distance is not None
            else timings.dropdown_drop_offset_px
        )
        if self._show_animation is not None:
            self._show_animation.stop()
            self._show_animation.deleteLater()
            self._show_animation = None

        slide_dx, slide_dy = slide_start_delta(
            final_rect,
            anchor_rect,
            distance=distance,
            animation_axis=animation_axis,
            shadow_radius=self.SHADOW_RADIUS,
            ux=ux,
            uy=uy,
            length=length,
        )
        start_pos = QPoint(
            final_rect.x() + slide_dx,
            final_rect.y() + slide_dy,
        )
        self.setGeometry(QRect(start_pos, final_rect.size()))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(int(duration))
        anim.setStartValue(start_pos)
        anim.setEndValue(QPoint(final_rect.x(), final_rect.y()))
        anim.setEasingCurve(easing)
        anim.finished.connect(self._on_show_animation_finished)
        self._show_animation = anim
        anim.start()

    def popup_at(self, global_pos: QPoint, *, animation: str | None = None) -> None:
        submenu_ops.close_submenu(self)
        self._relayout_widths()
        container_layout = self.container.layout()
        if container_layout is not None:
            container_layout.invalidate()
            container_layout.activate()
            self.container.updateGeometry()
        self.adjustSize()

        # Cursor-positioned menus resolve the same animation mode as the rest
        # (explicit -> global default -> historical "slide"); a fade-bearing
        # mode fades the menu in at the cursor and fades it out on hide.
        mode = resolve_flyout_animation(animation)
        self._fade.fade_out_enabled = "fade" in mode
        want_fade = "fade" in mode

        # Keep the open cursor outside the widget (incl. shadow) so the same
        # spot can dismiss on the next press. Opaque content still sits near
        # the cursor via the shadow inset.
        origin = global_pos + QPoint(1, 1)
        if self.is_popup_surface():
            bind_popup_transient_parent(self, self._logical_parent)
            place_popup_at_global(self, origin, margin=4)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            # Show FIRST, snapshot second: grab() of a top-level popup window
            # that was never shown can miss content (corners, shadow — the
            # "top-left corner pops in opaque" artifact) because the native
            # surface doesn't exist yet. show() + re-place stay synchronous
            # (no event-loop pass), so no frame ever paints at full opacity
            # before the fade takes over.
            # Show FIRST, snapshot second: grab() of a top-level popup window
            # that was never shown can miss content (corners, shadow — the
            # "top-left corner pops in opaque" artifact) because the native
            # surface doesn't exist yet. show() + re-place stay synchronous
            # (no event-loop pass), so no frame ever paints at full opacity
            # before the fade takes over.
            self.show()
            self.raise_()
            # Wayland may ignore pre-show geometry; re-apply once mapped.
            place_popup_at_global(self, origin, margin=4)
            if want_fade:
                self._fade.capture(self)
                self._fade.set_opacity(self, 0.0)
                self._start_popup_fade_in()
            return

        parent = self.parentWidget()
        local_pos = parent.mapFromGlobal(origin) if parent is not None else origin
        target = QRect(local_pos, self.size())
        if self.overlay_layer is not None and hasattr(self.overlay_layer, "clamp_rect"):
            try:
                target = self.overlay_layer.clamp_rect(target, margin=4)
            except TypeError:
                target = self.overlay_layer.clamp_rect(target)
        else:
            target = clamp_surface_rect(
                target,
                surface_available_rect(self, None, self.overlay_layer, margin=4),
            )
        self.setGeometry(target)

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        if want_fade:
            self._fade.capture(self)
            self._fade.set_opacity(self, 0.0)
        self.show()
        self.raise_()
        if want_fade:
            self._start_popup_fade_in()
        # Do not setFocus(): on Wayland focusing a ContextMenu can emit
        # ApplicationDeactivate, which then closes the menu and jerks QRhi
        # canvases. Escape is handled via FlyoutManager / key filters.

    def _start_popup_fade_in(self) -> None:
        if self._show_animation is not None:
            self._show_animation.stop()
            self._show_animation.deleteLater()
            self._show_animation = None
        anim = QVariantAnimation(self)
        anim.setDuration(get_flyout_timings().flyout_animation_duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.valueChanged.connect(
            lambda value: self._fade.on_fade_value_changed(self, value)
        )
        anim.finished.connect(self._on_popup_fade_in_finished)
        self._show_animation = anim
        anim.start()

    def _on_popup_fade_in_finished(self) -> None:
        if self._show_animation is not None:
            self._show_animation.deleteLater()
            self._show_animation = None
        self._fade.clear()
        self._fade.opacity = 1.0
        self.update()

    def _should_popup_fade_out(self) -> bool:
        return bool(
            self.is_popup_surface()
            and not self._is_submenu
            and self._fade.fade_out_enabled
            and self.isVisible()
            and not self._popup_fade_in_progress
        )

    def _start_popup_fade_out(self) -> None:
        self._popup_fade_in_progress = True
        self._fade.capture(self)
        anim = QVariantAnimation(self)
        anim.setDuration(get_flyout_timings().flyout_fade_out_duration_ms)
        anim.setStartValue(self._fade.opacity)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InQuad)
        anim.valueChanged.connect(
            lambda value: self._fade.on_fade_value_changed(self, value)
        )
        anim.finished.connect(self._on_popup_fade_out_finished)
        self._popup_fade_anim = anim
        anim.start()

    def _on_popup_fade_out_finished(self) -> None:
        if self._popup_fade_anim is not None:
            self._popup_fade_anim.deleteLater()
            self._popup_fade_anim = None
        self._popup_fade_in_progress = False
        self._fade.clear()
        self._fade.opacity = 1.0
        QWidget.hide(self)
        self.aboutToHide.emit()
        if self.is_popup_surface() and not self._is_submenu:
            self.deleteLater()

    def exec_at(self, global_pos: QPoint) -> str | None:
        result: dict[str, str | None] = {"id": None}
        loop = QEventLoop()

        def _on_triggered(action_id: str, _data: object) -> None:
            result["id"] = action_id

        def _on_about_to_hide() -> None:
            loop.quit()

        self.actionTriggered.connect(_on_triggered)
        self.aboutToHide.connect(_on_about_to_hide)
        self.popup_at(global_pos)
        loop.exec()
        self.actionTriggered.disconnect(_on_triggered)
        self.aboutToHide.disconnect(_on_about_to_hide)
        return result["id"]
