from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QWheelEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QTextEdit, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic import CustomGroupBuilder, MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.theme import ThemeManager


class NonPropagatingTextEdit(QTextEdit):
    def wheelEvent(self, event: QWheelEvent):
        scrollbar = self.verticalScrollBar()
        is_at_top = scrollbar.value() == scrollbar.minimum()
        is_at_bottom = scrollbar.value() == scrollbar.maximum()

        scrolling_down = event.angleDelta().y() < 0
        scrolling_up = event.angleDelta().y() > 0

        if (scrolling_up and is_at_top) or (scrolling_down and is_at_bottom):
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
        self.theme_manager = ThemeManager.get_instance()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.group, group_layout, self.title = CustomGroupBuilder.create_styled_group(title)
        self.group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.group, 1)

        self.text_view = NonPropagatingTextEdit()
        self.text_view.setObjectName("previewTextEdit")
        self.text_view.setFrameShape(QFrame.Shape.NoFrame)
        self.text_view.setReadOnly(True)
        self.text_view.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.text_view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.text_view.setVerticalScrollBar(
            MinimalistScrollBar(Qt.Orientation.Vertical, self.text_view)
        )
        self.text_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

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
        self.theme_manager.theme_changed.connect(self._apply_styles)
        self._apply_styles()

    def set_title(self, text: str) -> None:
        self.title.setText(text)

    def set_action_texts(self, *, edit: str, save: str, revert: str) -> None:
        self.edit_button.setText(edit)
        self.save_button.setText(save)
        self.revert_button.setText(revert)

    def set_actions_visible(self, visible: bool) -> None:
        self.edit_button.setVisible(visible)
        self.save_button.setVisible(visible)
        self.revert_button.setVisible(visible)

    def set_edit_mode(self, enabled: bool) -> None:
        self.text_view.setReadOnly(not enabled)
        if enabled:
            self.text_view.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.text_view.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.text_view.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self.text_view.viewport().setCursor(Qt.CursorShape.ArrowCursor)

        self.edit_button.setEnabled(not enabled)
        self.save_button.setEnabled(enabled)
        self.revert_button.setEnabled(enabled)

    def _apply_styles(self) -> None:
        text = self.theme_manager.get_color("dialog.text").name()
        bg = self.theme_manager.get_color("dialog.input.background").name(QColor.NameFormat.HexArgb)
        border = self.theme_manager.get_color("input.border.thin").name(QColor.NameFormat.HexArgb)
        self.text_view.setStyleSheet(f"""
            QTextEdit#previewTextEdit {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px;
                color: {text};
            }}
            QTextEdit#previewTextEdit QAbstractScrollArea::viewport {{
                background: transparent;
                border-radius: 6px;
            }}
        """)
