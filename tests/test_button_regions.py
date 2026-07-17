from __future__ import annotations

import dataclasses

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

from sli_ui_toolkit.widgets import (
    Button,
    ButtonRegion,
    ButtonSpec,
    HorizontalSplit,
    InstancesCounterButton,
    ShapeSpec,
    VerticalSplit,
)
from sli_ui_toolkit.ui.widgets.buttons.layers.ripple import RippleEffect, RippleLayer
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


def test_button_vertical_regions_emit_region_clicked(qtbot):
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
        action="settings.apply",
        action_data={"source": "probe"},
        action_callback=lambda action, data: None,
        badge=3,
        variant="surface",
        custom_bg_color=QColor(1, 2, 3),
        override_bg_color=QColor(4, 5, 6),
        override_border_color=QColor(7, 8, 9),
        hover_color=QColor(20, 21, 22),
        hover_compose="stack",
        bg_locked=True,
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


def test_grouped_ripple_paints_once_over_united_rect_including_gap(qtbot):
    """Layout gap inside group= must not punch a hole in the shared ripple."""
    gap = 10.0
    button = _show(
        Button(
            regions=[
                ButtonRegion(id="left", text="L", group="card", weight=1.0),
                ButtonRegion(id="right", text="R", group="card", weight=1.0),
            ],
            split=HorizontalSplit(gap=gap),
            size=(120, 36),
        ),
        qtbot,
    )
    left = button._controller.rects["left"]
    right = button._controller.rects["right"]
    assert right.left() - left.right() == pytest.approx(gap)

    group_rect = button._controller.ripple_rect("left")
    assert group_rect is not None
    assert group_rect.left() == pytest.approx(left.left())
    assert group_rect.right() == pytest.approx(right.right())

    ripple = button._controller.ripple("left")
    assert ripple is not None
    ripple.trigger(QPointF(left.center()))

    layer = RippleLayer()
    img = QImage(button.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    ctx = button._make_context(painter)
    applies = [
        (scoped.region_id, layer.applies(scoped))
        for scoped in button.iter_regions(ctx)
    ]
    painter.end()
    assert applies == [("left", True), ("right", False)]


def test_grouped_ripple_survives_sibling_background_overpaint(qtbot):
    """Sibling BackgroundLayer must not clip the shared group wave to the owner half.

    Region-major paint (BG→Ripple→Content per region) used to let the second
    region's fill cover the united ripple. Cluster layer-major painting keeps
    the wave visible on the non-owner sibling (e.g. session-picker text half).
    """
    button = _show(
        Button(
            regions=[
                ButtonRegion(
                    id="left",
                    text="L",
                    group="card",
                    weight=1.0,
                    override_bg_color=QColor(240, 240, 240),
                ),
                ButtonRegion(
                    id="right",
                    text="R",
                    group="card",
                    weight=1.0,
                    override_bg_color=QColor(240, 240, 240),
                ),
            ],
            split=HorizontalSplit(),
            size=(120, 36),
        ),
        qtbot,
    )
    left = button._controller.rects["left"]
    right = button._controller.rects["right"]
    ripple = button._controller.ripple("left")
    assert ripple is not None
    # Origin on the left half; wave must still tint the right half after full paint.
    ripple.trigger(QPointF(left.center()))
    # Mid-animation: progressive alpha still non-zero, radius past the seam.
    ripple._elapsed = RippleEffect.DURATION_MS // 2

    img = QImage(button.size(), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(240, 240, 240))
    painter = QPainter(img)
    button._painter.paint(button._make_context(painter))
    painter.end()

    sample = right.center().toPoint()
    pixel = img.pixelColor(sample)
    # Neutral grey bg is (240,240,240); overlay ripple darkens toward black.
    assert pixel.red() < 235 or pixel.green() < 235 or pixel.blue() < 235, (
        f"expected ripple tint on non-owner half at {sample!r}, got {pixel.name()}"
    )


def test_same_group_hover_move_keeps_hovered_without_clear(qtbot):
    """Moving the pointer between siblings in one group must not drop HOVERED.

    A clear→set pair would paint one frame with no hover (shared-capsule flicker).
    """
    button = _show(
        Button(
            regions=[
                ButtonRegion(id="left", text="L", group="card", weight=1.0),
                ButtonRegion(id="right", text="R", group="card", weight=1.0),
            ],
            split=HorizontalSplit(),
            size=(120, 36),
        ),
        qtbot,
    )
    left = button._controller.rects["left"]
    right = button._controller.rects["right"]

    qtbot.mouseMove(
        button,
        QPoint(int(left.center().x()), int(left.center().y())),
    )
    qtbot.wait(10)
    # Drive hover explicitly — HoverCoordinator may skip synthetic mouseMove.
    from PySide6.QtCore import QPointF

    button._update_hover_region(QPointF(left.center()))
    assert button._hovered_region == "left"
    assert ButtonState.HOVERED in button.region_states("left")
    assert ButtonState.HOVERED in button.region_states("right")

    cleared: list[bool] = []
    original = button._controller.set_state

    def tracking_set_state(region_id, state, active):
        if state == ButtonState.HOVERED and active is False:
            cleared.append(True)
        return original(region_id, state, active)

    button._controller.set_state = tracking_set_state  # type: ignore[method-assign]
    button._update_hover_region(QPointF(right.center()))

    assert button._hovered_region == "right"
    assert ButtonState.HOVERED in button.region_states("left")
    assert ButtonState.HOVERED in button.region_states("right")
    assert cleared == []


def test_gap_between_groups_keeps_hover_sticky(qtbot):
    """A split gap between different groups must not clear HOVERED mid-crossing.

    Classic flicker: cursor leaves region A into gap → region_at is None →
    clear all HOVERED → one paint of the idle wash → enter region B.
    """
    from PySide6.QtCore import QPointF, QRectF

    class _GappedSplit:
        gap = 4.0

        def compute(self, rect, regions):
            half = (rect.width() - self.gap) / 2.0
            left = QRectF(rect.left(), rect.top(), half, rect.height())
            right = QRectF(left.right() + self.gap, rect.top(), half, rect.height())
            return [left, right]

        def dividers(self, rects):
            return []

    button = _show(
        Button(
            regions=[
                ButtonRegion(id="plate", text="A", group="plate", weight=1.0),
                ButtonRegion(id="run", text="B", weight=1.0),
            ],
            split=_GappedSplit(),
            size=(120, 36),
        ),
        qtbot,
    )
    plate = button._controller.rects["plate"]
    run = button._controller.rects["run"]
    gap_x = plate.right() + 2.0
    gap_pos = QPointF(gap_x, plate.center().y())

    button._update_hover_region(QPointF(plate.center()))
    assert button._hovered_region == "plate"
    assert ButtonState.HOVERED in button.region_states("plate")

    # Mid-gap: still inside the widget, hit-test for a region fails.
    assert button._region_at(gap_pos) is None
    assert button.hoverHitTest(gap_pos) is True

    cleared: list[bool] = []
    original = button._controller.set_state

    def tracking_set_state(region_id, state, active):
        if state == ButtonState.HOVERED and active is False:
            cleared.append(True)
        return original(region_id, state, active)

    button._controller.set_state = tracking_set_state  # type: ignore[method-assign]
    button._update_hover_region(gap_pos)

    assert button._hovered_region == "plate"
    assert ButtonState.HOVERED in button.region_states("plate")
    assert cleared == []

    button._update_hover_region(QPointF(run.center()))
    assert button._hovered_region == "run"
    assert ButtonState.HOVERED in button.region_states("run")
    assert ButtonState.HOVERED not in button.region_states("plate")


def test_grouped_checked_mirrors_to_siblings(qtbot):
    """CHECKED on one grouped region must mirror to every sibling in the group."""
    button = _show(
        Button(
            regions=[
                ButtonRegion(id="left", text="L", group="card", toggle=True, weight=1.0),
                ButtonRegion(id="right", text="R", group="card", toggle=True, weight=1.0),
            ],
            split=HorizontalSplit(),
            size=(120, 36),
        ),
        qtbot,
    )

    button.setRegionChecked("left", True)
    assert ButtonState.CHECKED in button.region_states("left")
    assert ButtonState.CHECKED in button.region_states("right")

    button.setRegionChecked("right", False)
    assert ButtonState.CHECKED not in button.region_states("left")
    assert ButtonState.CHECKED not in button.region_states("right")


def test_grouped_checked_does_not_leak_across_groups(qtbot):
    button = _show(
        Button(
            regions=[
                ButtonRegion(id="plate", text="A", group="plate", toggle=True, weight=1.0),
                ButtonRegion(id="run", text="B", toggle=True, weight=1.0),
            ],
            split=HorizontalSplit(gap=4.0),
            size=(120, 36),
        ),
        qtbot,
    )

    button.setRegionChecked("plate", True)
    assert ButtonState.CHECKED in button.region_states("plate")
    assert ButtonState.CHECKED not in button.region_states("run")
