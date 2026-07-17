"""ContextMenu shell widget (BaseFlyout subclass)."""

from __future__ import annotations

import math
from typing import Callable, Iterable, Literal, Sequence

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QEventLoop,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.config import get_context_menu_surface, get_flyout_timings
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
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout import (
    AnimationAxis,
    BaseFlyout,
    _point_in_rect,
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
        # Popup menus must never attach to the host OverlayLayer: attach +
        # setParent(None) reorders overlay children and can shove open flyouts
        # off their geometry. Keep the QWidget parent so Wayland gets a
        # transient parent (parentless popups are compositor-centered).
        super().__init__(parent, attach_overlay=not (self._surface == "popup"))
        self._on_triggered = on_triggered
        self._rows: list[ContextMenuRow] = []
        # Menus must not steal window activation (Wayland / QRhi).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if self.is_popup_surface():
            configure_popup_widget(self)
            bind_popup_transient_parent(self, parent)
        elif _is_submenu:
            self.flyout_manager.unregister_flyout(self)
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
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        flat = _trim_flat_separators(self._flatten(tuple(entries)))
        check_gutter = 28 if any(
            isinstance(item, ContextMenuAction) and item.checkable for item in flat
        ) else 12
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
            widget = self.content_layout.itemAt(index).widget()
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
            widget = self.content_layout.itemAt(index).widget()
            if widget is None:
                continue
            hint = widget.sizeHint()
            if hint.isValid():
                max_w = max(max_w, hint.width())

        if max_w <= 0:
            self.adjustSize()
            return

        for index in range(self.content_layout.count()):
            widget = self.content_layout.itemAt(index).widget()
            if widget is not None:
                widget.setMinimumWidth(max_w)

        self.setMinimumSize(0, 0)
        if self.container.layout():
            self.container.layout().invalidate()
            self.container.layout().activate()
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
        submenu_ops.close_submenu(self)
        submenu_ops.root_menu(self).hide()
        self.actionTriggered.emit(spec.action_id, spec.data)
        if self._on_triggered is not None:
            self._on_triggered(spec.action_id, spec.data)

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
        if event.key() == Qt.Key.Key_Escape and self._open_submenu is not None:
            submenu_ops.close_submenu(self)
            event.accept()
            return
        super().keyPressEvent(event)

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

    def _popup_show_aligned(
        self,
        anchor_widget: QWidget,
        anchor_point: str = "bottom-center",
        flyout_point: str = "top-center",
        *,
        position: str | None = None,
        offset: int = 5,
        animation: str = "none",
        animation_duration_ms: int | None = None,
        animation_distance: int | None = None,
        animation_axis: AnimationAxis = "auto",
        easing: QEasingCurve.Type = QEasingCurve.Type.OutQuad,
    ) -> None:
        self._anchor_widget = anchor_widget
        if self.container.layout():
            self.container.layout().invalidate()
            self.container.layout().activate()
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
            anchor_pt = _point_in_rect(anchor_rect, anchor_point)
            flyout_pt_local = _point_in_rect(
                QRect(QPoint(0, 0), flyout_size),
                flyout_point,
            )
            top_left = QPoint(
                anchor_pt.x() - flyout_pt_local.x(),
                anchor_pt.y() - flyout_pt_local.y(),
            )
            flyout_center = QPoint(
                top_left.x() + flyout_size.width() // 2,
                top_left.y() + flyout_size.height() // 2,
            )
            dir_x = flyout_center.x() - anchor_rect.center().x()
            dir_y = flyout_center.y() - anchor_rect.center().y()
            length = math.hypot(dir_x, dir_y)
            push = offset - self.SHADOW_RADIUS
            if length > 0 and push != 0:
                ux, uy = dir_x / length, dir_y / length
                top_left = QPoint(
                    top_left.x() + int(round(push * ux)),
                    top_left.y() + int(round(push * uy)),
                )
            final_rect = clamp_popup_rect(
                QRect(top_left, flyout_size),
                self,
                margin=0,
            )
            flyout_center = final_rect.center()

        dir_x = flyout_center.x() - anchor_rect.center().x()
        dir_y = flyout_center.y() - anchor_rect.center().y()
        length = math.hypot(dir_x, dir_y)
        if length > 0:
            ux, uy = dir_x / length, dir_y / length
        else:
            ux = uy = 0.0

        mode = animation if animation else "none"
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

        if animation_axis == "vertical":
            slide_dx = 0
            slide_dy = (
                -distance
                if flyout_center.y() >= anchor_rect.center().y()
                else distance
            )
        elif animation_axis == "horizontal":
            slide_dy = 0
            slide_dx = (
                -distance
                if flyout_center.x() >= anchor_rect.center().x()
                else distance
            )
        else:
            slide_dx = -ux * distance if length > 0 else 0
            slide_dy = -uy * distance if length > 0 else 0
        start_pos = QPoint(
            final_rect.x() + int(round(slide_dx)),
            final_rect.y() + int(round(slide_dy)),
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

    def popup_at(self, global_pos: QPoint) -> None:
        submenu_ops.close_submenu(self)
        self._relayout_widths()
        if self.container.layout():
            self.container.layout().invalidate()
            self.container.layout().activate()
            self.container.updateGeometry()
        self.adjustSize()

        # Keep the open cursor outside the widget (incl. shadow) so the same
        # spot can dismiss on the next press. Opaque content still sits near
        # the cursor via the shadow inset.
        origin = global_pos + QPoint(1, 1)
        if self.is_popup_surface():
            bind_popup_transient_parent(self, self._logical_parent)
            place_popup_at_global(self, origin, margin=4)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.show()
            self.raise_()
            # Wayland may ignore pre-show geometry; re-apply once mapped.
            place_popup_at_global(self, origin, margin=4)
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
        self.show()
        self.raise_()
        # Do not setFocus(): on Wayland focusing a ContextMenu can emit
        # ApplicationDeactivate, which then closes the menu and jerks QRhi
        # canvases. Escape is handled via FlyoutManager / key filters.

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
