"""De-brittled navigation tests — public API + reset fixture."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
def test_navigation_manager_reset_fixture_cleans_via_public_api(qapp, qtbot, navigation_manager_reset):
    mgr = navigation_manager_reset
    assert mgr._sections == []
    class _Section:
        def owns(self, w):
            return w is row
        def navigate(self, key, w):
            return False
        def focus_first(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason):
            row.setFocus(reason)
            return True
        def focus_last(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason):
            return False
    row = QWidget()
    row.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    row.show()
    qtbot.addWidget(row)
    section = _Section()
    mgr.register(row, section)
    assert (row, section) in mgr._sections
    mgr.unregister(row)
    assert (row, section) not in mgr._sections
    assert mgr._sections == []
def test_register_is_idempotent_via_public_api(qapp, qtbot, navigation_manager_reset):
    mgr = navigation_manager_reset
    class _Section:
        def owns(self, w):
            return False
        def navigate(self, k, w):
            return False
        def focus_first(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason):
            return False
        def focus_last(self, ref_x=None, *, reason=Qt.FocusReason.OtherFocusReason):
            return False
    owner = QWidget()
    owner.show()
    qtbot.addWidget(owner)
    sec = _Section()
    mgr.register(owner, sec)
    mgr.register(owner, sec)
    assert mgr._sections.count((owner, sec)) == 1
    mgr.unregister(owner)
    assert mgr._sections == []
def test_toolbar_rows_registers_via_descriptor_and_cleans(qapp, qtbot, navigation_manager_reset):
    from sli_ui_toolkit.ui.managers.navigation_descriptor import register_navigation
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor
    from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
    row = QWidget()
    row.setGeometry(0, 0, 200, 30)
    row.show()
    qtbot.addWidget(row)
    child = QWidget(row)
    child.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    child.setGeometry(5, 5, 30, 20)
    child.show()
    section = ToolbarRowsSection(rows_provider=lambda: [row])
    row.widget_descriptor = WidgetDescriptor(family="test.nav_reset_descriptor", navigation=section)  # type: ignore[attr-defined]
    assert register_navigation(row) is True
    assert any(o is row for o, _ in NavigationManager.get_instance()._sections)
    NavigationManager.get_instance().unregister(row)
    assert all(o is not row for o, _ in NavigationManager.get_instance()._sections)
