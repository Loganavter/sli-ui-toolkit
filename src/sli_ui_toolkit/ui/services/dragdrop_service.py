from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtWidgets import QApplication


class ToolkitDragDropService(QObject):
    """In-window drag coordinator for UnifiedFlyout rows.

    Visual ghost rendering is host-owned (Improve-ImgSLI ``DragGhostWidget`` via
    ``configure_toolkit(dragdrop_service_getter=...)``). This default service
    tracks drop targets without painting a ghost — fine for toolkit demos/tests.
    """

    _instance: "ToolkitDragDropService | None" = None

    @classmethod
    def get_instance(cls) -> "ToolkitDragDropService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_dragging = False
        self._source_data: dict | None = None
        self._source_widget = None
        self._hotspot = QPointF()
        self._current_target = None
        self._drop_targets: list[object] = []
        self._event_filter_installed = False

    def register_drop_target(self, target) -> None:
        if target not in self._drop_targets:
            self._drop_targets.append(target)

    def unregister_drop_target(self, target) -> None:
        if target in self._drop_targets:
            self._drop_targets.remove(target)
        if self._current_target is target:
            self._current_target = None

    def is_dragging(self) -> bool:
        return self._is_dragging

    def get_source_data(self):
        return dict(self._source_data) if self._source_data is not None else None

    def start_drag(self, source_widget, event) -> None:
        if self._is_dragging:
            return

        list_num = getattr(source_widget, "list_num", None)
        if list_num not in (1, 2):
            list_num = getattr(source_widget, "image_number", None)
        index = getattr(source_widget, "index", -1)
        if list_num not in (1, 2) or not isinstance(index, int) or index < 0:
            return

        indices = getattr(source_widget, "drag_indices", None)
        if callable(indices):
            try:
                resolved = list(indices())
            except Exception:
                resolved = [index]
        else:
            resolved = [index]
        if not resolved:
            resolved = [index]

        self._is_dragging = True
        self._source_widget = source_widget
        self._source_data = {
            "list_num": list_num,
            "index": index,
            "indices": resolved,
        }
        self._hotspot = event.position()

        if hasattr(source_widget, "set_dragging_state"):
            source_widget.set_dragging_state(True)
        set_batch = getattr(source_widget, "set_batch_dragging_state", None)
        if callable(set_batch):
            try:
                set_batch(True, resolved)
            except Exception:
                pass

        self._install_event_filter()

    def update_drag_position(self, event) -> None:
        if not self._is_dragging:
            return
        self._update_drag_position(event.globalPosition())

    def finish_drag(self, event) -> None:
        if not self._is_dragging:
            return

        current_pos = event.globalPosition()
        self._update_drag_position(current_pos)
        final_target = self._current_target
        payload = self._source_data or {}
        if (
            final_target is not None
            and hasattr(final_target, "can_accept_drop")
            and final_target.can_accept_drop(payload)
            and hasattr(final_target, "handle_drop")
        ):
            final_target.handle_drop(payload, current_pos)
        self._cleanup()

    def cancel_drag(self) -> None:
        if self._is_dragging:
            self._cleanup()

    def eventFilter(self, obj, event):
        if not self._is_dragging:
            return False

        event_type = event.type()
        if event_type == QEvent.Type.MouseMove:
            self._update_drag_position(event.globalPosition())
        elif event_type == QEvent.Type.MouseButtonRelease:
            self.finish_drag(event)
        elif event_type in (QEvent.Type.ApplicationDeactivate, QEvent.Type.WindowDeactivate):
            self.cancel_drag()
        return False

    def _update_drag_position(self, current_pos: QPointF) -> None:
        self._maybe_switch_visible_single_flyout_to_double(current_pos)

        new_target = self._target_at(current_pos)
        if self._current_target is not new_target:
            self._clear_target_indicator(self._current_target)
            self._current_target = new_target

        payload = self._source_data or {}
        if (
            self._current_target is not None
            and hasattr(self._current_target, "can_accept_drop")
            and self._current_target.can_accept_drop(payload)
        ):
            if hasattr(self._current_target, "update_drop_indicator"):
                self._current_target.update_drop_indicator(current_pos)
        else:
            self._clear_target_indicator(self._current_target)

    def _target_at(self, current_pos: QPointF):
        global_point = current_pos.toPoint()
        for target in reversed(self._drop_targets):
            try:
                if not target.isVisible():
                    continue
                contains = getattr(target, "contains_global", None)
                if contains is not None and contains(global_point):
                    return target
                local_pos = target.mapFromGlobal(global_point)
                if target.rect().contains(local_pos):
                    return target
            except RuntimeError:
                self.unregister_drop_target(target)
            except Exception:
                continue
        return None

    def _maybe_switch_visible_single_flyout_to_double(self, current_pos: QPointF) -> None:
        global_point = current_pos.toPoint()
        for target in reversed(self._drop_targets):
            try:
                mode = getattr(target, "mode", None)
                if not target.isVisible() or mode is None or mode.name == "DOUBLE":
                    continue
                if not mode.name.startswith("SINGLE"):
                    continue
                contains = getattr(target, "contains_global", None)
                inside = contains(global_point) if contains is not None else False
                if not inside and hasattr(target, "switchToDoubleMode"):
                    target.switchToDoubleMode()
            except Exception:
                continue

    def _clear_target_indicator(self, target) -> None:
        if target is not None and hasattr(target, "clear_drop_indicator"):
            try:
                target.clear_drop_indicator()
            except RuntimeError:
                pass

    def _cleanup(self) -> None:
        if self._source_widget is not None:
            if hasattr(self._source_widget, "set_dragging_state"):
                try:
                    self._source_widget.set_dragging_state(False)
                except RuntimeError:
                    pass
            set_batch = getattr(self._source_widget, "set_batch_dragging_state", None)
            if callable(set_batch):
                try:
                    set_batch(False, [])
                except Exception:
                    pass

        self._clear_target_indicator(self._current_target)
        self._is_dragging = False
        self._source_data = None
        self._source_widget = None
        self._current_target = None
        self._remove_event_filter()

    def _install_event_filter(self) -> None:
        if self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.installEventFilter(self)
        self._event_filter_installed = True

    def _remove_event_filter(self) -> None:
        if not self._event_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._event_filter_installed = False
