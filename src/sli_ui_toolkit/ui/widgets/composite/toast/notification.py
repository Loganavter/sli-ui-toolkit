"""Toast family - progress bar, notification, and the stacking manager.

Folder split (the buttons/ folder is the model): one module per widget
class - ``progress_bar.py`` (painted track), ``notification.py``
(message/actions/progress layout + geometry), ``manager.py`` (id
registry, anchoring, stacking).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.managers.ui_font import apply_text_color, apply_ui_font
from sli_ui_toolkit.ui.widgets.buttons import Button

from .progress_bar import ToastProgressBar


_PROGRESS_UNSET = object()


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
        self._width_floor = 0
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

        self.progress_bar = ToastProgressBar(self.progress_container)
        self.progress_bar.setRange(0, 100)
        self.progress_layout.addWidget(self.progress_bar)
        self.progress_container.hide()
        self.root_layout.addWidget(self.progress_container)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._on_theme_changed)
        self._apply_message_typography()
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
        self._apply_message_typography()
        self._repolish_surface_widgets()
        self.progress_bar.update()
        self.adjustSize()

    def _apply_message_typography(self) -> None:
        apply_ui_font(self.message_label)
        apply_text_color(
            self.message_label, self.theme_manager.get_color("toast.text")
        )

    def _repolish_surface_widgets(self):
        widgets = (self, self.content_widget, self.progress_container)
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
        self._width_floor = 0
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
        progress: Any = _PROGRESS_UNSET,
    ):
        del success  # reserved for toastSuccess property on the manager side
        if actions is not None:
            self._set_actions(actions)
        self._apply_content_layout_state()
        if content is not None:
            self._set_content(content, max_width)
        else:
            self._fit_to_content(max_width)
        if progress is not _PROGRESS_UNSET:
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

    def _apply_fixed_width(self, desired_toast_width: int, max_width: int) -> int:
        """Grow-only width so shorter success labels do not shrink the toast."""
        safe_max_width = max(180, int(max_width))
        width = max(180, min(safe_max_width, int(desired_toast_width)))
        width = max(width, self._width_floor)
        self._width_floor = width
        return width

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
        desired_toast_width = self._apply_fixed_width(desired_toast_width, max_width)
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
        content_margins = self.main_layout.contentsMargins()
        progress_margins = self.progress_layout.contentsMargins()
        content_width = (
            self._custom_content.sizeHint().width()
            if self._custom_content is not None
            else self.message_label.sizeHint().width()
        )
        actions_width = self.action_row.sizeHint().width() if self.action_row.isVisible() else 0
        desired_toast_width = max(
            180,
            content_width + content_margins.left() + content_margins.right(),
            actions_width + content_margins.left() + content_margins.right(),
            content_width + progress_margins.left() + progress_margins.right(),
        )
        desired_toast_width = self._apply_fixed_width(desired_toast_width, max_width)
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
        painter.setBrush(QBrush(self.theme_manager.get_color("surface.background")))
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


ToastNotification.inspect_spec = InspectSpec(  # type: ignore[attr-defined]

    family="ToastNotification",
    state=(
        SpecField("width_floor", "_width_floor", private=True),
        SpecField("visible", "isVisible"),
    ),
    token_family=(
        "surface.background",
        "toast.border",
        "toast.text",
        "toast.progress.background",
        "toast.progress.fill",
    ),
    docs='docs/user/FEEDBACK_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

ToastNotification.widget_descriptor = WidgetDescriptor(
    family=ToastNotification.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(ToastNotification.inspect_spec, 'config', ()),
        state=ToastNotification.inspect_spec.state,
        token_family=getattr(ToastNotification.inspect_spec, 'token_family', ()),
        regions=getattr(ToastNotification.inspect_spec, 'regions', False),
        layers=getattr(ToastNotification.inspect_spec, 'layers', False),
        docs=getattr(ToastNotification.inspect_spec, 'docs', ''),
        preview_seed=getattr(ToastNotification.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(ToastNotification.inspect_spec, 'apply_config_refresh', None),
    ),
)