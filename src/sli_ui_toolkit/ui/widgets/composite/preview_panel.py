from __future__ import annotations

from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic import CustomGroupBuilder
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.text_view import TextView


class NonPropagatingTextEdit(TextView):
    """Painted :class:`TextView` that consumes the wheel at its scroll edges.

    Legacy name kept for import compatibility (``sli_ui_toolkit.widgets``
    re-exports it): the body is now the painted text view, not the stock Qt
    text widget the class used to subclass. The behavior is the original
    one — at the top scrolling up or at the bottom scrolling down the event
    is accepted and NOT forwarded to the parent; anywhere else the wheel
    scrolls this view.
    """

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        bar = self.verticalScrollBar()
        at_top = bar.value() == bar.minimum()
        at_bottom = bar.value() == bar.maximum()

        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        scrolling_down = delta < 0
        scrolling_up = delta > 0

        if (scrolling_up and at_top) or (scrolling_down and at_bottom):
            event.accept()
            return

        super().wheelEvent(event)


class PreviewPanel(QWidget):
    def __init__(
        self,
        title: str,
        *,
        show_actions: bool = False,
        edit_text: str = "Edit",
        save_text: str = "Save",
        revert_text: str = "Revert",
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.group, group_layout, self.title = CustomGroupBuilder.create_styled_group(title)
        self.group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.group, 1)

        # Painted text surface (no stock Qt text widget, no QSS): read-only
        # by default, switched into edit mode through the same canvas.
        self.text_view = NonPropagatingTextEdit()
        self.text_view.setObjectName("previewTextView")

        group_layout.addWidget(self.text_view, 1)

        self.edit_button = Button(text=edit_text, variant="surface")
        self.save_button = Button(text=save_text, variant="surface")
        self.revert_button = Button(text=revert_text, variant="surface")

        self.actions_layout = QHBoxLayout()
        self.actions_layout.addWidget(self.edit_button)
        self.actions_layout.addWidget(self.save_button)
        self.actions_layout.addWidget(self.revert_button)
        group_layout.addLayout(self.actions_layout)

        self.set_actions_visible(show_actions)

    def set_title(self, text: str) -> None:
        self.title.setText(text)

    def set_text(self, text: str) -> None:
        self.text_view.set_text(text)

    def text(self) -> str:
        return self.text_view.text()

    def set_action_texts(self, *, edit: str, save: str, revert: str) -> None:
        self.edit_button.setText(edit)
        self.save_button.setText(save)
        self.revert_button.setText(revert)

    def set_actions_visible(self, visible: bool) -> None:
        self.edit_button.setVisible(visible)
        self.save_button.setVisible(visible)
        self.revert_button.setVisible(visible)

    def set_edit_mode(self, enabled: bool) -> None:
        if enabled:
            self.text_view.enter_edit_mode()
        else:
            self.text_view.exit_edit_mode()

        self.edit_button.setEnabled(not enabled)
        self.save_button.setEnabled(enabled)
        self.revert_button.setEnabled(enabled)
