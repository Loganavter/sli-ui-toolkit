"""A drag on the slider must announce itself: pressed → moved → released.

The widget draws its own groove and thumb and handles the mouse itself. It used to do that WITHOUT the base class's
signals (`sliderPressed`/`sliderMoved`/`sliderReleased` were never emitted), so every consumer that connects them - the
preview's timeline scrubber is one - was silently dead: a click moved the thumb locally and nothing else happened.

Driven with real mouse events at groove coordinates, the same way a user presses.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.widgets.atomic.slider import Slider


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_a_drag_emits_pressed_moved_and_released():
    _app()
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(0, 1000)
    slider.setValue(0)
    slider.resize(240, 32)
    slider.show()
    QTest.qWaitForWindowExposed(slider)

    events: list[tuple[str, int | None]] = []
    slider.sliderPressed.connect(lambda: events.append(("pressed", slider.value())))
    slider.sliderMoved.connect(lambda v: events.append(("moved", int(v))))
    slider.sliderReleased.connect(lambda: events.append(("released", slider.value())))

    groove = slider._groove_rect()
    start = QPoint(int(groove.left() + groove.width() * 0.2), int(groove.center().y()))
    end = QPoint(int(groove.left() + groove.width() * 0.8), int(groove.center().y()))

    QTest.mousePress(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(slider, end, 20)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)

    names = [name for name, _ in events]
    assert "pressed" in names, f"a press announced nothing: {events}"
    assert "released" in names, f"a release announced nothing: {events}"
    assert "moved" in names, f"a drag announced no movement: {events}"
    assert names.index("pressed") < names.index("released")
    # The press lands on the groove at 20%, the drag ends at 80%: the value must follow the pointer.
    pressed_value = next(v for name, v in events if name == "pressed")
    assert 120 <= pressed_value <= 280, f"the press did not move the value to its point: {pressed_value}"
    assert slider.value() >= 700, f"the drag did not carry the value to the pointer: {slider.value()}"


def test_a_clicked_groove_is_announced_with_the_value_under_the_pointer():
    """PreviewTimeline commits on `sliderPressed`; announcing the OLD value would seek to where the thumb was."""
    _app()
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(0, 1000)
    slider.setValue(0)
    slider.resize(240, 32)
    slider.show()
    QTest.qWaitForWindowExposed(slider)

    seen: list[int] = []
    slider.sliderPressed.connect(lambda: seen.append(slider.value()))

    groove = slider._groove_rect()
    point = QPoint(int(groove.left() + groove.width() * 0.75), int(groove.center().y()))
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)

    assert seen, "a groove click announced no press"
    assert seen[0] >= 650, f"the press announced {seen[0]}, not the value under the pointer"
