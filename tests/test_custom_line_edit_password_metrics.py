"""Masked fields must measure what they PAINT.

In password mode the widget draws ``"\\u2022" * len(text)``; a bullet's advance
differs from the real characters', so any geometry computed on the model text
puts the caret and the selection highlight beside the dots. Measured in the
live app on 2026-10-25: the API-key field showed the selection drawn to the
right of the bullets, offset by exactly the width difference.

The test paints the selection into a transparent pixmap and compares the
highlight's right edge with the two candidate metrics.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPixmap

from sli_ui_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit

WIDTH, HEIGHT = 400, 30


def _right_edge_of_paint(line_edit: CustomLineEdit, paint) -> int:
    pixmap = QPixmap(WIDTH, HEIGHT)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        paint(painter, QRect(0, 0, WIDTH, HEIGHT))
    finally:
        painter.end()
    image = pixmap.toImage()
    right = -1
    for x in range(WIDTH):
        for y in range(HEIGHT):
            if image.pixelColor(x, y).alpha() > 0:
                right = x
                break
    return right


def _masked_field(qapp, *, selection):
    field = CustomLineEdit()
    field.setText("MMMMMMMMMM")
    field.setEchoMode(field.EchoMode.Password)
    field._selection_bounds = lambda: selection  # type: ignore[method-assign]
    field._text_start_x = lambda rect, for_width=None: 0.0  # type: ignore[method-assign]
    field.hasFocus = lambda: True  # type: ignore[method-assign]
    return field


@pytest.fixture
def selected_field(qapp):
    return _masked_field(qapp, selection=(0, 10))


@pytest.fixture
def unselected_field(qapp):
    return _masked_field(qapp, selection=None)


def test_password_selection_highlight_matches_the_painted_bullets(selected_field):
    masked_field = selected_field
    fm = masked_field.fontMetrics()
    bullet_width = fm.horizontalAdvance("\u2022" * len(masked_field.text()))
    text_width = fm.horizontalAdvance(masked_field.text())
    assert abs(bullet_width - text_width) > 3, "pick glyphs with a different advance"

    right = _right_edge_of_paint(masked_field, masked_field._paint_selection)

    assert abs(right - bullet_width) <= 2, (
        f"highlight ends at {right}px, the painted bullets end at {bullet_width}px"
    )
    assert abs(right - text_width) > 3, (
        "the highlight is measured on the model text again — it will sit beside the dots"
    )


def test_password_caret_sits_on_the_painted_bullets(unselected_field):
    masked_field = unselected_field
    fm = masked_field.fontMetrics()
    masked_field._cursor = len(masked_field.text())
    bullet_width = fm.horizontalAdvance("\u2022" * len(masked_field.text()))
    text_width = fm.horizontalAdvance(masked_field.text())

    right = _right_edge_of_paint(masked_field, masked_field._paint_caret)

    assert abs((right + 1) - bullet_width) <= 3, (
        f"caret lands at {right}px, the painted bullets end at {bullet_width}px"
    )
    assert abs((right + 1) - text_width) > 3
