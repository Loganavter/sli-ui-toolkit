from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.helpers import hover_coordinator
from sli_ui_toolkit.widgets import CheckBox, RadioButton


def test_hover_coordinator_clears_managed_descendants(qapp):
    parent = QWidget()
    radio_a = RadioButton("A", parent)
    radio_b = RadioButton("B", parent)

    calls: list[tuple[object, bool]] = []
    radio_a.setHoverActive = lambda active: calls.append((radio_a, bool(active)))
    radio_b.setHoverActive = lambda active: calls.append((radio_b, bool(active)))

    hover_coordinator().clear_descendants(parent)

    assert (radio_a, False) in calls
    assert (radio_b, False) in calls

    parent.deleteLater()


def test_radio_hover_hit_test_ignores_empty_widget_area(qapp):
    radio = RadioButton("Option")
    radio.resize(220, radio.sizeHint().height())

    assert radio.hoverHitTest(QPointF(4, radio.height() / 2))
    assert not radio.hoverHitTest(QPointF(radio.width() - 2, radio.height() / 2))

    radio.deleteLater()


def test_checkbox_hover_hit_test_ignores_empty_widget_area(qapp):
    checkbox = CheckBox("Option")
    checkbox.resize(220, checkbox.sizeHint().height())

    assert checkbox.hoverHitTest(QPointF(4, checkbox.height() / 2))
    assert not checkbox.hoverHitTest(QPointF(checkbox.width() - 2, checkbox.height() / 2))

    checkbox.deleteLater()
