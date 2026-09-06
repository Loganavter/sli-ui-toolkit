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


def test_hover_coordinator_skips_deleted_widgets(qapp):
    """Deleted hover buttons must not crash clear_descendants / reconcile."""
    import shiboken6

    from sli_ui_toolkit.widgets import Button

    parent = QWidget()
    parent.resize(200, 100)
    parent.show()
    button = Button(text="card", parent=parent)
    button.show()
    qapp.processEvents()

    coordinator = hover_coordinator()
    assert button in coordinator._widgets

    # Immediate C++ teardown (same end-state as deferred delete after events).
    button.setParent(None)
    shiboken6.delete(button)
    assert not shiboken6.isValid(button)

    # Must not raise RuntimeError / shiboken "already deleted".
    coordinator.clear_descendants(parent)
    coordinator.reconcile()
    coordinator.clear_all()

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


def test_button_set_hover_active_lights_region_without_position(qapp, monkeypatch):
    """setHoverActive(True) must activate hover (HoverCoordinator contract).

    Regression: only the False branch existed, so coordinator-driven
    activation (widget slid under a stationary cursor, flyout opened under
    it) silently never lit — e.g. +/- buttons in virtualized lists.
    """
    from PySide6.QtCore import QPoint

    from sli_ui_toolkit.ui.widgets.buttons import events as button_events
    from sli_ui_toolkit.widgets import Button

    button = Button(text="card")
    button.resize(120, 36)
    button.show()
    qapp.processEvents()

    center = button.mapToGlobal(button.rect().center())

    class _CursorAtButton:
        @staticmethod
        def pos() -> QPoint:
            return center

    monkeypatch.setattr(button_events, "QCursor", _CursorAtButton)

    button.setHoverActive(False)
    assert button._hovered_region is None
    button.setHoverActive(True)
    assert button._hovered_region is not None
    assert button._hovered_region in {region.id for region in button._regions}

    # Idempotent while lit: repeated True calls keep state, no crash.
    button.setHoverActive(True)
    assert button._hovered_region is not None

    button.setHoverActive(False)
    assert button._hovered_region is None

    button.deleteLater()
