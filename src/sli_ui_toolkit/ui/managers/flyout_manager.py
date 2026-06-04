from typing import Optional, Protocol, Set

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

class ManagedFlyout(Protocol):
    def isVisible(self) -> bool: ...
    def hide(self) -> None: ...

class FlyoutManager(QObject):
    _instance: Optional["FlyoutManager"] = None

    def __init__(self):
        super().__init__()
        self._active_flyout: Optional[ManagedFlyout] = None
        self._registered_flyouts: Set[ManagedFlyout] = set()
        self._anchor_snapshots: dict[ManagedFlyout, tuple[tuple[QWidget, QRect], ...]] = {}
        self._pending_anchor_snapshots: Set[int] = set()
        self._event_filter_installed = False

    @classmethod
    def get_instance(cls) -> "FlyoutManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_flyout(self, flyout: ManagedFlyout):
        if flyout not in self._registered_flyouts:
            self._registered_flyouts.add(flyout)

    def unregister_flyout(self, flyout: ManagedFlyout):
        self._registered_flyouts.discard(flyout)
        self._anchor_snapshots.pop(flyout, None)
        self._pending_anchor_snapshots.discard(id(flyout))
        if self._active_flyout is flyout:
            self._active_flyout = None

    def request_show(self, flyout: ManagedFlyout) -> bool:
        if flyout not in self._registered_flyouts:
            self.register_flyout(flyout)

        self._install_event_filter()

        if self._active_flyout is flyout and flyout.isVisible():
            self._schedule_anchor_snapshot(flyout)
            return True

        for registered in list(self._registered_flyouts):
            if registered is flyout:
                continue
            try:
                if registered.isVisible():
                    registered.hide()
            except RuntimeError:
                self._registered_flyouts.discard(registered)
            except Exception:
                continue

        self._active_flyout = flyout
        self._schedule_anchor_snapshot(flyout)
        return True

    def request_hide(self, flyout: ManagedFlyout):
        self._anchor_snapshots.pop(flyout, None)
        if self._active_flyout is flyout:
            self._active_flyout = None
        if not self._any_visible():
            self._remove_event_filter()

    def close_all(self):
        for flyout in list(self._registered_flyouts):
            try:
                if flyout.isVisible():
                    flyout.hide()
            except RuntimeError:
                self._registered_flyouts.discard(flyout)
            except Exception:
                continue
        self._active_flyout = None
        self._anchor_snapshots.clear()
        self._pending_anchor_snapshots.clear()
        self._remove_event_filter()

    def is_flyout_active(self, flyout: ManagedFlyout) -> bool:
        return self._active_flyout is flyout and flyout.isVisible()

    def get_active_flyout(self) -> Optional[ManagedFlyout]:
        if self._active_flyout is not None and self._active_flyout.isVisible():
            return self._active_flyout
        return None

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type in (
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.WindowDeactivate,
        ):
            self.close_all()
            return False

        if event_type in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Hide,
            QEvent.Type.Show,
            QEvent.Type.ParentChange,
            QEvent.Type.LayoutRequest,
        ):
            self._close_flyouts_with_moved_anchors()
            return False

        if event_type == QEvent.Type.Wheel:
            if self._active_flyout is not None and self._active_flyout.isVisible():
                try:
                    global_pos = event.globalPosition().toPoint()
                except AttributeError:
                    try:
                        global_pos = event.globalPos()
                    except AttributeError:
                        global_pos = None
                inside = self._is_inside_active_flyout(obj) or (
                    global_pos is not None and self._contains_global(global_pos)
                )
                if not inside:
                    self.close_all()
            return False

        if event_type == QEvent.Type.MouseButtonPress:
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                try:
                    global_pos = event.globalPos()
                except AttributeError:
                    global_pos = None
            if global_pos is not None and not self._contains_global(global_pos):
                self.close_all()
        return False

    def _schedule_anchor_snapshot(self, flyout: ManagedFlyout) -> None:
        self._snapshot_anchor_geometry(flyout)
        key = id(flyout)
        if key in self._pending_anchor_snapshots:
            return
        self._pending_anchor_snapshots.add(key)
        QTimer.singleShot(0, lambda: self._finish_anchor_snapshot(flyout, key))

    def _finish_anchor_snapshot(self, flyout: ManagedFlyout, key: int) -> None:
        self._pending_anchor_snapshots.discard(key)
        if flyout not in self._registered_flyouts:
            return
        try:
            if flyout.isVisible():
                self._snapshot_anchor_geometry(flyout)
        except RuntimeError:
            self.unregister_flyout(flyout)

    def _snapshot_anchor_geometry(self, flyout: ManagedFlyout) -> None:
        anchors = self._anchor_widgets(flyout)
        snapshots: list[tuple[QWidget, QRect]] = []
        for anchor in anchors:
            try:
                snapshots.append((anchor, self._global_rect(anchor)))
            except RuntimeError:
                continue
        if snapshots:
            self._anchor_snapshots[flyout] = tuple(snapshots)
        else:
            self._anchor_snapshots.pop(flyout, None)

    def _close_flyouts_with_moved_anchors(self) -> None:
        for flyout, snapshots in list(self._anchor_snapshots.items()):
            try:
                if not flyout.isVisible():
                    self._anchor_snapshots.pop(flyout, None)
                    continue
                for anchor, previous_rect in snapshots:
                    if self._global_rect(anchor) != previous_rect:
                        flyout.hide()
                        break
            except RuntimeError:
                self.unregister_flyout(flyout)
            except Exception:
                continue

    def _anchor_widgets(self, flyout: ManagedFlyout) -> tuple[QWidget, ...]:
        getter = getattr(flyout, "anchor_widgets", None)
        if getter is not None:
            try:
                anchors = getter()
                return tuple(anchor for anchor in anchors if isinstance(anchor, QWidget))
            except Exception:
                return ()

        anchor = getattr(flyout, "_anchor_widget", None)
        return (anchor,) if isinstance(anchor, QWidget) else ()

    def _global_rect(self, widget: QWidget) -> QRect:
        return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())

    def _is_inside_active_flyout(self, obj) -> bool:
        flyout = self._active_flyout
        if flyout is None or not isinstance(obj, QWidget):
            return False
        try:
            widget = obj
            flyout_widget = flyout if isinstance(flyout, QWidget) else None
            if flyout_widget is None:
                return False
            while widget is not None:
                if widget is flyout_widget:
                    return True
                widget = widget.parentWidget()
        except RuntimeError:
            return False
        return False

    def _contains_global(self, global_pos) -> bool:
        for flyout in list(self._registered_flyouts):
            try:
                if not flyout.isVisible():
                    continue
                contains = getattr(flyout, "contains_global", None)
                if contains is not None and contains(global_pos):
                    return True
                anchor_contains = getattr(flyout, "anchor_contains_global", None)
                if anchor_contains is not None and anchor_contains(global_pos):
                    return True
            except RuntimeError:
                self._registered_flyouts.discard(flyout)
            except Exception:
                continue
        return False

    def _any_visible(self) -> bool:
        for flyout in list(self._registered_flyouts):
            try:
                if flyout.isVisible():
                    return True
            except RuntimeError:
                self._registered_flyouts.discard(flyout)
        return False

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
