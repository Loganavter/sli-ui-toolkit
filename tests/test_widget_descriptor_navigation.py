from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.managers.navigation_descriptor import register_navigation
from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
from sli_ui_toolkit.ui.widget_descriptor import (
    WidgetDescriptor,
    WidgetRegistry,
    widget_descriptor,
)


class _StubSection:
    def owns(self, widget):
        return False

    def navigate(self, key, widget):
        return False

    def focus_first(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason):
        return False

    def focus_last(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason):
        return False


@pytest.fixture(autouse=True)
def _reset_navigation_manager():
    NavigationManager._instance = None
    yield
    if NavigationManager._instance is not None:
        NavigationManager._instance._uninstall_event_filter()
    NavigationManager._instance = None


def test_register_navigation_returns_false_when_nothing_set(qapp):
    widget = QWidget()
    assert register_navigation(widget) is False
    assert NavigationManager.get_instance()._sections == []


def test_register_navigation_uses_class_level_descriptor(qapp):
    section = _StubSection()

    @widget_descriptor(WidgetDescriptor(family="test.class-level", navigation=section))
    class ClassLevelWidget(QWidget):
        pass

    try:
        widget = ClassLevelWidget()
        assert register_navigation(widget) is True
        assert (widget, section) in NavigationManager.get_instance()._sections
    finally:
        WidgetRegistry.get_instance().unregister("test.class-level")


def test_register_navigation_instance_level_overrides_class_level(qapp):
    class_section = _StubSection()
    instance_section = _StubSection()

    @widget_descriptor(WidgetDescriptor(family="test.instance-override", navigation=class_section))
    class OverridableWidget(QWidget):
        pass

    try:
        widget = OverridableWidget()
        widget.widget_descriptor = WidgetDescriptor(
            family="test.instance-override", navigation=instance_section
        )
        assert register_navigation(widget) is True
        registered = dict(NavigationManager.get_instance()._sections)
        assert registered[widget] is instance_section
    finally:
        WidgetRegistry.get_instance().unregister("test.instance-override")


def test_register_navigation_falls_back_to_instance_attribute(qapp):
    section = _StubSection()
    widget = QWidget()
    widget.widget_descriptor = WidgetDescriptor(family="test.instance-only", navigation=section)
    assert register_navigation(widget) is True
    assert (widget, section) in NavigationManager.get_instance()._sections


def test_register_navigation_is_idempotent(qapp):
    section = _StubSection()
    widget = QWidget()
    widget.widget_descriptor = WidgetDescriptor(family="test.idempotent", navigation=section)
    assert register_navigation(widget) is True
    assert register_navigation(widget) is True
    assert NavigationManager.get_instance()._sections.count((widget, section)) == 1
