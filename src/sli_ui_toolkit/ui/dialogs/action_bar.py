"""One row of dialog buttons, shared by the toolkit's message and input dialogs.

The row is a plain widget so a host can embed it anywhere (a dialog body, a
flyout card, an inline confirmation strip). Its buttons come from the toolkit
``Button`` pipeline — never ``QPushButton``/QSS — and the two signals are the
dialog-level answer: ``accepted`` for the primary action, ``rejected`` for the
secondary one.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import Button


class DialogActionBar(QWidget):
    """Primary(+optional secondary) button row with ``accepted``/``rejected``.

    ``primary_min_size``/``secondary_min_size`` are design px defaults that
    keep the single-row dialog layout from collapsing to a text-tight button;
    pass ``(0, 0)`` to fall back to the button's own natural minimums.
    ``secondary_text=None`` builds a one-button row (informational dialogs).
    ``destructive`` tints the primary button with the palette's error colour —
    the palette has no dedicated button-danger token, so ``progress.error``
    (the designed error colour in both themes) is the seed.
    """

    accepted = Signal()
    rejected = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        primary_text: str,
        secondary_text: str | None = None,
        primary_min_size: tuple[int, int] = (100, 36),
        secondary_min_size: tuple[int, int] = (100, 36),
        destructive: bool = False,
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addStretch(1)

        self.primary = Button(text=primary_text, variant="surface", parent=self)
        self.primary.setProperty("class", "primary")
        self.primary.setMinimumSize(*primary_min_size)
        if destructive:
            error = ThemeManager.get_instance().try_get_color("progress.error")
            if error is not None:
                self.primary.set_background_color(error)
        self.primary.clicked.connect(self.accepted)
        layout.addWidget(self.primary)

        self.secondary: Button | None = None
        if secondary_text is not None:
            secondary = Button(text=secondary_text, variant="surface", parent=self)
            secondary.setMinimumSize(*secondary_min_size)
            secondary.clicked.connect(self.rejected)
            self.secondary = secondary
            layout.addWidget(secondary)
