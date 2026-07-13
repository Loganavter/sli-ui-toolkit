from __future__ import annotations

import dataclasses

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainterPath

from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    ButtonSpec,
    InstancesCounterButton,
    ShapeSpec,
    VerticalSplit,
)
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState


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
                    ButtonRegion(id="top", icon="add"),
                    ButtonRegion(id="bottom", icon="remove"),
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


def test_button_spec_click_behavior_dispatches_action(qtbot):
    callbacks: list[tuple[str, object]] = []
    button = _show(
        Button.from_spec(
            ButtonSpec(
                regions=(
                    ButtonRegion(
                        id="apply",
                        text="Apply",
                        action="settings.apply",
                        action_data={"source": "button"},
                        action_callback=lambda action, data: callbacks.append((action, data)),
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


def test_button_regions_kwarg_dispatches_action(qtbot):
    """Action dispatch must not be exclusive to the spec= construction path.

    ButtonRegion carries its own action/action_data/action_callback fields
    (regions.py) precisely so Button(regions=[...]) — the path most callers
    use — gets the same actionTriggered dispatch as Button.from_spec(...),
    instead of it silently no-op'ing the way it used to when RegionSpec was
    the only place these fields lived.
    """
    callbacks: list[tuple[str, object]] = []
    button = _show(
        Button(
            regions=[
                ButtonRegion(
                    id="apply",
                    text="Apply",
                    action="settings.apply",
                    action_data={"source": "button"},
                    action_callback=lambda action, data: callbacks.append((action, data)),
                ),
            ],
            size=(80, 32),
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


def test_button_region_round_trip_preserves_all_fields(qtbot):
    """ButtonRegion is the single schema for region config (see
    docs/dev/BUTTON_REGION_ARCHITECTURE.md) — Button(regions=[...]) stores
    the objects passed in directly, with no intermediate spec conversion to
    drop fields in. This test used to guard a hand-written field-by-field
    RegionSpec<->ButtonRegion conversion (that's how per-region `corner_radii`
    went dead for months: added to ButtonRegion, never added to the
    conversion). That conversion no longer exists, so this is now a cheap
    identity smoke test — kept so a future reintroduction of a second schema
    would have to break it deliberately.
    """
    original = ButtonRegion(
        id="probe",
        weight=2.5,
        icon="add",
        text="hi",
        rows=None,
        toggle=True,
        long_press=True,
        long_press_ms=999,
        menu=[("a", 1)],
        action="settings.apply",
        action_data={"source": "probe"},
        action_callback=lambda action, data: None,
        badge=3,
        variant="surface",
        custom_bg_color=QColor(1, 2, 3),
        override_bg_color=QColor(4, 5, 6),
        override_border_color=QColor(7, 8, 9),
        show_underline=True,
        underline_color=QColor(10, 11, 12),
        underline_thickness=2.0,
        icon_size_px=17,
        show_strike_through=True,
        enabled=True,
        cursor=None,
        rect_fn=None,
        path_fn=None,
        z_index=5,
        corner_radii=(1, 2, 3, 4),
        group=None,
    )

    button = Button(regions=[original], size=(60, 40))
    qtbot.addWidget(button)
    (round_tripped,) = button.regions()

    for f in dataclasses.fields(ButtonRegion):
        original_value = getattr(original, f.name)
        round_tripped_value = getattr(round_tripped, f.name)
        assert round_tripped_value == original_value, (
            f"ButtonRegion.{f.name} was dropped: expected {original_value!r}, "
            f"got {round_tripped_value!r}."
        )


def test_button_set_checked_updates_main_region_state():
    button = Button(text="Toggle", toggle=True)

    button.setChecked(True, emit=False)
    assert button.isChecked() is True
    assert ButtonState.CHECKED in button.region_states("_main")

    button.setChecked(False, emit=False)
    assert button.isChecked() is False
    assert ButtonState.CHECKED not in button.region_states("_main")
