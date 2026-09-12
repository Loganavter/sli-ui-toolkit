"""BaseFlyout content-builder API — label/row/radio-row helpers.

Pure construction over ``self.content_layout``; no state beyond the layout
the facade already owns.
"""

from __future__ import annotations

from typing import Any

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic.radio import RadioButton, RadioButtonGroup
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label


class _FlyoutBuilderApi:
    """Mixin: add_section / add_row / add_radio_row content builders."""

    # Declared here only so mypy can resolve them across the mixin split —
    # the real layout is created in BaseFlyout.__init__ (widget.py).
    content_layout: Any

    def add_section(self, text: str, *, pixel_size: int = 12) -> Label:
        """Add a section heading label."""
        label = Label(
            text,
            pixel_size=pixel_size,
            bold=True,
            color_token="dialog.text",
        )
        self.content_layout.addWidget(label)
        return label

    def add_row(
        self,
        label_text: str,
        widget: QWidget,
        *,
        label_pixel_size: int = 11,
        stretch_before_widget: bool = True,
    ) -> Label:
        """Add a labeled row (label left, widget right)."""
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        label = Label(
            label_text,
            pixel_size=label_pixel_size,
            color_token="dialog.text",
        )
        row.addWidget(label)
        if stretch_before_widget:
            row.addStretch()
        row.addWidget(widget)
        self.content_layout.addWidget(host)
        return label

    def add_radio_row(
        self,
        label_text: str,
        options: list[tuple[str, Any]],
        *,
        default: Any = None,
    ) -> tuple[Label, RadioButtonGroup, dict[Any, RadioButton]]:
        """Add a label followed by a horizontal row of RadioButtons."""
        label = Label(
            label_text,
            pixel_size=11,
            color_token="dialog.text",
        )
        self.content_layout.addWidget(label)

        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        group = RadioButtonGroup()
        radios: dict[Any, RadioButton] = {}
        for i, (text, value) in enumerate(options):
            rb = RadioButton(text)
            if (default is None and i == 0) or value == default:
                rb.setChecked(True)
            group.addButton(rb)
            row.addWidget(rb)
            radios[value] = rb
        row.addStretch()
        self.content_layout.addWidget(host)
        return label, group, radios
