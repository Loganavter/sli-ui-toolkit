"""CheckBox tri-state — Qt ``QCheckBox`` semantics for generated-UI hosts.

A host's Qt compatibility layer mocked ``QCheckBox`` because the toolkit had no
tri-state. These tests pin the three calls that adapter made, against stock
``QCheckBox`` on this Qt (6.11.2) as the oracle:

* ``setTristate(True)`` makes clicks and Space cycle
  Unchecked → PartiallyChecked → Checked (that order, measured);
* a gesture/``setCheckState`` emits ``toggled(bool)`` only when the *checked
  bool* changes, then ``stateChanged(int)`` — so partial → checked emits
  ``stateChanged`` alone;
* ``isChecked()`` is true for the partial state, and the indeterminate mark
  paints as a dash inside a filled box.

With ``tristate`` unset (the default) the widget is byte-for-byte the
two-state control it has always been — pinned by the last two tests.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import CheckBox


def _theme() -> None:
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")


def _checkbox(qtbot, *, tristate: bool = False) -> CheckBox:
    _theme()
    checkbox = CheckBox("Option", tristate=tristate)
    qtbot.addWidget(checkbox)
    checkbox.show()
    qtbot.waitExposed(checkbox)
    return checkbox


def _click(qtbot, checkbox: CheckBox) -> None:
    qtbot.mouseClick(
        checkbox, Qt.MouseButton.LeftButton, pos=checkbox.rect().center()
    )


def _signals(checkbox: CheckBox) -> list[tuple[str, object]]:
    log: list[tuple[str, object]] = []
    checkbox.toggled.connect(lambda checked: log.append(("toggled", checked)))
    checkbox.stateChanged.connect(lambda state: log.append(("stateChanged", state)))
    return log


def _painted(checkbox: CheckBox) -> QImage:
    # A dark backdrop keeps the box border's antialiasing out of the glyph
    # classifier (an edge pixel blending toward a light backdrop reads as ink).
    image = QImage(checkbox.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(30, 30, 30))
    painter = QPainter(image)
    try:
        checkbox._painter.paint(checkbox._make_context(painter))
    finally:
        painter.end()
    return image


def _indicator(checkbox: CheckBox) -> QRectF:
    return checkbox._indicator_rect(QRectF(checkbox.rect()))


def _glyph_ink(checkbox: CheckBox, image: QImage) -> list[tuple[int, int]]:
    """Pixels carrying the glyph (white/#fff) over the accent fill (#0078d4).

    The fill has no red channel and the backdrop none either, so ``red > 90``
    is a clean ink test even for an antialiased 1.1 px stroke. The 3 px inset
    skips the box border, whose grey would otherwise pass the test.
    """
    rect = _indicator(checkbox)
    points: list[tuple[int, int]] = []
    for y in range(int(rect.top()) + 3, int(rect.bottom()) - 2):
        for x in range(int(rect.left()) + 3, int(rect.right()) - 2):
            if image.pixelColor(x, y).red() > 90:
                points.append((x, y))
    return points


def test_two_state_is_the_default(qtbot) -> None:
    checkbox = _checkbox(qtbot)

    assert checkbox.isTristate() is False
    assert checkbox.checkState() == Qt.CheckState.Unchecked

    _click(qtbot, checkbox)

    assert checkbox.checkState() == Qt.CheckState.Checked
    assert checkbox.isChecked()


def test_a_click_cycles_unchecked_partial_checked(qtbot) -> None:
    checkbox = _checkbox(qtbot, tristate=True)

    _click(qtbot, checkbox)
    assert checkbox.checkState() == Qt.CheckState.PartiallyChecked
    # Qt: the partial state counts as checked for toggled()/isChecked().
    assert checkbox.isChecked()

    _click(qtbot, checkbox)
    assert checkbox.checkState() == Qt.CheckState.Checked
    assert checkbox.isChecked()

    _click(qtbot, checkbox)
    assert checkbox.checkState() == Qt.CheckState.Unchecked
    assert not checkbox.isChecked()


def test_space_cycles_in_the_same_order(qtbot) -> None:
    checkbox = _checkbox(qtbot, tristate=True)
    checkbox.setFocus()

    qtbot.keyClick(checkbox, Qt.Key.Key_Space)
    assert checkbox.checkState() == Qt.CheckState.PartiallyChecked
    qtbot.keyClick(checkbox, Qt.Key.Key_Space)
    assert checkbox.checkState() == Qt.CheckState.Checked
    qtbot.keyClick(checkbox, Qt.Key.Key_Space)
    assert checkbox.checkState() == Qt.CheckState.Unchecked


def test_set_check_state_emits_what_qt_emits(qtbot) -> None:
    checkbox = _checkbox(qtbot, tristate=True)
    log = _signals(checkbox)

    checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
    # Qt's order: toggled (the bool changed) before stateChanged.
    assert log == [("toggled", True), ("stateChanged", 1)]

    log.clear()
    checkbox.setCheckState(Qt.CheckState.Checked)
    # Partial -> checked keeps isChecked() true, so no toggled — only the state.
    assert log == [("stateChanged", 2)]

    log.clear()
    checkbox.setCheckState(Qt.CheckState.Unchecked)
    assert log == [("toggled", False), ("stateChanged", 0)]


def test_setting_the_same_state_is_silent(qtbot) -> None:
    checkbox = _checkbox(qtbot, tristate=True)
    checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
    log = _signals(checkbox)

    checkbox.setCheckState(Qt.CheckState.PartiallyChecked)

    assert log == []


def test_set_checked_collapses_the_partial_state(qtbot) -> None:
    """Qt's ``QCheckBox::checkStateSet``: a bool write drops PartiallyChecked."""
    checkbox = _checkbox(qtbot, tristate=True)
    checkbox.setCheckState(Qt.CheckState.PartiallyChecked)

    checkbox.setChecked(True)

    assert checkbox.checkState() == Qt.CheckState.Checked


def test_turning_tristate_off_restores_the_two_state_click(qtbot) -> None:
    checkbox = _checkbox(qtbot, tristate=True)
    checkbox.setTristate(False)

    _click(qtbot, checkbox)
    assert checkbox.checkState() == Qt.CheckState.Checked

    _click(qtbot, checkbox)
    assert checkbox.checkState() == Qt.CheckState.Unchecked


def test_partial_paints_a_dash_where_checked_paints_the_tick(qtbot) -> None:
    checkbox = _checkbox(qtbot, tristate=True)
    unchecked = _painted(checkbox)

    checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
    partial = _painted(checkbox)

    checkbox.setCheckState(Qt.CheckState.Checked)
    checked = _painted(checkbox)

    # The box is filled in both non-empty states (differing from unchecked)...
    indicator = _indicator(checkbox)
    mid = (int(indicator.center().x()), int(indicator.center().y()))
    assert partial.pixelColor(*mid) != unchecked.pixelColor(*mid)
    assert checked.pixelColor(*mid) != unchecked.pixelColor(*mid)

    # ...but the glyph differs: the indeterminate mark is a horizontal dash
    # (ink within a couple of pixels of the centre row), the tick is not.
    partial_ink = _glyph_ink(checkbox, partial)
    checked_ink = _glyph_ink(checkbox, checked)
    assert partial_ink, "the indeterminate state must paint a dash"
    assert checked_ink, "the checked state must paint its tick"
    centre_y = indicator.center().y()
    assert max(abs(y - centre_y) for _, y in partial_ink) <= 2.0
    assert max(abs(y - centre_y) for _, y in checked_ink) > 3.0

    assert partial_ink != checked_ink


def test_tristate_checked_paint_is_the_two_state_checked_paint(qtbot) -> None:
    """Enabling tri-state must not reshape the ordinary checked look."""
    two_state = _checkbox(qtbot)
    tri = _checkbox(qtbot, tristate=True)
    for checkbox in (two_state, tri):
        checkbox.resize(two_state.sizeHint())
        checkbox.setChecked(True)
        assert checkbox._checked_progress == 1.0

    left = _painted(two_state)
    right = _painted(tri)

    assert left.size() == right.size()
    for y in range(left.height()):
        for x in range(left.width()):
            assert left.pixelColor(x, y) == right.pixelColor(x, y), (x, y)


def test_a_two_state_checkbox_still_paints_its_tick(qtbot) -> None:
    checkbox = _checkbox(qtbot)
    empty = _painted(checkbox)
    checkbox.setChecked(True)
    checked = _painted(checkbox)

    assert _glyph_ink(checkbox, checked), "the two-state tick is unchanged"
    assert not _glyph_ink(checkbox, empty)
