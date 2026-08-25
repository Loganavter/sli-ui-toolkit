from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
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


def test_register_navigation_returns_false_when_nothing_set(qapp, navigation_manager_reset):
    widget = QWidget()
    assert register_navigation(widget) is False
    assert NavigationManager.get_instance()._sections == []


def test_register_navigation_uses_class_level_descriptor(qapp, navigation_manager_reset):
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
        NavigationManager.get_instance().unregister(widget)


def test_register_navigation_instance_level_overrides_class_level(qapp, navigation_manager_reset):
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
        NavigationManager.get_instance().unregister(widget)


def test_register_navigation_falls_back_to_instance_attribute(qapp, navigation_manager_reset):
    section = _StubSection()
    widget = QWidget()
    widget.widget_descriptor = WidgetDescriptor(family="test.instance-only", navigation=section)
    assert register_navigation(widget) is True
    assert (widget, section) in NavigationManager.get_instance()._sections
    NavigationManager.get_instance().unregister(widget)


def test_register_navigation_is_idempotent(qapp, navigation_manager_reset):
    section = _StubSection()
    widget = QWidget()
    widget.widget_descriptor = WidgetDescriptor(family="test.idempotent", navigation=section)
    assert register_navigation(widget) is True
    assert register_navigation(widget) is True
    assert NavigationManager.get_instance()._sections.count((widget, section)) == 1
    NavigationManager.get_instance().unregister(widget)
