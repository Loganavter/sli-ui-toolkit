from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.nav_row_builder import NavRowBuilder, as_nav_row
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection


def _make_focusable(parent: QWidget, x: int, y: int = 5, w: int = 30, h: int = 20) -> QWidget:
    widget = QWidget(parent)
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.setGeometry(x, y, w, h)
    widget.show()
    return widget


def test_row_order_matches_call_order_regardless_of_unrelated_code(qapp):
    builder = NavRowBuilder(tag="test-order")
    first = QWidget()
    a = builder.row(first)
    # Unrelated work between calls must not affect ordering.
    _noop = [1, 2, 3]
    second = QWidget()
    b = builder.row(second)
    third = QWidget()
    c = builder.row(third)

    section = builder.build()
    assert section._rows_provider() == [a, b, c]


def test_extend_preserves_relative_order(qapp):
    builder = NavRowBuilder(tag="test-extend")
    a = builder.row(QWidget())
    extra1, extra2 = QWidget(), QWidget()
    builder.extend([extra1, extra2])
    b = builder.row(QWidget())

    section = builder.build()
    assert section._rows_provider() == [a, extra1, extra2, b]


def test_build_output_behaves_like_hand_built_section(qapp):
    window = QWidget()
    window.setGeometry(0, 0, 400, 200)
    layout = QVBoxLayout(window)
    window.show()
    QApplication.setActiveWindow(window)
    try:
        builder = NavRowBuilder(tag="test-behavior")
        row0 = builder.row(_make_focusable(None, x=10, y=0))
        row1 = builder.row(_make_focusable(None, x=10, y=0))
        layout.addWidget(row0)
        layout.addWidget(row1)
        row0.show()
        row1.show()
        built_section = builder.build()

        hand_section = ToolbarRowsSection(rows_provider=lambda: [row0, row1], tag="test-behavior")

        assert built_section.focus_first() == hand_section.focus_first()
        assert QApplication.focusWidget() is not None
    finally:
        window.close()
        window.deleteLater()
        QApplication.processEvents()


def test_as_nav_row_wraps_bare_widget():
    widget = QWidget()
    row = as_nav_row(widget)
    assert row is not widget
    assert row.isAncestorOf(widget)
