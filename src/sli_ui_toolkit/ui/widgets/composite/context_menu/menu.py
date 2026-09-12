"""ContextMenu shell widget (BaseFlyout subclass)."""

from __future__ import annotations

import logging
from typing import Callable, Iterable, Literal

logger = logging.getLogger(__name__)

import shiboken6 as sip

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.config import get_context_menu_surface
from sli_ui_toolkit.ui.widgets.buttons.feedback import get_ripple_duration_ms
from sli_ui_toolkit.ui.popup_surface import (
    bind_popup_transient_parent,
    configure_popup_widget,
    popup_contains_global,
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.ui.widgets.composite.context_menu import content as content_ops
from sli_ui_toolkit.ui.widgets.composite.context_menu import popup as popup_ops
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuEntry,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import ContextMenuRow
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

    # -------- entries (content.py) --------

    def set_entries(self, entries: Iterable[ContextMenuEntry]) -> None:
        content_ops.set_entries(self, entries)

    def _relayout_widths(self) -> None:
        content_ops._relayout_widths(self)

    def _build_row(self, item, check_gutter: int) -> QWidget:
        return content_ops._build_row(self, item, check_gutter)

    def _on_row_clicked(self, row: ContextMenuRow, spec) -> None:
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

    def _root_menu(self) -> "ContextMenu":
        return submenu_ops.root_menu(self)

    def _toggle_submenu(self, row: ContextMenuRow, spec) -> None:
        submenu_ops.toggle_submenu(self, row, spec)

    def _position_submenu(self, submenu: "ContextMenu", row: ContextMenuRow) -> None:
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

    def eventFilter(self, obj, event):  # noqa: N802
        # Rows are child Buttons — they receive presses before the menu widget.
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.RightButton
        ):
            submenu_ops.root_menu(self).hide()
            return True
        return super().eventFilter(obj, event)

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
        if popup_ops.should_popup_fade_out(self):
            # Popup surface shown with a fade-bearing animation: fade out
            # first, then really hide + emit aboutToHide + deleteLater once
            # the widget is off screen (see popup._on_popup_fade_out_finished).
            popup_ops.start_popup_fade_out(self)
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

    # -------- public show API (popup.py) --------

    def show_aligned(
        self,
        anchor_widget,
        anchor_point="bottom-center",
        flyout_point="top-center",
        **kwargs,
    ):
        self._relayout_widths()
        if self.is_popup_surface():
            popup_ops.popup_show_aligned(
                self,
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

    def popup_at(self, global_pos: QPoint, *, animation: str | None = None) -> None:
        popup_ops.popup_at(self, global_pos, animation=animation)

    def exec_at(self, global_pos: QPoint) -> str | None:
        return popup_ops.exec_at(self, global_pos)
