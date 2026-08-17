"""SimpleOptionsFlyout is a generic scrollable list: set_rows accepts any widgets."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import SimpleOptionsFlyout


def test_set_rows_installs_arbitrary_widgets(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    rows = [Button("One"), Button("Two"), Button("Three")]
    flyout.set_rows(rows)

    assert flyout.rows() == tuple(rows)
    assert flyout.row_widget(0) is rows[0]
    assert flyout.row_widget(2) is rows[2]
    assert flyout.row_widget(3) is None
    # Rows are installed into the flyout's list container.
    assert rows[0].parentWidget() is flyout._rows_container


def test_set_rows_wires_clicked_to_item_chosen(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    chosen: list[int] = []
    flyout.item_chosen.connect(chosen.append)

    rows = [Button("A"), Button("B"), Button("C")]
    flyout.set_rows(rows)
    rows[1].click()
    assert chosen == [1]


def test_set_rows_sizes_panel_to_row_hints(qtbot):
    from PySide6.QtCore import QSize

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)

    class _Row(QWidget):
        def __init__(self, w: int, h: int):
            super().__init__()
            self._w, self._h = w, h

        def sizeHint(self):
            return QSize(self._w, self._h)

    separator = _Row(60, 9)
    row = _Row(180, 32)
    flyout.set_rows([separator, row])

    margins = flyout.content_layout.contentsMargins()
    spacing = flyout._rows_layout.spacing()
    expected_h = 9 + 32 + spacing + margins.top() + margins.bottom()
    assert flyout.container.height() == expected_h
    # Width follows the widest row (shadow halo adds MARGIN on each side).
    assert flyout.container.width() == 180 + margins.left() + margins.right()


def test_populate_after_set_rows_replaces_content(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)

    flyout.set_rows([Button("X")])
    flyout.populate(["RGB", "SSIM"], current_index=0)
    assert len(flyout.rows()) == 2
    assert flyout.rows()[0].label.text() == "RGB"
    assert flyout.rows()[1].label.text() == "SSIM"


def test_set_list_padding_controls_inner_inset(qtbot):
    from PySide6.QtCore import QSize

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)

    class _Row(QWidget):
        def sizeHint(self):
            return QSize(120, 32)

    flyout.set_rows([_Row()])
    margins_before = flyout.content_layout.contentsMargins()
    assert margins_before.top() == 2

    flyout.set_list_padding(6)
    margins = flyout.content_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (6, 6, 6, 6)
    # Panel grew by 8px total (4 extra top + 4 extra bottom) vs the 2px inset.
    assert flyout.container.height() == 32 + 12

    flyout.set_list_padding((8, 4, 8, 4))
    m2 = flyout.content_layout.contentsMargins()
    assert (m2.left(), m2.top(), m2.right(), m2.bottom()) == (8, 4, 8, 4)
    assert flyout.container.height() == 32 + 8
