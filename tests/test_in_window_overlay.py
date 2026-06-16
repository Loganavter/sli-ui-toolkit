from __future__ import annotations

import pytest

import sli_ui_toolkit.widgets as public_widgets
from sli_ui_toolkit.ui.widgets import overlays
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.overlays.choice_overlay import ChoiceOverlay
from sli_ui_toolkit.widgets import DragDropOverlay, Label, OverlaySlot, TopLevelInWindowOverlay


def test_top_level_in_window_overlay_hosts_arbitrary_widget(qapp, qtbot):
    host = QWidget()
    host.resize(300, 220)
    qtbot.addWidget(host)
    host.show()

    anchor = QWidget(host)
    anchor.setGeometry(120, 100, 20, 20)
    anchor.show()
    host.show()

    overlay = TopLevelInWindowOverlay(host, anchor=anchor, default_distance=50)
    child = Label("Any")
    child.setFixedSize(40, 24)
    overlay.add_widget(child, key="label", slot=OverlaySlot.UP)
    overlay.show_overlay()

    assert overlay.parentWidget() is host
    assert overlay.geometry() == host.rect()
    assert overlay.widget_for_key("label") is child

    expected_center = QPoint(anchor.geometry().center().x(), anchor.geometry().center().y() - 50)
    actual_center = child.geometry().center()
    assert abs(actual_center.x() - expected_center.x()) <= 1
    assert abs(actual_center.y() - expected_center.y()) <= 1


def test_choice_overlay_stays_as_button_choice_helper(qapp, qtbot):
    host = QWidget()
    host.resize(300, 220)
    qtbot.addWidget(host)
    host.show()

    with pytest.warns(DeprecationWarning, match="ChoiceOverlay is deprecated"):
        overlay = ChoiceOverlay(host, button_size=48, cancel_size=24, spacing=8)
    button = overlay.add_choice("up", slot=OverlaySlot.UP, label="Up")
    overlay.show_modal()

    with qtbot.waitSignal(overlay.chosen, timeout=1000) as blocker:
        button.clicked.emit()

    assert blocker.args == ["up"]
    assert not overlay.isVisible()


def test_choice_overlay_is_not_public_widget_api():
    assert "ChoiceOverlay" not in public_widgets.__all__
    assert "ChoiceSlot" not in public_widgets.__all__


def test_legacy_overlay_package_names_warn():
    with pytest.warns(DeprecationWarning, match="ChoiceOverlay is deprecated"):
        legacy_overlay = getattr(overlays, "ChoiceOverlay")
    with pytest.warns(DeprecationWarning, match="ChoiceSlot is deprecated"):
        legacy_slot = getattr(overlays, "ChoiceSlot")

    assert legacy_overlay is ChoiceOverlay
    assert legacy_slot is OverlaySlot


def test_drag_drop_overlay_uses_top_level_overlay_base(qapp, qtbot):
    host = QWidget()
    host.resize(300, 220)
    qtbot.addWidget(host)
    host.show()

    overlay = DragDropOverlay(host)
    assert isinstance(overlay, TopLevelInWindowOverlay)

    overlay.set_overlay_state(True, host.rect(), horizontal=True, text1="A", text2="B")

    assert overlay.isVisible()
    assert overlay.geometry() == host.rect()

    overlay.set_overlay_state(False, host.rect())
    assert not overlay.isVisible()
