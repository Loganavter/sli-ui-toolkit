"""Painted message/confirm dialog — the toolkit replacement for ``QMessageBox``.

The body text is a selectable ``Text`` (painter pipeline), the buttons come
from ``DialogActionBar``, and the surface is ``BaseDialog``'s. No QSS, no
stock ``QMessageBox``, no frameless/CSD decision: a host that wants the
frameless chrome keeps applying its decorator, exactly as it does for every
other ``BaseDialog`` subclass.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.dialogs.action_bar import DialogActionBar
from sli_ui_toolkit.ui.dialogs.dialog_helpers import BaseDialog, auto_size_dialog
from sli_ui_toolkit.ui.widgets.atomic import CheckBox
from sli_ui_toolkit.ui.widgets.text import Text

#: Kinds a host may pass. The kind is semantic (a host may pick its own icon
#: from it); the toolkit itself does not paint icons into the body.
MESSAGE_KINDS = ("information", "warning", "critical", "question")


@dataclass(frozen=True)
class MessageResult:
    """Outcome of :meth:`MessageDialog.show_message`.

    ``ok`` is True when the primary action was taken (button, Enter on a
    default="ok" dialog, or any accept); ``checked`` is the state of the
    "don't show again" box, always False when no ``checkbox_text`` was given.
    """

    ok: bool
    checked: bool = False


class MessageDialog(BaseDialog):
    """Message / confirm dialog with an optional "don't show again" box."""

    def __init__(
        self,
        parent=None,
        title: str = "",
        text: str = "",
        *,
        kind: str = "information",
        checkbox_text: str | None = None,
        ok_text: str | None = None,
        cancel_text: str | None = None,
        default: str = "ok",
        destructive: bool = False,
    ):
        if kind not in MESSAGE_KINDS:
            raise ValueError(f"unknown message kind: {kind!r} (expected one of {MESSAGE_KINDS})")
        super().__init__(parent, title=title)
        self.kind = kind
        self._default = "cancel" if default == "cancel" else "ok"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        self.body = Text(text, mode="plain", word_wrap=True, selectable=True, parent=self)
        layout.addWidget(self.body)

        self.checkbox: CheckBox | None = None
        if checkbox_text:
            self.checkbox = CheckBox(checkbox_text, parent=self)
            layout.addWidget(self.checkbox)

        # None = no secondary button. A one-button row is an acknowledgement
        # ("information"), a two-button row asks a question.
        self.action_bar = DialogActionBar(
            self,
            primary_text=ok_text or "OK",
            secondary_text=cancel_text,
            destructive=destructive,
        )
        layout.addWidget(self.action_bar)

        self.action_bar.accepted.connect(self.accept)
        self.action_bar.rejected.connect(self.reject)
        # Keyboard first: Enter must reach the default button even when a
        # selectable body would otherwise take focus, and Escape keeps
        # propagating to the dialog.
        if self._default == "cancel" and self.action_bar.secondary is not None:
            self.action_bar.secondary.setFocus()
        else:
            self.action_bar.primary.setFocus()
        auto_size_dialog(self, min_width=360)

    def _read_surface_color(self) -> None:
        """Paint the surface from ``dialog.background``.

        ``BaseDialog`` reads ``surface.background``; default palettes keep the
        two equal, but a host overriding the dialog token expects its dialog
        to follow — that is the token this dialog actually names.
        """
        try:
            color = QColor(ThemeManager.get_instance().get_color("dialog.background"))
        except Exception:
            color = QColor(self.palette().window().color())
        self._surface_color = color

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Escape = cancel; Enter = the dialog's ``default`` button."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._default == "cancel" and self.action_bar.secondary is not None:
                self.action_bar.secondary.click()
            else:
                self.action_bar.primary.click()
            event.accept()
            return
        super().keyPressEvent(event)

    @classmethod
    def show_message(
        cls,
        parent,
        title: str,
        text: str,
        *,
        kind: str = "information",
        checkbox_text: str | None = None,
        ok_text: str | None = None,
        cancel_text: str | None = None,
        default: str = "ok",
        destructive: bool = False,
    ) -> MessageResult:
        """Run the dialog modally and return ``(ok, checked)``.

        ``cancel_text=None`` builds a one-button acknowledgement; pass a label
        (e.g. ``"Cancel"``) to make it a confirmation.
        """
        dialog = cls(
            parent,
            title,
            text,
            kind=kind,
            checkbox_text=checkbox_text,
            ok_text=ok_text,
            cancel_text=cancel_text,
            default=default,
            destructive=destructive,
        )
        ok = dialog.exec() == QDialog.DialogCode.Accepted
        checked = bool(dialog.checkbox.isChecked()) if dialog.checkbox is not None else False
        return MessageResult(ok=ok, checked=checked)

    @classmethod
    def information(
        cls,
        parent,
        title: str,
        text: str,
        *,
        checkbox_text: str | None = None,
        ok_text: str | None = None,
    ) -> None:
        cls.show_message(
            parent, title, text, kind="information",
            checkbox_text=checkbox_text, ok_text=ok_text,
        )

    @classmethod
    def warning(
        cls,
        parent,
        title: str,
        text: str,
        *,
        checkbox_text: str | None = None,
        ok_text: str | None = None,
    ) -> None:
        cls.show_message(
            parent, title, text, kind="warning",
            checkbox_text=checkbox_text, ok_text=ok_text,
        )

    @classmethod
    def critical(
        cls,
        parent,
        title: str,
        text: str,
        *,
        checkbox_text: str | None = None,
        ok_text: str | None = None,
    ) -> None:
        cls.show_message(
            parent, title, text, kind="critical",
            checkbox_text=checkbox_text, ok_text=ok_text,
        )

    @classmethod
    def question(
        cls,
        parent,
        title: str,
        text: str,
        *,
        checkbox_text: str | None = None,
        ok_text: str | None = None,
        cancel_text: str | None = None,
        default: str = "ok",
        destructive: bool = False,
    ) -> bool:
        """Ask a yes/no question; True when the primary action was taken."""
        result = cls.show_message(
            parent,
            title,
            text,
            kind="question",
            checkbox_text=checkbox_text,
            ok_text=ok_text,
            cancel_text=cancel_text if cancel_text is not None else "Cancel",
            default=default,
            destructive=destructive,
        )
        return result.ok
