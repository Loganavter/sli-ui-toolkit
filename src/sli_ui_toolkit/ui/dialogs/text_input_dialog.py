"""Painted text-input dialog — the toolkit replacement for ``QInputDialog.getText``.

The field is ``CustomLineEdit`` (painter pipeline, submit preset on), the
prompt is a ``Text``, and the buttons are ``DialogActionBar``'s. ``get_text``
keeps ``QInputDialog.getText``'s ``(text, ok)`` shape so a host swaps the
import and deletes its own copy in one move.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QValidator
from PySide6.QtWidgets import QDialog, QVBoxLayout

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.dialogs.action_bar import DialogActionBar
from sli_ui_toolkit.ui.dialogs.dialog_helpers import BaseDialog, auto_size_dialog
from sli_ui_toolkit.ui.widgets.atomic import CustomLineEdit
from sli_ui_toolkit.ui.widgets.text import Text


class TextInputDialog(BaseDialog):
    """Single-line text prompt; Enter accepts, Escape cancels."""

    def __init__(
        self,
        parent=None,
        title: str = "",
        prompt: str = "",
        text: str = "",
        *,
        ok_text: str | None = None,
        cancel_text: str | None = None,
        placeholder: str | None = None,
        validator: QValidator | None = None,
    ):
        super().__init__(parent, title=title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        self.prompt = Text(prompt, mode="plain", word_wrap=True, selectable=True, parent=self)
        layout.addWidget(self.prompt)

        self.field = CustomLineEdit(self, submit_preset=True)
        self.field.setText(text)
        if text:
            self.field.selectAll()
        if placeholder is not None:
            self.field.setPlaceholderText(placeholder)
        if validator is not None:
            self.field.setValidator(validator)
        layout.addWidget(self.field)

        self.action_bar = DialogActionBar(
            self,
            primary_text=ok_text or "OK",
            secondary_text=cancel_text if cancel_text is not None else "Cancel",
        )
        layout.addWidget(self.action_bar)

        # The field consumes Return/Escape itself (CustomLineEdit accepts both),
        # so both paths are wired explicitly: Enter accepts (validator gate),
        # Escape cancels (event filter below).
        self.field.returnPressed.connect(self._try_accept)
        self.field.installEventFilter(self)
        self.action_bar.accepted.connect(self._try_accept)
        self.action_bar.rejected.connect(self.reject)

        self.field.setFocus()
        auto_size_dialog(self, min_width=360)

    def _read_surface_color(self) -> None:
        """Paint the surface from ``dialog.background`` (the dialog's own token)."""
        try:
            color = QColor(ThemeManager.get_instance().get_color("dialog.background"))
        except Exception:
            color = QColor(self.palette().window().color())
        self._surface_color = color

    def _try_accept(self) -> None:
        """Accept only an acceptable value; an invalid one keeps the dialog open."""
        if not self.field.hasAcceptableInput():
            return
        self.accept()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if (
            obj is self.field
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self.reject()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Escape cancels even when focus sits outside the field."""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    @classmethod
    def get_text(
        cls,
        parent,
        title: str,
        prompt: str,
        text: str = "",
        *,
        ok_text: str | None = None,
        cancel_text: str | None = None,
        placeholder: str | None = None,
        validator: QValidator | None = None,
    ) -> tuple[str, bool]:
        """Run the prompt modally and return ``(text, ok)``.

        The text is the edited value on accept, ``("", False)`` on cancel —
        the same contract as ``QInputDialog.getText``.
        """
        dialog = cls(
            parent,
            title,
            prompt,
            text,
            ok_text=ok_text,
            cancel_text=cancel_text,
            placeholder=placeholder,
            validator=validator,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.field.text(), True
        return "", False
