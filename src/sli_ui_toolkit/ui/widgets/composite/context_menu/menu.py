"""ContextMenu shell widget (BaseFlyout subclass)."""

from __future__ import annotations

import logging
from typing import Callable, Iterable, Literal

logger = logging.getLogger(__name__)

import shiboken6 as sip

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.config import get_context_menu_surface
from sli_ui_toolkit.core.debug_flags import any_flag
from sli_ui_toolkit.i18n import translator_for
from sli_ui_toolkit.ui.widgets.buttons.feedback import get_ripple_duration_ms
from sli_ui_toolkit.ui.popup_surface import (
    bind_popup_transient_parent,
    configure_popup_widget,
    popup_contains_global,
)
from sli_ui_toolkit.ui.managers.ui_metrics import (
    AXIS_FONT,
    AXIS_SCALE,
    connect_ui_metrics,
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.ui.widgets.composite.context_menu import content as content_ops
from sli_ui_toolkit.ui.widgets.composite.context_menu import popup as popup_ops
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuEntry,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import ContextMenuRow
from sli_ui_toolkit.ui.widgets.composite.context_menu import submenu as submenu_ops

# Canonical toolkit var for context-menu key traces. Call-time check,
# ``[ctx-menu]`` prefix on every line, off by default even under host
# ``--debug``. Never mutates logger levels at import time.
_CTX_MENU_DEBUG_VARS = ("SLI_CTX_MENU_DEBUG",)


def _ctx_menu_debug_enabled() -> bool:
    """True when context-menu tracing was opted in via env."""
    return any_flag(*_CTX_MENU_DEBUG_VARS)


def _ctx_menu_debug(message: str, *args) -> None:
    """Env-gated context-menu trace line (already carries its ``[ctx-menu]`` prefix)."""
    if _ctx_menu_debug_enabled():
        logger.debug(message, *args)


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
        # Pending hover-open (FM parity): a single-shot QTimer started when
        # the pointer enters a parent row, cancelled when it leaves before
        # SUBMENU_HOVER_DELAY_MS. Never confused with _open_submenu.
        self._submenu_hover_timer: QTimer | None = None
        self._submenu_hover_row: ContextMenuRow | None = None
        # The row whose submenu was just closed (toggle/leaf/outside). While
        # the pointer never left that row, the popup hide makes Qt re-deliver
        # a hover Enter to it; without this guard that Enter re-schedules the
        # hover-open and the branch blinks (closes, reopens). Cleared on the
        # row's Leave (or when another row is entered).
        self._submenu_closed_row: ContextMenuRow | None = None
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
        # The menu is cached across a live appearance change (Settings → OK);
        # re-derive every cached chrome metric (row/section/separator heights,
        # gutter, trailing widths, icons, own size) through the bus.
        connect_ui_metrics(
            self,
            self._on_ui_metrics_changed,
            axes=frozenset({AXIS_FONT, AXIS_SCALE}),
        )
        if entries is not None:
            self.set_entries(entries)

    def _on_ui_metrics_changed(self, *_args) -> None:
        """Re-fit the cached menu for the new font/scale (appearance bus)."""
        self._relayout_widths()

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

    def set_translator(self, tr_func, *, defer_when_hidden: bool = False) -> None:
        """Duck-typed protocol hook used by ``bind_translator``/``install_translator``."""
        self._sli_translator = tr_func
        self._sli_defer_when_hidden = defer_when_hidden

    def retranslate(self, lang: str) -> None:
        """Re-resolve every keyed row's text/tooltip, then refresh metrics/layout.

        Entries are retained on each row (``row._spec``), so this never rebuilds
        the menu — it mutates the live rows and re-runs the width pass.
        """
        tr_func = translator_for(self)
        changed = False
        for row in list(self._rows):
            spec = getattr(row, "_spec", None)
            if spec is None:
                continue
            text_key = getattr(spec, "text_key", None)
            if text_key:
                # Rows paint ``widget._text`` directly (``_RowContentLayer``);
                # set it and refresh metrics without a full ``setText`` (which
                # would flip the row's text geometry policy).
                row._text = tr_func(text_key, lang)
                row._has_text = bool(row._text)
                row.refresh_metrics()
                row.update()
                changed = True
            tooltip_key = getattr(spec, "tooltip_key", None)
            if tooltip_key:
                row.setToolTip(tr_func(tooltip_key, lang))
        if changed:
            self._relayout_widths()
        submenu = getattr(self, "_open_submenu", None)
        if submenu is not None:
            try:
                submenu.retranslate(lang)
            except (RuntimeError, SystemError):
                pass

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
        _ctx_menu_debug(
            "[ctx-menu] row click action_id=%s -> close submenu", action_id
        )
        submenu_ops.close_submenu(self, reason="row-click")
        submenu_ops.root_menu(self).hide()
        self.actionTriggered.emit(action_id, data)
        if self._on_triggered is not None:
            self._on_triggered(action_id, data)

    def _root_menu(self) -> "ContextMenu":
        return submenu_ops.root_menu(self)

    def _toggle_submenu(self, row: ContextMenuRow, spec) -> None:
        submenu_ops.toggle_submenu(self, row, spec)

    def _schedule_submenu_hover(self, row: ContextMenuRow, spec) -> None:
        """Start the hover-open delay for a parent row (FM parity).

        Fires ``open_submenu`` after ``SUBMENU_HOVER_DELAY_MS`` unless the
        pointer leaves first (see ``_cancel_submenu_hover``) or the submenu
        is already open on this row. Re-scheduling the same row while its
        timer is still pending is a no-op (Enter+HoverEnter both hit this
        path, and the submenu branch forwards repeated moves).
        """
        pending = self._submenu_hover_timer
        if pending is not None and self._submenu_hover_row is row:
            try:
                if pending.isActive():
                    _ctx_menu_debug(
                        "[ctx-menu] hover schedule row=%s already pending -> keep",
                        getattr(getattr(row, "_spec", None), "action_id", None),
                    )
                    return
            except RuntimeError:
                pass
        self._cancel_submenu_hover()
        if self._open_submenu is None and row is self._submenu_closed_row:
            _ctx_menu_debug(
                "[ctx-menu] hover schedule row=%s suppressed (just-closed owner)",
                getattr(getattr(row, "_spec", None), "action_id", None),
            )
            return
        if self._open_submenu is not None and self._submenu_owner_row is row:
            _ctx_menu_debug(
                "[ctx-menu] hover schedule row=%s already owner -> keep",
                getattr(getattr(row, "_spec", None), "action_id", None),
            )
            return
        _ctx_menu_debug(
            "[ctx-menu] hover schedule row=%s delay_ms=%d",
            getattr(getattr(row, "_spec", None), "action_id", None),
            submenu_ops.SUBMENU_HOVER_DELAY_MS,
        )
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(submenu_ops.SUBMENU_HOVER_DELAY_MS)
        timer.timeout.connect(
            lambda: self._on_submenu_hover_timeout(row, spec, timer)
        )
        self._submenu_hover_timer = timer
        self._submenu_hover_row = row
        timer.start()

    def _cancel_submenu_hover(self) -> None:
        """Drop a pending hover-open; an already-open submenu is untouched."""
        had_pending = self._submenu_hover_timer is not None
        submenu_ops._cancel_pending_hover(self)
        if had_pending:
            _ctx_menu_debug("[ctx-menu] hover cancelled (pointer left first)")

    def _on_submenu_hover_timeout(self, row: ContextMenuRow, spec, timer: QTimer) -> None:
        if self._submenu_hover_timer is not timer:
            return  # superseded by a newer hover (or cancelled)
        self._submenu_hover_timer = None
        self._submenu_hover_row = None
        try:
            if not sip.isValid(self) or not sip.isValid(row):  # type: ignore[attr-defined]
                return
        except Exception:
            return
        if not self.isVisible() or row not in self._rows:
            _ctx_menu_debug(
                "[ctx-menu] hover timeout row=%s dropped (visible=%s in_rows=%s)",
                getattr(spec, "action_id", None),
                self.isVisible(),
                row in self._rows,
            )
            return
        _ctx_menu_debug(
            "[ctx-menu] hover timeout row=%s -> open",
            getattr(spec, "action_id", None),
        )
        submenu_ops.open_submenu(self, row, spec)

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
        event_type = event.type()
        if self._open_submenu is not None and event_type in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
        ):
            # Hover forwarding: the open submenu holds the mouse grab, so
            # the owner's rows see no Enter events. Hit-test the forwarded
            # position instead (sibling switch / leaf close).
            if submenu_ops._is_forwarded_obj(self, obj):
                global_pos = None
                try:
                    global_pos = event.globalPosition().toPoint()
                except AttributeError:
                    try:
                        global_pos = event.globalPos()
                    except AttributeError:
                        global_pos = None
                if global_pos is not None:
                    _ctx_menu_debug(
                        "[ctx-menu] forward move pos=%s -> hit-test", global_pos
                    )
                    submenu_ops._handle_submenu_forward(self, global_pos)
                return super().eventFilter(obj, event)
        if isinstance(obj, ContextMenuRow):
            if self._open_submenu is not None and submenu_ops._is_forwarded_obj(
                self, obj
            ):
                # Enter/Leave inside the open submenu branch: the branch owns
                # its own hover. Reading it as sibling motion closed the
                # submenu out from under the pointer on the first step into
                # it (live: recent-empty Sort by -> first leaf Enter killed
                # the branch as "sibling leaf"). Ignore for sibling logic.
                if event_type in (
                    QEvent.Type.Enter,
                    QEvent.Type.HoverEnter,
                    QEvent.Type.Leave,
                    QEvent.Type.HoverLeave,
                ):
                    _ctx_menu_debug(
                        "[ctx-menu] branch row %s action_id=%s -> ignore (own hover)",
                        "enter"
                        if event_type
                        in (QEvent.Type.Enter, QEvent.Type.HoverEnter)
                        else "leave",
                        getattr(getattr(obj, "_spec", None), "action_id", None),
                    )
                    return super().eventFilter(obj, event)
            if event_type in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                spec = getattr(obj, "_spec", None)
                action_id = getattr(spec, "action_id", None)
                has_children = bool(getattr(spec, "children", ()))
                if obj is not self._submenu_closed_row:
                    if self._submenu_closed_row is not None:
                        _ctx_menu_debug(
                            "[ctx-menu] just-closed guard cleared "
                            "(entered other row action_id=%s)",
                            action_id,
                        )
                    # Pointer is on a different row now — the just-closed
                    # owner may reopen on a later re-entry.
                    self._submenu_closed_row = None
                _ctx_menu_debug(
                    "[ctx-menu] row enter action_id=%s children=%s open=%s",
                    action_id,
                    has_children,
                    self._open_submenu is not None,
                )
                if spec is not None and has_children:
                    self._schedule_submenu_hover(obj, spec)
                elif self._open_submenu is not None:
                    # Sibling leaf hovered: drop the open submenu (native-menu
                    # parity) so only one branch stays open at a time.
                    # Moving from the owner row straight into its submenu
                    # never hovers a sibling row, so this cannot steal the
                    # submenu out from under the pointer.
                    _ctx_menu_debug(
                        "[ctx-menu] row enter action_id=%s -> close (sibling leaf)",
                        action_id,
                    )
                    submenu_ops.close_submenu(self, reason="sibling-leaf-hover")
            elif event_type in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                if obj is self._submenu_closed_row:
                    _ctx_menu_debug(
                        "[ctx-menu] just-closed guard cleared "
                        "(pointer left row action_id=%s)",
                        getattr(getattr(obj, "_spec", None), "action_id", None),
                    )
                    # Pointer actually left the just-closed owner; a later
                    # re-entry may hover-open it again.
                    self._submenu_closed_row = None
                _ctx_menu_debug(
                    "[ctx-menu] row leave action_id=%s",
                    getattr(getattr(obj, "_spec", None), "action_id", None),
                )
                self._cancel_submenu_hover()
        # Rows are child Buttons — they receive presses before the menu widget.
        if (
            event_type == QEvent.Type.MouseButtonPress
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
        _ctx_menu_debug(
            "[ctx-menu] hide surface=%s had_submenu=%s fade_out=%s "
            "fade_in_progress=%s visible=%s is_submenu=%s",
            self._surface,
            self._open_submenu is not None,
            popup_ops.should_popup_fade_out(self),
            self._popup_fade_in_progress,
            self.isVisible(),
            self._is_submenu,
        )
        # A hide while our own fade-out is already running is a no-op: the
        # finish handler owns the real hide + deleteLater. Without this,
        # cascade re-entry (owner hide -> branch hide -> owner hide) would
        # restart animations and double-emit aboutToHide.
        if getattr(self, "_popup_fade_anim", None) is not None:
            _ctx_menu_debug("[ctx-menu] hide suppressed — fade already in flight")
            return
        # Only the root menu fades (submenus never do — see ``toggle_submenu``).
        # Start our own fade BEFORE detaching the branch: the snapshot must
        # keep the owner row's open-highlight (detaching repaints it plain
        # while still fully opaque — a one-frame unhover flash).
        fading = popup_ops.should_popup_fade_out(self)
        if fading:
            # Popup surface shown with a fade-bearing animation: fade out
            # first, then really hide + emit aboutToHide + deleteLater once
            # the widget is off screen (see popup._on_popup_fade_out_finished).
            popup_ops.start_popup_fade_out(self)
        submenu_ops.close_submenu(self, reason="parent-hide")
        # The menu is going away; drop the just-closed-owner guard so a later
        # show of this instance is not affected.
        self._submenu_closed_row = None
        if not self.is_popup_surface():
            self._visible_menus.discard(self)
        if fading:
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
            _ctx_menu_debug("[ctx-menu] Escape pressed, submenu=%s", self._open_submenu is not None)
            if self._open_submenu is not None:
                submenu_ops.close_submenu(self)
                event.accept()
                return
            self.hide()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = QApplication.focusWidget()
            _ctx_menu_debug("[ctx-menu] Enter pressed, focused=%s rows=%d", type(focused).__name__ if focused else None, len(self._rows))
            if focused is not None:
                for row in self._rows:
                    if row is focused or row.isAncestorOf(focused):
                        spec = getattr(row, "_spec", None)
                        if spec is not None:
                            _ctx_menu_debug("[ctx-menu] Enter -> activate row action_id=%s", spec.action_id)
                            self._on_row_clicked(row, spec)
                            event.accept()
                            return
            event.accept()
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            _ctx_menu_debug("[ctx-menu] %s pressed", "Down" if key == Qt.Key.Key_Down else "Up")
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
