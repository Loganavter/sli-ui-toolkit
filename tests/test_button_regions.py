from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QPainterPath, QWheelEvent

from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    ButtonSpec,
    ClickBehavior,
    ContentSpec,
    InstancesCounterButton,
    RegionSpec,
    ScrollBehavior,
    ShapeSpec,
    VerticalSplit,
)


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


def test_button_from_spec_emits_region_clicked(qtbot):
    button = _show(
        Button.from_spec(
            ButtonSpec(
                regions=(
                    RegionSpec(id="top", content=ContentSpec(icon="add")),
                    RegionSpec(id="bottom", content=ContentSpec(icon="remove")),
                ),
                split=VerticalSplit(),
                shape=ShapeSpec(size=(36, 36)),
            )
        ),
        qtbot,
    )
    clicked: list[str] = []
    button.regionClicked.connect(clicked.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(18, 8))
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(18, 28))

    assert clicked == ["top", "bottom"]
    assert [region.id for region in button.regions()] == ["top", "bottom"]


def test_button_spec_region_scroll_emits_value(qtbot):
    button = _show(
        Button.from_spec(
            ButtonSpec(
                regions=(
                    RegionSpec(
                        id="scroll",
                        content=ContentSpec(icon="add"),
                        behaviors=(ScrollBehavior(min_value=0, max_value=2),),
                    ),
                ),
                shape=ShapeSpec(size=(36, 36)),
            )
        ),
        qtbot,
    )
    values: list[tuple[str, int]] = []
    button.regionValueChanged.connect(lambda region_id, value: values.append((region_id, value)))

    event = QWheelEvent(
        QPointF(18, 18),
        QPointF(button.mapToGlobal(QPoint(18, 18))),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    button.wheelEvent(event)

    assert values == [("scroll", 2)]


def test_button_spec_click_behavior_dispatches_action(qtbot):
    callbacks: list[tuple[str, object]] = []
    button = _show(
        Button.from_spec(
            ButtonSpec(
                regions=(
                    RegionSpec(
                        id="apply",
                        content=ContentSpec(text="Apply"),
                        behaviors=(
                            ClickBehavior(
                                action="settings.apply",
                                data={"source": "button"},
                                callback=lambda action, data: callbacks.append((action, data)),
                            ),
                        ),
                    ),
                ),
                shape=ShapeSpec(size=(80, 32), corner_radius=2),
            )
        ),
        qtbot,
    )
    actions: list[tuple[str, object]] = []
    button.actionTriggered.connect(lambda action, data: actions.append((action, data)))

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(20, 16))

    assert callbacks == [("settings.apply", {"source": "button"})]
    assert actions == [("settings.apply", {"source": "button"})]


def _diamond_path(rect):
    path = QPainterPath()
    center = rect.center()
    radius = min(rect.width(), rect.height()) * 0.25
    path.moveTo(center.x(), center.y() - radius)
    path.lineTo(center.x() + radius, center.y())
    path.lineTo(center.x(), center.y() + radius)
    path.lineTo(center.x() - radius, center.y())
    path.closeSubpath()
    return path


def test_path_region_hit_test_uses_shape_not_bounding_rect(qtbot):
    button = _show(
        Button(
            regions=[
                ButtonRegion(
                    id="diamond",
                    icon="add",
                    rect_fn=lambda rect: rect,
                    path_fn=_diamond_path,
                ),
            ],
            size=(40, 40),
        ),
        qtbot,
    )
    clicked: list[str] = []
    button.regionClicked.connect(clicked.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))

    assert clicked == ["diamond"]


def test_path_region_z_index_wins_over_lower_region(qtbot):
    button = _show(
        Button(
            regions=[
                ButtonRegion(id="base", icon="remove", rect_fn=lambda rect: rect, z_index=0),
                ButtonRegion(
                    id="diamond",
                    icon="add",
                    rect_fn=lambda rect: rect,
                    path_fn=_diamond_path,
                    z_index=10,
                ),
            ],
            size=(40, 40),
        ),
        qtbot,
    )
    clicked: list[str] = []
    button.regionClicked.connect(clicked.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))

    assert clicked == ["diamond", "base"]
