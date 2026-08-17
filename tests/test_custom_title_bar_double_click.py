"""Title-bar double-click toggles maximize without raising.

Regression: ``_TitleBarDragApi.mouseDoubleClickEvent`` called a renamed
hook (``_on_toggle_maximize``) that no longer exists on ``CustomTitleBar``
— the actual toggle is ``_toggle_maximize(window)``. Every double-click on
a draggable title-bar area raised AttributeError from inside the Python
override instead of toggling the window state.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar


def _make_host(qtbot) -> tuple[QWidget, CustomTitleBar]:
    host = QWidget()
    host.resize(800, 300)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    bar = CustomTitleBar(parent=host, title="Double-click test")
    layout.addWidget(bar)
    layout.addWidget(QWidget(host), 1)
    bar.attach_window(host)
    host.show()
    qtbot.waitExposed(host)
    return host, bar


def test_double_click_toggles_maximize(qtbot, qapp):
    host, bar = _make_host(qtbot)
    try:
        center = QPoint(bar.width() // 2, bar.height() // 2)
        QTest.mouseDClick(bar, Qt.MouseButton.LeftButton, pos=center)
        assert host.isMaximized()
        QTest.mouseDClick(bar, Qt.MouseButton.LeftButton, pos=center)
        assert not host.isMaximized()
    finally:
        host.hide()
