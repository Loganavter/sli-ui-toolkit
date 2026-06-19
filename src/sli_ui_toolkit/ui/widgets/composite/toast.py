from dataclasses import dataclass
from typing import Callable, Iterable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QBrush, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button

@dataclass(slots=True)
class ToastAction:
    text: str
    callback: Callable[[], None] | None = None
    dismiss: bool = True
    icon: object = None
    variant: str = "surface"

class ToastNotification(QWidget):
    _MARGINS_WITH_ACTION = (12, 10, 12, 10)
    _MARGINS_NO_ACTION = (12, 10, 12, 6)

    def __init__(self, parent=None):
        if parent is None:
            raise ValueError("ToastNotification requires an in-window parent widget")
        super().__init__(parent)

        self.setObjectName("ToastNotification")
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._custom_content: QWidget | None = None
        self._action_widgets: list[QWidget] = []
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_and_close)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.content_widget = QWidget(self)
        self.content_widget.setObjectName("ToastContentWidget")
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.main_layout = QVBoxLayout(self.content_widget)
        self.main_layout.setContentsMargins(12, 10, 12, 10)
        self.main_layout.setSpacing(8)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.main_layout.addWidget(self.message_label)

        self.action_row = QWidget(self.content_widget)
        self.action_row_layout = QHBoxLayout(self.action_row)
        self.action_row_layout.setContentsMargins(0, 0, 0, 0)
        self.action_row_layout.setSpacing(6)
        self.action_row_layout.addStretch(1)
        self.action_row.hide()
        self.main_layout.addWidget(self.action_row)
        self.root_layout.addWidget(self.content_widget)

        self.progress_container = QWidget(self)
        self.progress_container.setObjectName("ToastProgressContainer")
        self.progress_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.progress_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.progress_layout = QVBoxLayout(self.progress_container)
        self.progress_layout.setContentsMargins(12, 0, 12, 10)
        self.progress_layout.setSpacing(0)

        self.progress_bar = QProgressBar(self.progress_container)
        self.progress_bar.setObjectName("ToastProgressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_layout.addWidget(self.progress_bar)
        self.progress_container.hide()
        self.root_layout.addWidget(self.progress_container)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self._apply_surface_state()

    def _apply_content_layout_state(self):
        if self.action_row.isVisible():
            left, top, right, bottom = self._MARGINS_WITH_ACTION
            self.main_layout.setSpacing(8)
        else:
            left, top, right, bottom = self._MARGINS_NO_ACTION
            self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(left, top, right, bottom)

    def _on_theme_changed(self):
        self._repolish_surface_widgets()
        self.adjustSize()

    def _repolish_surface_widgets(self):
        widgets = (self, self.content_widget, self.progress_container, self.progress_bar)
        for widget in widgets:
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()

    def _apply_surface_state(self):
        has_progress = not self.progress_container.isHidden()
        self.content_widget.setProperty("hasProgress", has_progress)
        self.progress_container.setProperty("hasProgress", has_progress)
        self._repolish_surface_widgets()

    def show_message(
        self,
        content,
        max_width: int,
        duration: int = 3000,
        actions: Iterable[ToastAction | QWidget | dict | tuple] | None = None,
        progress: int | None = None,
    ):
        self._set_actions(actions)
        self._apply_content_layout_state()
        self._set_content(content, max_width)
        self._set_progress(progress)
        self.adjustSize()
        self.show()
        self._apply_duration(duration)

    def update_message(
        self,
        content,
        max_width: int,
        success: bool,
        duration: int = 4000,
        actions: Iterable[ToastAction | QWidget | dict | tuple] | None = None,
        progress: int | None = None,
    ):
        if actions is not None:
            self._set_actions(actions)
        self._apply_content_layout_state()
        if content is not None:
            self._set_content(content, max_width)
        else:
            self._fit_to_content(max_width)
        self._set_progress(progress)
        self.adjustSize()
        self._apply_duration(duration)

    def _set_actions(
        self,
        actions: Iterable[ToastAction | QWidget | dict | tuple] | None,
    ) -> None:
        while self.action_row_layout.count() > 1:
            item = self.action_row_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._action_widgets.clear()

        for action in actions or ():
            widget = self._build_action_widget(action)
            if widget is None:
                continue
            widget.setParent(self.action_row)
            self.action_row_layout.insertWidget(
                self.action_row_layout.count() - 1,
                widget,
                0,
                Qt.AlignmentFlag.AlignLeft,
            )
            self._action_widgets.append(widget)

        self.action_row.setVisible(bool(self._action_widgets))

    def _build_action_widget(self, action) -> QWidget | None:
        if isinstance(action, QWidget):
            return action
        if isinstance(action, ToastAction):
            spec = action
        elif isinstance(action, dict):
            spec = ToastAction(**action)
        elif isinstance(action, tuple):
            text = action[0] if len(action) > 0 else ""
            callback = action[1] if len(action) > 1 else None
            dismiss = action[2] if len(action) > 2 else True
            spec = ToastAction(str(text), callback, bool(dismiss))
        else:
            return None

        button = Button(
            spec.icon,
            text=spec.text,
            size=(0, 28),
            variant=spec.variant,
            density="compact",
            parent=self.action_row,
        )
        button.clicked.connect(
            lambda spec=spec: self._handle_action_clicked(spec.callback, spec.dismiss)
        )
        return button

    def _set_content(self, content, max_width: int):
        if isinstance(content, QWidget):
            self._set_custom_content(content, max_width)
        else:
            self._set_message_text(str(content), max_width)

    def _set_custom_content(self, widget: QWidget, max_width: int):
        if self._custom_content is not None and self._custom_content is not widget:
            self.main_layout.removeWidget(self._custom_content)
            self._custom_content.setParent(None)
            self._custom_content.deleteLater()

        self._custom_content = widget
        self.message_label.hide()
        widget.setParent(self.content_widget)
        if self.main_layout.indexOf(widget) < 0:
            self.main_layout.insertWidget(0, widget)

        safe_max_width = max(180, int(max_width))
        widget.setMaximumWidth(safe_max_width - 24)
        widget.show()
        widget.updateGeometry()
        self._fit_to_content(max_width)

    def _set_message_text(self, message: str, max_width: int):
        if self._custom_content is not None:
            self.main_layout.removeWidget(self._custom_content)
            self._custom_content.setParent(None)
            self._custom_content.deleteLater()
            self._custom_content = None
        self.message_label.show()

        safe_max_width = max(180, int(max_width))
        content_margins = self.main_layout.contentsMargins()
        progress_margins = self.progress_layout.contentsMargins()
        actions_width = self.action_row.sizeHint().width() if self.action_row.isVisible() else 0
        text_width = max(
            80,
            safe_max_width
            - content_margins.left()
            - content_margins.right()
        )
        font_metrics = QFontMetrics(self.message_label.font())
        lines = message.split("\n") if "\n" in message else [message]
        longest_line_width = max((font_metrics.horizontalAdvance(line) for line in lines), default=0)
        desired_text_width = max(80, min(text_width, longest_line_width + 4))
        desired_toast_width = min(
            safe_max_width,
            max(
                180,
                desired_text_width
                + content_margins.left()
                + content_margins.right()
                + 4,
                actions_width
                + content_margins.left()
                + content_margins.right(),
                desired_text_width
                + progress_margins.left()
                + progress_margins.right(),
            ),
        )
        final_text_width = max(
            80,
            desired_toast_width
            - content_margins.left()
            - content_margins.right()
        )

        self.setFixedWidth(desired_toast_width)
        self.content_widget.setFixedWidth(desired_toast_width)
        self.progress_container.setFixedWidth(desired_toast_width)
        self.message_label.setFixedWidth(final_text_width)
        self.message_label.setText(message)
        self.action_row.setFixedWidth(final_text_width)
        self.message_label.updateGeometry()
        self.content_widget.adjustSize()
        self.adjustSize()
        self.updateGeometry()

    def _fit_to_content(self, max_width: int):
        safe_max_width = max(180, int(max_width))
        content_margins = self.main_layout.contentsMargins()
        progress_margins = self.progress_layout.contentsMargins()
        content_width = (
            self._custom_content.sizeHint().width()
            if self._custom_content is not None
            else self.message_label.sizeHint().width()
        )
        actions_width = self.action_row.sizeHint().width() if self.action_row.isVisible() else 0
        desired_toast_width = min(
            safe_max_width,
            max(
                180,
                content_width + content_margins.left() + content_margins.right(),
                actions_width + content_margins.left() + content_margins.right(),
                content_width + progress_margins.left() + progress_margins.right(),
            ),
        )
        self.setFixedWidth(desired_toast_width)
        self.content_widget.setFixedWidth(desired_toast_width)
        self.progress_container.setFixedWidth(desired_toast_width)
        self.action_row.setFixedWidth(
            max(80, desired_toast_width - content_margins.left() - content_margins.right())
        )
        self.content_widget.adjustSize()
        self.adjustSize()
        self.updateGeometry()

    def _set_progress(self, progress: int | None):
        if progress is None:
            self.progress_container.hide()
            self._apply_surface_state()
            return

        safe_progress = max(0, min(100, int(progress)))
        self.progress_bar.setValue(safe_progress)
        self.progress_container.show()
        self._apply_surface_state()

    def _apply_duration(self, duration: int):
        self._hide_timer.stop()
        if duration > 0:
            self._hide_timer.start(duration)

    def hide_and_close(self):
        self._hide_timer.stop()
        self.hide()
        self.close()

    def _handle_action_clicked(self, callback=None, dismiss: bool = True):
        try:
            if callable(callback):
                callback()
        finally:
            if dismiss:
                self.hide_and_close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.setBrush(QBrush(self.theme_manager.get_color("toast.background")))
        painter.setPen(QPen(self.theme_manager.get_color("toast.border"), 1))
        painter.drawRoundedRect(rect, 8, 8)
        painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if self.action_row.isVisible() and self.action_row.rect().contains(
            self.action_row.mapFrom(self, event.pos())
        ):
            return super().mousePressEvent(event)
        self.hide_and_close()
        event.accept()

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
        progress: int | None = None,
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
