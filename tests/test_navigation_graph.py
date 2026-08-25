"""Navigation graph POC — toolkit side."""

from PySide6.QtCore import Qt


def test_focus_reason_centralized(qapp):
    from sli_ui_toolkit.ui.managers.nav_graph import focus_reason
    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

    mgr = NavigationManager.get_instance()
    mgr._last_input_keyboard = False
    assert focus_reason() == Qt.FocusReason.MouseFocusReason
    mgr._last_input_keyboard = True
    assert focus_reason() == Qt.FocusReason.OtherFocusReason


def test_toolbar_rows_extra_keys(qapp, qtbot, navigation_manager_reset):
    from sli_ui_toolkit.ui.managers.nav_graph import snapshot, validate
    from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager
    from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
    from PySide6.QtWidgets import QWidget

    mgr = navigation_manager_reset
    row = QWidget()
    row.show()
    qtbot.addWidget(row)
    section = ToolbarRowsSection(lambda: [row], tag="test")
    mgr.register(row, section)
    graph = snapshot()
    violations = validate(graph)
    assert not violations
    # extra_keys must contain Left/Right
    assert Qt.Key.Key_Left in graph.nodes[0].extra_keys
    assert Qt.Key.Key_Right in graph.nodes[0].extra_keys
    mgr.unregister(row)


def test_tab_bar_enter_required(qapp):
    from sli_ui_toolkit.widgets import AdaptiveTabStrip

    strip = AdaptiveTabStrip(add_icon="a", close_icon="x")
    strip.addTab("A")
    strip.addTab("B")
    strip.setCurrentIndex(0)
    strip.resize(400, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()
    bar = strip.tab_bar
    bar._focused_index = 0
    bar._move_focus(1)
    assert bar.currentIndex() == 0
    assert bar._focused_index == 1
    bar._activate_focused()
    assert bar.currentIndex() == 1
    strip.hide()
