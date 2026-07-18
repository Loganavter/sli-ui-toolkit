"""SimpleOptionsFlyout sizes to content, not a hardcoded width floor."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import SimpleOptionsFlyout


def test_populate_sizes_to_longest_label_not_180(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    labels = ["RGB", "R", "SSIM"]
    flyout.populate(labels, current_index=0)

    longest_row = max(
        flyout._rows_layout.itemAt(i).widget().sizeHint().width()
        for i in range(len(labels))
    )
    margins = flyout.content_layout.contentsMargins()
    expected = longest_row + margins.left() + margins.right() + flyout.MARGIN * 2

    assert flyout.width() == expected
    assert flyout.width() < 180


def test_mode_picker_labels_stay_near_text_width(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    labels = ["Off", "Highlight", "Grayscale", "Edge Comparison", "SSIM Map"]
    flyout.populate(labels, current_index=0)

    edge_row = flyout._rows_layout.itemAt(3).widget()
    label_w = edge_row.label.sizeHint().width()
    # Outer widget includes shadow halo; opaque panel should stay close to the label.
    opaque = flyout.container.width()
    assert opaque <= label_w + 28  # row pad 16 + content margins 4 + slack
    assert flyout.width() < label_w * 1.6


def test_show_below_grows_for_long_label_above_anchor(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(500, 400)
    host.show()

    combo = QWidget(host)
    combo.setFixedSize(80, 28)
    combo.move(40, 40)
    combo.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    flyout.populate(["A very long interpolation mode label"], current_index=0)
    flyout.show_below(combo, exact_width_match=True)
    qtbot.wait(20)

    assert flyout.width() > 80 + flyout.MARGIN * 2
