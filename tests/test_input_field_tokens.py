"""The input family paints its own state tokens, not a neighbour's.

P3 migration (2026-11-24). The palette had already shipped the input family's
state keys, but the field painters still read another family's:
``dialog.text`` for text/caret/placeholder/disabled ink,
``surface.background`` for the plate, and the raw accent for the selection
wash. A host that restyles its inputs therefore repainted dialog bodies and
list surfaces instead.

Every test registers a palette where the new key and the old one are
*different* colours, so a reading site that still borrows fails on the pixel
rather than on a source-level assertion. Run in both themes: light and dark
are both first-class and the migration is not allowed to be a dark-theme
convenience.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import ComboBox, CustomLineEdit

THEMES = ("light", "dark")

#: Stand-in colours: the migrated (input) key and the token it used to borrow.
INPUT_PLATE = "#123456"
SURFACE_PLATE = "#fedcba"
INPUT_INK = "#00ff00"
BORROWED_INK = "#ff00ff"
PLACEHOLDER_INK = "#00ffff"
DISABLED_INK = "#ffaa00"
SELECTION_WASH = "#ff8800"


@pytest.fixture(autouse=True)
def _restore_shipped_palettes():
    """Leave the singleton on the shipped palettes: neighbours share it."""
    yield
    ThemeManager.get_instance().register_palettes(FLUENT_LIGHT, FLUENT_DARK)


def _theme(theme: str, overrides: dict[str, str]) -> ThemeManager:
    tm = ThemeManager.get_instance()
    light = dict(FLUENT_LIGHT)
    dark = dict(FLUENT_DARK)
    for key, value in overrides.items():
        light[key] = QColor(value)
        dark[key] = QColor(value)
    tm.register_palettes(light, dark)
    tm.set_theme(theme)
    return tm


def _render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        widget.render(painter, QPoint(0, 0))
    finally:
        painter.end()
    return image


def _painted_names(image: QImage) -> set[str]:
    return {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
    }


def _pixels(image: QImage):
    return [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())]


def _max_gap(image: QImage, channel: str, other: str) -> int:
    """Largest ``channel - other`` gap over the image: how strongly that hue shows.

    The combobox label is drawn at the UI size, so its strokes never reach full
    opacity; an exact-pixel assertion would be a false green (and would have
    passed on the borrowed code too). A hue that no other paint in the field
    produces proves the reading site, alpha or not.
    """
    return max(
        getattr(colour, channel)() - getattr(colour, other)() for colour in _pixels(image)
    )


def _edit(*, text: str = "", placeholder: str = "", enabled: bool = True) -> CustomLineEdit:
    edit = CustomLineEdit()
    edit.setFixedSize(180, CustomLineEdit.HEIGHT)
    if text:
        edit.setText(text)
    if placeholder:
        edit.setPlaceholderText(placeholder)
    edit.setEnabled(enabled)
    # A large enough ink area that the stroke interior is the token itself,
    # never an antialiased blend of it (the offscreen platform grants focus to
    # the first shown widget, so focus is held off explicitly).
    edit.setFont(QFont(edit.font().family(), 24))
    edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return edit


def _combo(*, enabled: bool = True) -> ComboBox:
    combo = ComboBox()
    combo.addItems(["Alpha", "Beta"])
    combo.setCurrentIndex(0)
    combo.setFixedSize(220, 36)
    combo.setEnabled(enabled)
    combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return combo


# -- line edit --------------------------------------------------------------


@pytest.mark.parametrize("theme", THEMES)
def test_the_field_plate_is_the_input_background(qapp, theme):
    _theme(theme, {"input.background": INPUT_PLATE, "surface.background": SURFACE_PLATE})
    edit = _edit()
    try:
        image = _render(edit)
    finally:
        edit.deleteLater()

    assert image.pixelColor(140, edit.height() // 2) == QColor(INPUT_PLATE)
    assert SURFACE_PLATE not in _painted_names(image)


@pytest.mark.parametrize("theme", THEMES)
def test_the_field_text_is_the_input_text(qapp, theme):
    _theme(theme, {"input.text": INPUT_INK, "dialog.text": BORROWED_INK})
    edit = _edit(text="HHHH")
    try:
        painted = _painted_names(_render(edit))
    finally:
        edit.deleteLater()

    assert INPUT_INK in painted
    assert BORROWED_INK not in painted


@pytest.mark.parametrize("theme", THEMES)
def test_the_placeholder_is_the_placeholder_token(qapp, theme):
    _theme(
        theme,
        {
            "input.placeholder": PLACEHOLDER_INK,
            "input.text": INPUT_INK,
            "dialog.text": BORROWED_INK,
        },
    )
    edit = _edit(placeholder="HHHH")
    try:
        painted = _painted_names(_render(edit))
    finally:
        edit.deleteLater()

    assert PLACEHOLDER_INK in painted
    assert INPUT_INK not in painted
    assert BORROWED_INK not in painted


@pytest.mark.parametrize("theme", THEMES)
def test_a_disabled_field_paints_the_disabled_text_token(qapp, theme):
    _theme(
        theme,
        {
            "input.text.disabled": DISABLED_INK,
            "input.text": INPUT_INK,
            "dialog.text": BORROWED_INK,
        },
    )
    edit = _edit(text="HHHH", enabled=False)
    try:
        painted = _painted_names(_render(edit))
    finally:
        edit.deleteLater()

    assert DISABLED_INK in painted
    assert INPUT_INK not in painted
    assert BORROWED_INK not in painted


def test_the_selection_wash_is_the_selection_token(qapp):
    _theme(
        "light",
        {
            "input.selection.background": SELECTION_WASH,
            "accent": BORROWED_INK,
            "input.text": INPUT_INK,
        },
    )
    edit = _edit(text="abcdefghij")
    edit.show()
    edit.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()
    try:
        edit.selectAll()
        image = _render(edit)
        painted = _painted_names(image)
    finally:
        edit.deleteLater()

    # The wash is opaque here so its pixel is the token itself; the accent is
    # still reachable for the clear button, which this field does not show.
    assert SELECTION_WASH in painted
    assert BORROWED_INK not in painted


def test_the_disabled_underline_fallback_reads_the_input_family(qapp):
    """The no-token derivation follows the field, not the dialog.

    ``input.underline.disabled`` is the shipped answer; a palette that predates
    it reaches the owner's mix, which must move with the input family's own
    plate and disabled ink (it read ``surface.background``/``dialog.text``).
    """
    _theme(
        "light",
        {
            "input.background": "#000000",
            "input.text.disabled": "#ffffff",
            "surface.background": "#00ff00",
            "dialog.text": "#ff0000",
        },
    )
    reference = CustomLineEdit()
    try:
        derived = reference._disabled_underline_colour()
        mix = reference.DISABLED_UNDERLINE_MIX
    finally:
        reference.deleteLater()

    expected = int(round(0 + (255 - 0) * mix))
    assert derived == QColor(expected, expected, expected)


# -- combobox field ---------------------------------------------------------


@pytest.mark.parametrize("theme", THEMES)
def test_the_combo_field_plate_is_the_input_background(qapp, theme):
    _theme(theme, {"input.background": INPUT_PLATE, "surface.background": SURFACE_PLATE})
    combo = _combo()
    try:
        image = _render(combo)
    finally:
        combo.deleteLater()

    assert image.pixelColor(120, combo.height() // 2) == QColor(INPUT_PLATE)
    assert SURFACE_PLATE not in _painted_names(image)


@pytest.mark.parametrize("theme", THEMES)
def test_the_combo_field_text_is_the_input_text(qapp, theme):
    _theme(theme, {"input.text": INPUT_INK, "dialog.text": BORROWED_INK})
    combo = _combo()
    try:
        image = _render(combo)
    finally:
        combo.deleteLater()

    # The label and the chevron are both the field's own ink; the dialog's
    # magenta must not appear anywhere in the field.
    assert _max_gap(image, "green", "red") >= 40
    assert _max_gap(image, "green", "blue") >= 40
    assert _max_gap(image, "blue", "green") < 20


@pytest.mark.parametrize("theme", THEMES)
def test_a_disabled_combo_field_paints_the_disabled_text_token(qapp, theme):
    _theme(
        theme,
        {
            "input.text.disabled": DISABLED_INK,
            "input.text": INPUT_INK,
            "dialog.text": BORROWED_INK,
        },
    )
    combo = _combo(enabled=False)
    try:
        image = _render(combo)
    finally:
        combo.deleteLater()

    # Orange (#ffaa00) is the disabled label; the chevron legitimately keeps
    # the enabled ink, so the proof is its presence, not the enabled ink's
    # absence. The borrowed dialog magenta must be gone.
    assert _max_gap(image, "red", "green") >= 40
    assert _max_gap(image, "red", "blue") >= 60
    assert _max_gap(image, "blue", "green") < 20


@pytest.mark.parametrize("theme", THEMES)
def test_the_hovered_combo_field_takes_its_own_hover_plate(qapp, theme):
    """The field's hover plate is its own token, not the row's.

    This test used to pin the debt (hover read
    ``list_item.background.hover`` because no input hover plate existed) and
    said it would flip when the token landed. It has: ``input.background.hover``
    wins even while the row plate is set to a different colour.
    """
    hover_plate = "#654321"
    row_plate = "#112233"
    _theme(
        theme,
        {
            "input.background": INPUT_PLATE,
            "input.background.hover": hover_plate,
            "list_item.background.hover": row_plate,
        },
    )
    combo = _combo()
    combo._hovered = True
    try:
        image = _render(combo)
    finally:
        combo.deleteLater()

    assert image.pixelColor(120, combo.height() // 2) == QColor(hover_plate)


@pytest.mark.parametrize("theme", THEMES)
def test_an_expanded_combo_field_keeps_the_input_plate(qapp, theme):
    """An open dropdown is the field's pressed state, not a second surface."""
    _theme(theme, {"input.background": INPUT_PLATE, "surface.background": SURFACE_PLATE})
    combo = _combo()
    combo._expanded = True
    try:
        image = _render(combo)
    finally:
        combo.deleteLater()

    assert image.pixelColor(120, combo.height() // 2) == QColor(INPUT_PLATE)
