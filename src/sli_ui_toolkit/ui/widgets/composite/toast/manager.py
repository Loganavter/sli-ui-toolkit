"""Toast family - progress bar, notification, and the stacking manager.

Folder split (the buttons/ folder is the model): one module per widget
class - ``progress_bar.py`` (painted track), ``notification.py``
(message/actions/progress layout + geometry), ``manager.py`` (id
registry, anchoring, stacking).
"""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer
from PySide6.QtWidgets import QWidget

from .notification import ToastAction, ToastNotification, _PROGRESS_UNSET


class ToastManager(QObject):
    def __init__(self, parent_window, image_label=None):
        host_parent = parent_window
        if host_parent is None and image_label is not None:
            try:
                host_parent = image_label.window()
            except RuntimeError:
                host_parent = None
        if host_parent is None:
            raise ValueError("ToastManager requires an in-window parent widget")
        super().__init__(host_parent)
        self.parent_window = host_parent
        self.image_label = image_label
        self._next_id = 1
        self._toasts: dict[int, ToastNotification] = {}
        self.spacing = 10

        if self.parent_window is not None:
            self.parent_window.installEventFilter(self)
        if self.image_label is not None:
            self.image_label.installEventFilter(self)

    def set_anchor(self, image_label) -> None:
        """Repoint the anchor widget used for toast placement/sizing.

        Lets one shared ToastManager track whichever tab/widget is
        currently active instead of being permanently anchored to the
        widget it was constructed with.
        """
        if image_label is self.image_label:
            return
        if self.image_label is not None:
            try:
                self.image_label.removeEventFilter(self)
            except RuntimeError:
                pass
        self.image_label = image_label
        if self.image_label is not None:
            self.image_label.installEventFilter(self)
        self._position_toasts()

    def show_toast(
        self,
        content,
        *,
        duration: int = 3000,
        actions: Iterable[ToastAction | QWidget | dict | tuple] | None = None,
        progress: int | None = None,
        success: bool = False,
    ) -> int:
        toast_id = self._next_id
        self._next_id += 1

        toast = ToastNotification(self.parent_window)
        toast.setProperty("toastSuccess", bool(success))
        self._toasts[toast_id] = toast
        toast.destroyed.connect(lambda: self._toasts.pop(toast_id, None))
        toast.show_message(
            content,
            max_width=self._toast_max_width(),
            duration=duration,
            actions=actions,
            progress=progress,
        )
        self._position_toasts()
        toast.show()
        toast.raise_()
        QTimer.singleShot(0, self._position_toasts)
        return toast_id

    def update_toast(
        self,
        toast_id: int,
        content=None,
        *,
        success: bool,
        duration: int = 3000,
        actions: Iterable[ToastAction | QWidget | dict | tuple] | None = None,
        progress: Any = _PROGRESS_UNSET,
    ) -> None:
        toast = self._toasts.get(toast_id)
        if toast is None:
            return
        toast.setProperty("toastSuccess", bool(success))
        toast.update_message(
            content,
            max_width=self._toast_max_width(),
            success=success,
            duration=duration,
            actions=actions,
            progress=progress,
        )
        self._position_toasts()
        toast.show()
        toast.raise_()
        QTimer.singleShot(0, self._position_toasts)

    def close_toast(self, toast_id: int) -> None:
        toast = self._toasts.pop(toast_id, None)
        if toast is None:
            return
        toast.hide_and_close()

    def _toast_max_width(self) -> int:
        if self.image_label is not None:
            try:
                return max(260, int(self.image_label.width() * 0.42))
            except Exception:
                pass
        if self.parent_window is not None:
            try:
                return max(260, int(self.parent_window.width() * 0.35))
            except Exception:
                pass
        return 360

    def _position_toasts(self) -> None:
        if self.parent_window is None:
            return
        try:
            anchor_point = QPoint(0, 0)
            if self.image_label is not None:
                anchor_point = self.image_label.mapTo(self.parent_window, QPoint(0, 0))

            at_x = anchor_point.x() + self.spacing
            at_y = anchor_point.y() + self.spacing

            for toast in list(self._toasts.values()):
                if not toast.isVisible():
                    continue
                toast.setGeometry(QRect(at_x, at_y, toast.width(), toast.height()))
                toast.raise_()
                at_y += toast.height() + self.spacing
        except Exception:
            pass

    def _position_toast(self, toast: ToastNotification) -> None:
        self._position_toasts()

    def eventFilter(self, watched, event):
        if watched in (self.parent_window, self.image_label) and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
            QEvent.Type.LayoutRequest,
        ):
            QTimer.singleShot(0, self._position_toasts)
        return False
