"""InspectorController: hover/Shift+click selection, per-window overlays with
per-region highlight, live token capture — drives ``InspectorWindow``.

Ported from the app's inspector controller (same Wayland rules: overlays are
in-process children of the inspected window; no global grabs).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

from .capture import capture_tokens
from .overlay import InspectorOverlay
from .qss_scan import QssIndex
from .registry import inspect_widget

logger = logging.getLogger("sli_ui_toolkit.inspector")


class InspectorController(QObject):
    def __init__(self, app: QApplication, window: "InspectorWindow", theme_manager):
        super().__init__(window)
        self._app = app
        self._window = window
        self._theme_manager = theme_manager
        self._qss_index = QssIndex.from_theme_manager(theme_manager)
        # Optional token → "file:line" map rendered on the Theme page
        # (the app fills it from its themes.json).
        self._token_sources: dict[str, str] = {}
        self._qss_dead: dict[tuple[str, str, int], bool] | None = None
        self._qss_dead_widget_count: int = -1
        self._overlays: dict[QWidget, InspectorOverlay] = {}
        self._active_overlay: InspectorOverlay | None = None
        self._enabled = True
        self._committed_widget: QWidget | None = None
        self._hover_widget: QWidget | None = None
        self._hovered_region: str | None = None
        self._shift_held = False
        # Highlight suspended while the user works in the inspected window
        # (plain click there hides the overlay; returning to the inspector
        # restores it for the still-committed widget).
        self._overlay_suspended = False
        # Same-physical-press dedup key (pos, timestamp) — one press can be
        # delivered to the app filter several times via re-dispatch.
        self._last_press_key: tuple[int, int, int] | None = None
        # Window whose ApplicationModal modality was lifted while the
        # inspector commits a widget inside it (modal windows block every
        # other app window — including the inspector's own).
        self._lifted_modal: tuple[QWidget, Qt.WindowType] | None = None
        # Last top-level window that wasn't inspector chrome (used by the
        # app's "dump layout" action to target the window you were using).
        self._last_focused_window: QWidget | None = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(30)
        self._hover_timer.timeout.connect(self._poll_hover)

        window.region_selected.connect(self._on_region_selected)
        window.widget_activated.connect(self._on_widget_activated)
        window.widget_hovered.connect(self._on_tree_hover)
        window.widget_hover_cleared.connect(self._on_tree_hover_cleared)
        window.capture_requested.connect(self._capture_tokens)
        window.refresh_requested.connect(self._resnapshot)
        self._app.installEventFilter(self)

    def shutdown(self) -> None:
        self._hover_timer.stop()
        self._app.removeEventFilter(self)
        self._overlay_suspended = False
        self._restore_modality()
        for window, overlay in self._overlays.items():
            try:
                window.removeEventFilter(self)
            except RuntimeError:
                pass
            try:
                overlay.hide()
                overlay.deleteLater()
            except RuntimeError:
                pass
        self._overlays.clear()
        self._active_overlay = None

    # -- event plumbing -----------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.KeyPress and self._handle_key_press(event):
            return True
        if event_type == QEvent.Type.KeyRelease:
            self._handle_key_release(event)
        if event_type in {QEvent.Type.Close, QEvent.Type.DeferredDelete} and isinstance(
            obj, QWidget
        ):
            overlay = self._overlays.pop(obj, None)
            if overlay is not None and overlay is self._active_overlay:
                self._active_overlay = None
            # Drop our own filter from the closing window too — otherwise
            # ``shutdown`` no longer finds it in ``_overlays`` (popped above)
            # and the controller stays attached to a dying window.
            try:
                obj.removeEventFilter(self)
            except RuntimeError:
                pass
            if self._widget_is_within(obj, self._committed_widget) or self._widget_is_within(
                obj, self._hover_widget
            ):
                # The inspected window (or the committed row inside it) is
                # gone — drop the stale references, or every later interaction
                # crashes on the deleted widgets and the inspector hangs.
                logger.debug(
                    "inspected widget's window closed: %s#%s",
                    type(obj).__name__,
                    obj.objectName(),
                )
                self._reset_selection()
            if obj is self._window:
                # The inspector window itself closed — take its highlight
                # (and the modal lift) down with it.
                logger.debug("inspector window closed")
                self._reset_selection()
            return False
        if event_type == QEvent.Type.Hide and isinstance(obj, QWidget):
            if self._lifted_modal is not None and obj is self._lifted_modal[0]:
                # The modal hid (e.g. its reject/accept path) — detach the
                # inspector child window, or it would hide along with it.
                self._restore_modality()
            return False
        if event_type == QEvent.Type.Resize and isinstance(obj, QWidget):
            self._sync_overlay_for(obj)
            return False
        if event_type == QEvent.Type.WindowActivate and isinstance(obj, QWidget):
            if obj.isWindow() and not bool(obj.property("_ui_inspector_owned")):
                self._last_focused_window = obj
            # NOTE: no overlay resume here — the inspector window can get
            # activated spontaneously (compositor focus handling) and would
            # re-light a suspended highlight on its own. The highlight is
            # restored only by an actual click on the inspector window
            # (see ``_handle_mouse_press``).
            return False
        if not self._enabled:
            return False
        if event_type == QEvent.Type.MouseButtonPress:
            if self._handle_mouse_press(event):
                return True
        return False

    def _handle_key_press(self, event) -> bool:
        modifiers = event.modifiers()
        key = event.key()
        if (
            key == Qt.Key.Key_I
            and modifiers & Qt.KeyboardModifier.ControlModifier
            and modifiers & Qt.KeyboardModifier.ShiftModifier
        ):
            self._enabled = not self._enabled
            logger.debug(
                "Ctrl+Shift+I toggle: inspector %s",
                "ENABLED" if self._enabled else "disabled",
            )
            if self._enabled:
                self._refresh_overlay()
                if self._committed_widget is not None:
                    self._window.show()
                    self._window.raise_()
            else:
                self._reset_selection()
                self._hide_overlays()
                self._window.hide()
            return True
        if key == Qt.Key.Key_Escape and self._enabled:
            from sli_ui_toolkit.managers import NavigationManager
            if NavigationManager.get_instance().should_intercept(Qt.Key.Key_Escape):
                return False
            logger.debug("Escape: clearing selection")
            self._reset_selection()
            return True
        if self._enabled and key == Qt.Key.Key_Shift and not self._shift_held:
            self._shift_held = True
            self._hover_timer.start()
            self._poll_hover()
        return False

    def _handle_key_release(self, event) -> None:
        if event.key() != Qt.Key.Key_Shift:
            return
        self._shift_held = False
        self._hover_timer.stop()
        self._hovered_region = None
        if self._hover_widget is not None:
            self._hover_widget = None
            self._refresh_overlay()

    def _handle_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        global_pos = _event_global_pos(event)
        first = self._is_first_press_log(global_pos, event)
        widget = QApplication.widgetAt(global_pos)
        if widget is not None and self._is_inspector_widget(widget):
            if self._widget_is_within(self._window, widget):
                # Click on the inspector window itself — bring the highlight
                # of the still-committed widget back.
                if first:
                    logger.debug(
                        "click on inspector window: %s#%s at %s (win geo=%s) under=%s",
                        type(widget).__name__,
                        widget.objectName(),
                        global_pos,
                        self._window.geometry(),
                        self._widget_below(global_pos, exclude=self._window),
                    )
                self._resume_overlay()
            else:
                # Click landed on an inspector-owned overlay floating over the
                # inspected window (widgetAt can report it despite
                # WA_TransparentForMouseEvents) — treat it as a click on the
                # inspected window: hide the highlight.
                if first:
                    logger.debug(
                        "click on overlay: %s#%s at %s",
                        type(widget).__name__,
                        widget.objectName(),
                        global_pos,
                    )
                self._suspend_overlay()
            return False
        if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._committed_widget is not None or self._hover_widget is not None:
                # Plain click in the inspected window: hide the highlight so
                # the window can be used normally — keep the committed widget
                # so returning to the inspector restores it.
                self._suspend_overlay()
            return False
        widget = _resolve_meaningful_widget(widget)
        if widget is None or widget.window() is self._window:
            return False
        self._select_widget(widget, global_pos=global_pos)
        return True

    def _is_first_press_log(self, global_pos: QPoint, event) -> bool:
        """True for the first delivery of a physical press (the same press can
        reach the app filter several times via re-dispatch)."""
        try:
            stamp = int(event.timestamp())
        except Exception:
            stamp = -1
        key = (global_pos.x(), global_pos.y(), stamp)
        if key == self._last_press_key:
            return False
        self._last_press_key = key
        return True

    def _widget_below(self, global_pos: QPoint, *, exclude: QWidget) -> str:
        """Describe the top-level + deepest child under a global point, for
        overlap diagnostics (what the user actually aimed at)."""
        for top in QApplication.topLevelWidgets():
            if top is exclude or not top.isVisible():
                continue
            local = top.mapFromGlobal(global_pos)
            if not top.rect().contains(local):
                continue
            child = top.childAt(local)
            if child is not None and child is not top:
                label = f"{type(top).__name__} -> {type(child).__name__}"
                name = child.objectName()
                if name:
                    label += f"#{name}"
                return label
            return type(top).__name__
        return "none"

    # -- selection ----------------------------------------------------------

    def _is_valid_widget(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        try:
            from shiboken6 import isValid  # type: ignore[attr-defined]

            return bool(isValid(widget))
        except ImportError:
            pass
        try:
            widget.isVisible()
            return True
        except RuntimeError:
            return False

    def _widget_is_within(self, container: QWidget, target: QWidget | None) -> bool:
        if target is None or not self._is_valid_widget(target):
            return False
        node: QWidget | None = target
        while node is not None:
            if node is container:
                return True
            node = node.parentWidget()
        return False

    def _lift_modality_for(self, window: QWidget) -> None:
        try:
            modality = window.windowModality()
        except RuntimeError:
            return
        logger.debug(
            "modality lift: window=%s#%s modality=%s",
            type(window).__name__,
            window.objectName(),
            modality,
        )
        self._restore_modality()
        if modality == Qt.WindowModality.NonModal:
            return
        # setParent(parent, flags) *replaces* the widget's window flags with
        # the passed ones — hand the original flags back, or the inspector's
        # CSD/frameless setup (InspectorWindow is a decorated QDialog) breaks.
        flags = self._window.windowFlags()
        self._lifted_modal = (window, flags)
        # Qt's modal input filter blocks every top-level except the modal
        # window and its descendants. Reparenting the inspector window as a
        # *child window* of the modal makes it fully interactive without any
        # hide/show — hiding the modal would visibly close and reopen it (the
        # modal stack only pops on hide).
        try:
            global_pos = self._window.mapToGlobal(QPoint(0, 0))
            self._window.setParent(window, flags)
            self._window.move(window.mapFromGlobal(global_pos))
            self._window.show()
        except RuntimeError:
            self._lifted_modal = None
        logger.debug(
            "modal lift via child-window: inspector parent=%s#%s flags=0x%x",
            type(window).__name__,
            window.objectName(),
            int(flags.value) if hasattr(flags, "value") else 0,
        )

    def _restore_modality(self) -> None:
        if self._lifted_modal is None:
            return
        window, flags = self._lifted_modal
        self._lifted_modal = None
        logger.debug(
            "modality restore: inspector parent=%s#%s",
            type(window).__name__,
            window.objectName(),
        )
        try:
            # Put the inspector window back as an independent top-level with
            # its original flags (CSD/frameless must survive the round trip).
            global_pos = self._window.mapToGlobal(QPoint(0, 0))
            self._window.setParent(None, flags)
            self._window.move(global_pos)
            self._window.show()
        except RuntimeError:
            pass

    def _reset_selection(self) -> None:
        logger.debug(
            "selection reset (committed=%s hover=%s)",
            type(self._committed_widget).__name__ if self._committed_widget is not None else None,
            type(self._hover_widget).__name__ if self._hover_widget is not None else None,
        )
        self._committed_widget = None
        self._hover_widget = None
        self._hovered_region = None
        self._shift_held = False
        self._overlay_suspended = False
        self._hover_timer.stop()
        self._restore_modality()
        self._clear_active_overlay()

    def _suspend_overlay(self) -> None:
        """Hide the highlight so the inspected window can be used normally.

        The committed widget is kept — ``_resume_overlay`` restores the
        highlight when the user comes back to the inspector window.
        """
        if self._overlay_suspended:
            return
        logger.debug(
            "overlay suspended (committed=%s)",
            type(self._committed_widget).__name__
            if self._committed_widget is not None
            else None,
        )
        self._overlay_suspended = True
        self._hover_widget = None
        self._hovered_region = None
        self._hover_timer.stop()
        self._clear_active_overlay()

    def _resume_overlay(self) -> None:
        if not self._overlay_suspended:
            return
        self._overlay_suspended = False
        logger.debug(
            "overlay resumed (committed=%s)",
            type(self._committed_widget).__name__
            if self._committed_widget is not None
            else None,
        )
        if self._committed_widget is not None:
            self._refresh_overlay()

    def _select_widget(self, widget: QWidget, *, global_pos: QPoint) -> None:
        if not self._is_valid_widget(widget):
            self._reset_selection()
            return
        window = widget.window()
        logger.debug(
            "select widget=%s#%s in window=%s#%s modality=%s (widget visible=%s window visible=%s)",
            type(widget).__name__,
            widget.objectName(),
            type(window).__name__,
            window.objectName(),
            window.windowModality(),
            widget.isVisible(),
            window.isVisible(),
        )
        self._lift_modality_for(window)
        self._committed_widget = widget
        self._hover_widget = None
        self._hovered_region = None
        self._overlay_suspended = False
        self._refresh_overlay()
        inspection = inspect_widget(widget, self._theme_manager)
        self._window.open_widget(widget, self._label_for(widget))
        self._window.set_inspection(
            inspection,
            widget=widget,
            theme_manager=self._theme_manager,
            qss_candidates=self._qss_index.candidates_for(widget),
            qss_dead=self._qss_dead_map(),
            token_sources=self._token_sources,
        )
        self._window.show()
        self._window.raise_()
        self._activate_inspector_window()
        logger.debug(
            "inspector window shown: isVisible=%s isActiveWindow=%s activeWindow=%s activeModalWidget=%s",
            self._window.isVisible(),
            self._window.isActiveWindow(),
            type(QApplication.activeWindow()).__name__
            if QApplication.activeWindow() is not None
            else None,
            type(QApplication.activeModalWidget()).__name__
            if QApplication.activeModalWidget() is not None
            else None,
        )
        self._layout_nodes_for(widget)
        self._constructor_nodes_for(widget)

    def _activate_inspector_window(self) -> None:
        """Wayland-safe activation of the inspector window.

        ``activateWindow()``/``raise_()`` can be a no-op while the platform
        window is still mapping — and the lifted modal re-shows right before
        us, grabbing focus again. Retry on zero timers (same pattern the
        app's dialogs use for their first-focus widget).
        """

        def _do_activate() -> None:
            if not self._is_valid_widget(self._window):
                return
            try:
                self._window.activateWindow()
                handle = self._window.windowHandle()
                if handle is not None:
                    handle.requestActivate()
            except RuntimeError:
                pass

        _do_activate()
        QTimer.singleShot(0, _do_activate)
        QTimer.singleShot(60, _do_activate)

    def _on_widget_activated(self, widget: QWidget) -> None:
        if isinstance(widget, QWidget):
            # ``_select_widget`` validates and resets stale selections.
            self._select_widget(widget, global_pos=QCursor.pos())

    def _on_tree_hover(self, widget: QWidget | None) -> None:
        """Hover over a Layout/Constructor tree row → highlight the widget in
        its window via the overlay (same pipeline as Shift-hover)."""
        if not self._enabled or not self._is_valid_widget(widget):
            return
        if self._hover_widget is widget:
            return
        logger.debug(
            "tree hover: %s (suspended=%s)",
            type(widget).__name__,
            self._overlay_suspended,
        )
        self._hover_widget = widget
        self._hovered_region = None
        self._refresh_overlay()

    def _on_tree_hover_cleared(self) -> None:
        if self._hover_widget is None:
            return
        logger.debug("tree hover cleared")
        self._hover_widget = None
        self._hovered_region = None
        self._refresh_overlay()

    def _on_region_selected(self, region_id: str) -> None:
        logger.debug("region selected: %s (suspended=%s)", region_id, self._overlay_suspended)
        self._hovered_region = region_id
        self._refresh_overlay()

    def _resnapshot(self) -> None:
        widget = self._committed_widget
        if not self._is_valid_widget(widget):
            self._reset_selection()
            return
        self._select_widget(widget, global_pos=QCursor.pos())

    def _capture_tokens(self) -> None:
        widget = self._committed_widget
        if widget is None:
            return
        inspection = inspect_widget(widget, self._theme_manager)
        from dataclasses import replace

        inspection = replace(
            inspection,
            live_tokens=capture_tokens(widget, self._theme_manager),
        )
        self._window.open_widget(widget, self._label_for(widget))
        self._window.set_inspection(
            inspection,
            widget=widget,
            theme_manager=self._theme_manager,
            qss_candidates=self._qss_index.candidates_for(widget),
            qss_dead=self._qss_dead_map(),
        )

    def _qss_dead_map(self) -> dict[tuple[str, str, int], bool]:
        """Rule identity → does any live widget match it (``False`` = the
        rule's selector matches nothing in the app — likely dead).

        Cached between selections and invalidated when the app's live widget
        count changes (lazily-created windows then stop lingering as dead).
        The inspector's own widgets are excluded from the scan, so opening
        more inspector tabs does not invalidate the cache on every select.
        """
        count = self._live_widget_count()
        if self._qss_dead is None or count != self._qss_dead_widget_count:
            self._qss_dead = {
                (rule.source, rule.selector, rule.line): matched
                for rule, matched in self._qss_index.dead_selectors(
                    self._app_widgets()
                )
            }
            self._qss_dead_widget_count = count
        return self._qss_dead

    def _app_widgets(self) -> list[QWidget]:
        """Every live widget in the app, excluding inspector-owned chrome."""
        widgets: list[QWidget] = []
        for top in QApplication.topLevelWidgets():
            if self._is_inspector_widget(top):
                continue
            widgets.append(top)
            widgets.extend(top.findChildren(QWidget))
        return widgets

    def _live_widget_count(self) -> int:
        return len(self._app_widgets())

    def _layout_nodes_for(self, widget: QWidget) -> None:
        if not self._is_valid_widget(widget):
            return
        nodes: list[tuple[str, object, int]] = []

        def walk(current: QWidget, depth: int) -> None:
            nodes.append((type(current).__name__, current, depth))
            for child in current.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if self._is_inspector_widget(child):
                    continue
                walk(child, depth + 1)

        walk(widget.window(), 0)
        self._window.set_layout_nodes(tuple(nodes))

    def _constructor_nodes_for(self, widget: QWidget) -> None:
        """Every widget inside the selected widget (its own subtree)."""
        if not self._is_valid_widget(widget):
            return
        nodes: list[tuple[str, object, int]] = []

        def walk(current: QWidget, depth: int) -> None:
            nodes.append((type(current).__name__, current, depth))
            for child in current.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if self._is_inspector_widget(child):
                    continue
                walk(child, depth + 1)

        walk(widget, 0)
        self._window.set_constructor_nodes(tuple(nodes))

    # -- hover --------------------------------------------------------------

    def _poll_hover(self) -> None:
        if not self._enabled or not self._shift_held:
            return
        pos = QCursor.pos()
        widget = QApplication.widgetAt(pos)
        if widget is not None and self._is_inspector_widget(widget):
            widget = None
        widget = _resolve_meaningful_widget(widget)
        if widget is self._hover_widget:
            return
        self._hover_widget = widget
        self._hovered_region = None
        self._refresh_overlay()

    def _refresh_overlay(self) -> None:
        if self._overlay_suspended:
            # The highlight is hidden while the user works in the inspected
            # window — tree hovers / region clicks / refresh paths must not
            # silently re-light it (that made the highlight look "stuck").
            logger.debug(
                "overlay refresh skipped (suspended; hover=%s committed=%s)",
                type(self._hover_widget).__name__
                if self._hover_widget is not None
                else None,
                type(self._committed_widget).__name__
                if self._committed_widget is not None
                else None,
            )
            return
        target = self._hover_widget or self._committed_widget
        if not self._is_valid_widget(target):
            self._reset_selection()
            return
        overlay = self._overlay_for(target.window())
        rect = _map_widget_rect(target, overlay.parentWidget())
        label = self._label_for(target)
        if self._active_overlay is not None and self._active_overlay is not overlay:
            self._active_overlay.clear_target()
            self._active_overlay.hide()
        self._active_overlay = overlay
        overlay.set_target(rect, label)
        overlay.set_regions(self._mapped_regions(target, overlay), self._hovered_region)

    def _mapped_regions(self, widget: QWidget, overlay: InspectorOverlay):
        if self._hover_widget is not widget and self._committed_widget is not widget:
            return []
        try:
            inspection = inspect_widget(widget, self._theme_manager)
        except Exception:
            return []
        if not inspection.regions:
            return []
        origin = widget.mapTo(overlay.parentWidget(), QPoint(0, 0))
        out = []
        for region in inspection.regions:
            if region.rect is None:
                continue
            out.append((region.id, region.rect.translated(origin)))
        return out

    def _clear_active_overlay(self) -> None:
        overlay = self._active_overlay
        self._active_overlay = None
        if overlay is None:
            return
        try:
            overlay.clear_target()
            overlay.hide()
        except RuntimeError:
            pass

    def _label_for(self, widget: QWidget) -> str:
        label = type(widget).__name__
        object_name = widget.objectName()
        if object_name:
            label = f"{label}#{object_name}"
        return label

    def _is_inspector_widget(self, widget: QWidget) -> bool:
        current: QWidget | None = widget
        while current is not None:
            if bool(current.property("_ui_inspector_owned")):
                return True
            current = current.parentWidget()
        return False

    def _overlay_for(self, window: QWidget) -> InspectorOverlay:
        overlay = self._overlays.get(window)
        if overlay is None:
            overlay = InspectorOverlay(window)
            self._overlays[window] = overlay
            window.installEventFilter(self)
        overlay.setGeometry(window.rect())
        overlay.raise_()
        return overlay

    def _sync_overlay_for(self, widget: QWidget) -> None:
        overlay = self._overlays.get(widget)
        if overlay is None:
            return
        try:
            overlay.setGeometry(widget.rect())
            overlay.raise_()
        except RuntimeError:
            pass

    def _hide_overlays(self) -> None:
        for overlay in self._overlays.values():
            try:
                overlay.hide()
            except RuntimeError:
                pass
        self._active_overlay = None


def _event_global_pos(event) -> QPoint:
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def _map_widget_rect(widget: QWidget, target_parent: QWidget):
    top_left = widget.mapTo(target_parent, QPoint(0, 0))
    return widget.rect().translated(top_left)


def _resolve_meaningful_widget(widget: QWidget | None) -> QWidget | None:
    current = widget
    while current is not None:
        name = current.objectName()
        if not name.startswith("qt_"):
            return current
        parent = current.parentWidget()
        if parent is None:
            return current
        current = parent
    return widget
