from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt

from sli_ui_toolkit.widgets import Button, ButtonRegion, InstancesCounterButton, VerticalSplit


def _show(widget, qtbot):
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_button_vertical_regions_emit_region_clicked(qtbot):
    button = _show(
        Button(
            regions=[
                ButtonRegion(id="top", icon="add"),
                ButtonRegion(id="bottom", icon="remove"),
            ],
            split=VerticalSplit(),
            size=(36, 36),
        ),
        qtbot,
    )
    clicked: list[str] = []
    button.regionClicked.connect(clicked.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(18, 8))
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(18, 28))

    assert clicked == ["top", "bottom"]


def test_disabled_region_does_not_emit_click(qtbot):
    button = _show(
        Button(
            regions=[
                ButtonRegion(id="top", icon="add"),
                ButtonRegion(id="bottom", icon="remove", enabled=False),
            ],
            split=VerticalSplit(),
            size=(36, 36),
        ),
        qtbot,
    )
    clicked: list[str] = []
    button.regionClicked.connect(clicked.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(18, 28))

    assert clicked == []


def test_instances_counter_button_uses_regions(qtbot):
    counter = _show(InstancesCounterButton(), qtbot)
    added: list[bool] = []
    removed: list[bool] = []
    counter.addClicked.connect(lambda: added.append(True))
    counter.removeClicked.connect(lambda: removed.append(True))

    qtbot.mouseClick(counter, Qt.MouseButton.LeftButton, pos=QPoint(18, 18))
    assert added == [True]

    counter.set_count(2)
    qtbot.mouseClick(counter, Qt.MouseButton.LeftButton, pos=QPoint(18, 28))
    assert removed == []

    counter.set_can_remove(True)
    qtbot.mouseClick(counter, Qt.MouseButton.LeftButton, pos=QPoint(18, 28))
    assert removed == [True]
