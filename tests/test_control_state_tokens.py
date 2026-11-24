"""The box, switch and slider paint their own state tokens, not a neighbour's.

Before this migration a checkbox hovered with ``dialog.button.hover``, its
outline was ``dialog.border`` and its label ``dialog.text`` — so a host that
restyled dialogs repainted every checkbox. The same borrows sat in the radio
(which shares the box family), the switch (its hover wash was the dialog button
plate) and the slider (its groove was the dialog border). The palettes already
carry ``checkbox.*`` / ``switch.*`` / ``slider.*``; these tests drive the real
widgets and read pixels to prove the paint path now follows the family token and
ignores the borrowed one, in both themes.

Every test is red before the migration: the sampled pixel followed the borrowed
token and ignored the family token, which is the opposite of what is asserted.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import CheckBox, RadioButton, Slider, Switch

#: One sentinel per owned state, different per theme: a pixel that resolves the
#: family key has to answer the *active* theme's value, not a hardcoded one.
_SENTINELS = {
    "light": {
        "checkbox.text": "#0044ff",
        "checkbox.text.disabled": "#ff2200",
        "checkbox.border": "#00aa00",
        "checkbox.background.hover": "#aa00aa",
        "checkbox.background.pressed": "#00aaaa",
        "switch.text": "#0044ff",
        "switch.text.disabled": "#ff2200",
        "switch.track.hover": "#aa00aa",
        "switch.track.disabled": "#00aaaa",
        "slider.track.unfilled": "#00aa00",
        "slider.track.filled": "#0000cc",
        "slider.track.hover": "#aa00aa",
        "slider.track.disabled": "#00aaaa",
        "slider.thumb.disabled": "#ff8800",
    },
    "dark": {
        "checkbox.text": "#3399ff",
        "checkbox.text.disabled": "#ff4400",
        "checkbox.border": "#44cc44",
        "checkbox.background.hover": "#cc44cc",
        "checkbox.background.pressed": "#44cccc",
        "switch.text": "#3399ff",
        "switch.text.disabled": "#ff4400",
        "switch.track.hover": "#cc44cc",
        "switch.track.disabled": "#44cccc",
        "slider.track.unfilled": "#44cc44",
        "slider.track.filled": "#4444dd",
        "slider.track.hover": "#cc44cc",
        "slider.track.disabled": "#44cccc",
        "slider.thumb.disabled": "#dd9944",
    },
}

#: The keys the migration removed from these painters. A pixel that still follows
#: one of them is a borrow: the widget would be restyled by a dialog change.
_BORROWED = ("dialog.border", "dialog.text", "dialog.button.hover")


@pytest.fixture(params=["light", "dark"])
def themed(request, qapp):
    """Register a palette whose state colours are sentinels, in both themes."""
    name = request.param
    base = FLUENT_DARK if name == "dark" else FLUENT_LIGHT
    palettes = {}
    for theme_name, source in (("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)):
        palette = dict(source)
        palette.update(
            {token: QColor(value) for token, value in _SENTINELS[theme_name].items()}
        )
        palettes[theme_name] = palette
    tm = ThemeManager.get_instance()
    tm.register_palettes(palettes["light"], palettes["dark"])
    tm.set_theme(name, qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield tm, palettes[name]
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]


def _render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    return image


def _rgb(image: QImage, x: int, y: int) -> tuple[int, int, int]:
    colour = image.pixelColor(x, y)
    return colour.red(), colour.green(), colour.blue()


def _token_rgb(palette, token: str) -> tuple[int, int, int]:
    colour = palette[token]
    return colour.red(), colour.green(), colour.blue()


def _assert_follows(
    widget, sample: tuple[int, int], *, owned: str, borrowed: str, palette
) -> None:
    """The sampled pixel answers *owned* and is untouched by *borrowed*.

    This is the discriminating assertion of the migration: before it, the same
    pixel moved with ``borrowed`` and stayed put when ``owned`` changed.
    """
    before = _rgb(_render(widget), *sample)

    ThemeManager.get_instance().set_color(borrowed, QColor("#123456"))
    assert _rgb(_render(widget), *sample) == before, (
        f"the pixel still follows the borrowed token {borrowed!r}"
    )

    ThemeManager.get_instance().set_color(owned, QColor("#fedcba"))
    assert _rgb(_render(widget), *sample) != before, (
        f"the pixel does not follow the family token {owned!r}"
    )
    ThemeManager.get_instance().set_color(owned, palette[owned])


# -------- check box ---------------------------------------------------------


def _checkbox(qtbot) -> CheckBox:
    checkbox = CheckBox("Row text")
    qtbot.addWidget(checkbox)
    checkbox.resize(160, 26)
    checkbox.show()
    qtbot.waitExposed(checkbox)
    return checkbox


def test_checkbox_hover_plate_is_the_box_token(qapp, qtbot, themed):
    tm, palette = themed
    checkbox = _checkbox(qtbot)
    indicator = checkbox._indicator_rect(checkbox.rect())
    centre = (int(indicator.center().x()), int(indicator.center().y()))

    checkbox.setHoverActive(True)
    qtbot.wait(220)  # the hover progress animation settles at 1.0

    _assert_follows(
        checkbox,
        centre,
        owned="checkbox.background.hover",
        borrowed="dialog.button.hover",
        palette=palette,
    )
    # The outline is the box's own border, not the dialog's.
    assert _rgb(_render(checkbox), int(indicator.left()), centre[1]) == _token_rgb(
        palette, "checkbox.border"
    )


def test_checkbox_pressed_plate_is_the_box_token(qapp, qtbot, themed):
    tm, palette = themed
    checkbox = _checkbox(qtbot)
    indicator = checkbox._indicator_rect(checkbox.rect())
    centre = (int(indicator.center().x()), int(indicator.center().y()))

    QTest.mousePress(
        checkbox, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        QPoint(*centre),
    )
    _assert_follows(
        checkbox,
        centre,
        owned="checkbox.background.pressed",
        borrowed="dialog.button.hover",
        palette=palette,
    )
    QTest.mouseRelease(
        checkbox, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        QPoint(*centre),
    )


def test_checkbox_disabled_label_reads_its_own_token(qapp, qtbot, themed):
    _tm, palette = themed
    checkbox = _checkbox(qtbot)
    text_left = int(checkbox._indicator_rect(checkbox.rect()).right()) + 2

    enabled = _render(checkbox)
    assert _count(enabled, _bluish, text_left) > 0
    assert _count(enabled, _reddish, text_left) == 0

    checkbox.setEnabled(False)
    disabled = _render(checkbox)
    assert _count(disabled, _bluish, text_left) == 0
    assert _count(disabled, _reddish, text_left) > 0


# -------- radio (shares the box family) -------------------------------------


def _radio(qtbot) -> RadioButton:
    radio = RadioButton("Option")
    qtbot.addWidget(radio)
    radio.resize(150, 26)
    radio.show()
    qtbot.waitExposed(radio)
    return radio


def test_radio_hover_plate_is_the_box_token(qapp, qtbot, themed):
    _tm, palette = themed
    radio = _radio(qtbot)
    indicator = radio._indicator_rect(radio.rect())
    centre = (int(indicator.center().x()), int(indicator.center().y()))

    radio.setHoverActive(True)
    qtbot.wait(220)

    _assert_follows(
        radio,
        centre,
        owned="checkbox.background.hover",
        borrowed="dialog.button.hover",
        palette=palette,
    )
    # The outline is the box family's border, not the dialog border (the
    # ellipse edge is antialiased, so only the ownership, not the exact value,
    # is asserted there).
    edge = (int(indicator.left()), centre[1])
    _assert_follows(
        radio, edge, owned="checkbox.border", borrowed="dialog.border",
        palette=palette,
    )


def test_radio_pressed_plate_is_the_box_token(qapp, qtbot, themed):
    _tm, palette = themed
    radio = _radio(qtbot)
    indicator = radio._indicator_rect(radio.rect())
    centre = (int(indicator.center().x()), int(indicator.center().y()))

    QTest.mousePress(
        radio, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        QPoint(*centre),
    )
    _assert_follows(
        radio,
        centre,
        owned="checkbox.background.pressed",
        borrowed="dialog.button.hover",
        palette=palette,
    )
    QTest.mouseRelease(
        radio, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        QPoint(*centre),
    )


def test_radio_disabled_label_reads_its_own_token(qapp, qtbot, themed):
    _tm, _palette = themed
    radio = _radio(qtbot)
    text_left = int(radio._indicator_rect(radio.rect()).right()) + 2

    assert _count(_render(radio), _bluish, text_left) > 0
    assert _count(_render(radio), _reddish, text_left) == 0

    radio.setEnabled(False)
    assert _count(_render(radio), _bluish, text_left) == 0
    assert _count(_render(radio), _reddish, text_left) > 0


# -------- switch ------------------------------------------------------------


def _switch(qtbot) -> Switch:
    switch = Switch()
    qtbot.addWidget(switch)
    switch.resize(switch.sizeHint())
    switch.show()
    qtbot.waitExposed(switch)
    return switch


def _track_sample(switch: Switch) -> tuple[int, int]:
    """A point on the track, right of the knob (the knob rests at the left)."""
    from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

    x = scaled_px(switch.RING_GUTTER) + scaled_px(switch.TRACK_WIDTH) - 4
    return int(x), switch.height() // 2


def test_switch_hover_track_is_the_switch_token(qapp, qtbot, themed):
    _tm, palette = themed
    switch = _switch(qtbot)
    switch.setHoverActive(True)
    qtbot.wait(220)

    _assert_follows(
        switch,
        _track_sample(switch),
        owned="switch.track.hover",
        borrowed="dialog.button.hover",
        palette=palette,
    )


def test_switch_disabled_track_and_label_read_their_own_tokens(qapp, qtbot, themed):
    tm, palette = themed
    switch = _switch(qtbot)
    text_left = switch.sizeHint().width() - 20

    assert _count(_render(switch), _bluish, text_left) > 0

    switch.setEnabled(False)
    image = _render(switch)
    assert _rgb(image, *_track_sample(switch)) == _token_rgb(
        palette, "switch.track.disabled"
    )
    assert _count(image, _bluish, text_left) == 0
    assert _count(image, _reddish, text_left) > 0

    # The disabled track must not fall back to the dialog plate either.
    track = _track_sample(switch)
    tm.set_color("dialog.button.hover", QColor("#123456"))
    assert _rgb(_render(switch), *track) == _token_rgb(
        palette, "switch.track.disabled"
    )


# -------- slider ------------------------------------------------------------


def _slider(qtbot) -> Slider:
    slider = Slider()
    qtbot.addWidget(slider)
    slider.resize(200, 40)
    slider.show()
    qtbot.waitExposed(slider)
    return slider


def test_slider_groove_is_the_slider_token(qapp, qtbot, themed):
    _tm, palette = themed
    slider = _slider(qtbot)
    slider.setValue(0)
    y = slider.thumbCenter().y()
    sample = (100, y)

    assert _rgb(_render(slider), *sample) == _token_rgb(palette, "slider.track.unfilled")
    _assert_follows(
        slider,
        sample,
        owned="slider.track.unfilled",
        borrowed="dialog.border",
        palette=palette,
    )


def test_slider_fill_hover_and_disabled_read_their_own_tokens(qapp, qtbot, themed):
    _tm, palette = themed
    slider = _slider(qtbot)
    slider.setValue(slider.maximum())
    centre = slider.thumbCenter()
    groove = (100, centre.y())

    assert _rgb(_render(slider), *groove) == _token_rgb(palette, "slider.track.filled")

    slider.setHoverActive(True)
    assert _rgb(_render(slider), *groove) == _token_rgb(palette, "slider.track.hover")

    slider.setEnabled(False)
    image = _render(slider)
    assert _rgb(image, *groove) == _token_rgb(palette, "slider.track.disabled")
    # Thumb plate: outside the inner value dot (radius = half the outer one).
    plate = (centre.x() - 6, centre.y())
    assert _rgb(image, *plate) == _token_rgb(palette, "slider.thumb.disabled")


# -------- the whole painter ignores the borrowed family ---------------------


def _assert_ignores_dialog_family(tm, widget) -> None:
    """No pixel of this control may move when a dialog token changes."""
    before = _render(widget)
    for token in _BORROWED:
        tm.set_color(token, QColor("#123456"))
    assert _render(widget) == before, (
        "the painter still reads a dialog token — the control is restyled by a "
        "dialog change"
    )


def test_checkbox_painter_ignores_the_dialog_family(qtbot, themed):
    tm, _palette = themed
    checkbox = _checkbox(qtbot)
    checkbox.setHoverActive(True)
    qtbot.wait(220)
    _assert_ignores_dialog_family(tm, checkbox)


def test_radio_painter_ignores_the_dialog_family(qtbot, themed):
    tm, _palette = themed
    radio = _radio(qtbot)
    radio.setHoverActive(True)
    qtbot.wait(220)
    _assert_ignores_dialog_family(tm, radio)


def test_switch_painter_ignores_the_dialog_family(qtbot, themed):
    tm, _palette = themed
    switch = _switch(qtbot)
    switch.setHoverActive(True)
    qtbot.wait(220)
    _assert_ignores_dialog_family(tm, switch)


def test_slider_painter_ignores_the_dialog_family(qtbot, themed):
    tm, _palette = themed
    slider = _slider(qtbot)
    slider.setValue(50)
    _assert_ignores_dialog_family(tm, slider)


# -------- pixel predicates --------------------------------------------------


def _bluish(colour: QColor) -> bool:
    return colour.blue() - max(colour.red(), colour.green()) > 40


def _reddish(colour: QColor) -> bool:
    return colour.red() - max(colour.green(), colour.blue()) > 40


def _count(image: QImage, predicate, x_from: int) -> int:
    hits = 0
    for y in range(image.height()):
        for x in range(max(0, x_from), image.width()):
            if predicate(image.pixelColor(x, y)):
                hits += 1
    return hits
