"""text_fit Button mode: rows-aware sizeHint + grow-to-content sizing."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.atomic import Label
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow


def _path_row(host: QWidget, text: str):
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(Label("path", pixel_size=13, bold=True))
    button = Button(
        rows=[ButtonRow(text=text, size=None, ratio=1.0, marquee=True)],
        variant="surface",
        size=(0, 26),
        text_fit=True,
    )
    lay.addWidget(button)
    lay.addStretch(1)
    return button


def test_rows_size_hint_reflects_row_texts(qapp):
    long_text = "some quite long path that will not fit in a narrow column.py:123"
    btn = Button(
        rows=[ButtonRow(text=long_text, size=None, ratio=1.0, marquee=True)],
        variant="surface",
        size=(0, 26),
    )
    natural = btn.sizeHint().width()
    short = Button(
        rows=[ButtonRow(text="short.py", size=None, ratio=1.0, marquee=True)],
        variant="surface",
        size=(0, 26),
    )
    assert natural > short.sizeHint().width()


def test_text_fit_grows_up_to_text_and_compresses(qapp):
    long_text = "some quite long path that will not fit in a narrow column.py:123"
    host = QWidget()
    host.resize(800, 60)
    host.show()
    button = _path_row(host, long_text)
    qapp.processEvents()
    qapp.processEvents()
    natural = button.sizeHint().width()
    assert button.width() == natural  # enough room: sized to the text

    host.resize(200, 60)
    qapp.processEvents()
    qapp.processEvents()
    assert button.width() < natural  # compressed below the text width
    assert button.width() > 36  # but never below the small minimum

    host.resize(1200, 60)
    qapp.processEvents()
    qapp.processEvents()
    assert button.width() == natural  # and never beyond the text width
    host.deleteLater()


def test_text_fit_minimum_stays_small(qapp):
    long_text = "x" * 200
    button = Button(
        rows=[ButtonRow(text=long_text, marquee=True)],
        variant="surface",
        size=(0, 26),
        text_fit=True,
    )
    assert button.sizeHint().width() > 200
    assert button.minimumSizeHint().width() < 60


def test_text_fit_left_anchored(qapp):
    long_text = "x" * 200
    host = QWidget()
    host.resize(800, 60)
    host.show()
    button = _path_row(host, long_text)
    qapp.processEvents()
    qapp.processEvents()
    x_first = button.x()
    host.resize(1000, 60)
    qapp.processEvents()
    qapp.processEvents()
    assert button.x() == x_first  # the button stays glued to the label
    host.deleteLater()
