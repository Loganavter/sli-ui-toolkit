"""A spin box prints its value through the locale, like Qt's own QDoubleSpinBox.

A host replacing the stock widget measured a TEXT difference on every setting row: the toolkit printed `3.5` where the
stock box printed `3,5` (a Russian desktop). The formatter was `f"{value:.1f}"`, which ignores the locale entirely, and
the editor parsed with `float(text)`, which rejects the separator the user sees.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QLocale

from sli_ui_toolkit.widgets import DoubleSpinBox


@pytest.fixture(autouse=True)
def _restore_locale():
    previous = QLocale()
    yield
    QLocale.setDefault(previous)


@pytest.mark.parametrize("locale_name, expected", [("ru_RU", "3,5"), ("en_US", "3.5"), ("de_DE", "3,5")])
def test_the_text_follows_the_default_locale(qapp, locale_name, expected):
    QLocale.setDefault(QLocale(locale_name))
    box = DoubleSpinBox(single_step=0.1)
    box.setDecimals(1)
    box.setValue(3.5)
    assert box.text() == expected


def test_decimals_still_control_the_digits(qapp):
    QLocale.setDefault(QLocale("ru_RU"))
    box = DoubleSpinBox(single_step=0.1)
    box.setDecimals(2)
    box.setValue(3.5)
    assert box.text() == "3,50"
    box.setDecimals(0)
    box.setValue(3.0)
    assert box.text() == "3"


def test_editing_accepts_the_locale_separator_and_a_plain_dot(qapp):
    QLocale.setDefault(QLocale("ru_RU"))
    for typed, expected in (("3,5", 3.5), ("3.5", 3.5), ("4,2", 4.2)):
        box = DoubleSpinBox(single_step=0.1)
        box.setDecimals(1)
        box.setText(typed)
        box._on_editing_finished()
        assert box.value() == expected, typed
