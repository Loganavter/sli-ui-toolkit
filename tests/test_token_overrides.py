"""Per-instance colour overrides: one widget's colour, without the whole theme.

Before this module a host could recolour a toolkit control only globally
(``ThemeManager.set_color`` repaints every widget painted with that token) or
through a one-off constructor argument. ``TokenOverrideMixin`` +
``resolve_token`` give the missing third option: a per-instance map, consulted
by the painters before the family token.

Every test drives real widgets and reads the painted pixel, so a reading site
that ignores the map fails on the pixel instead of on a source-level
assertion. Both themes are exercised: light and dark are first-class, and an
override must survive a theme switch without becoming a theme write.

Red before: on the base commit the module does not exist (collection error),
``Button.getBackgroundColor`` reads only the constructor field, and the four
painter families read ``ThemeManager`` directly — every pixel assertion below
that expects the override would sample the family token instead.
"""

from __future__ import annotations

import copy
import logging

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.helpers import (
    NEUTRAL_TOKEN_FALLBACK,
    TokenOverrideMixin,
    reset_miss_warning,
    resolve_token,
)
from sli_ui_toolkit.widgets import Button, CheckBox, CustomLineEdit, Slider, Switch

THEMES = ("light", "dark")

#: The same override in both themes: a theme switch must not touch it, and it
#: must differ from every sentinel below (both themes') or a stale colour would
#: pass for an override.
OVERRIDE = QColor("#ff8800")

#: Family tokens the adopted widgets paint with, and the sentinel each palette
#: gets per theme. Different values per theme: a pixel that answers the wrong
#: theme's sentinel is caught, not merely "not the override".
_SENTINELS: dict[str, dict[str, str]] = {
    "light": {
        "input.background": "#123456",
        "checkbox.border": "#00aa00",
        "switch.track.disabled": "#aa00aa",
        "slider.track.unfilled": "#0066cc",
        "button.default.background": "#00aa55",
    },
    "dark": {
        "input.background": "#654321",
        "checkbox.border": "#00ff66",
        "switch.track.disabled": "#66ff00",
        "slider.track.unfilled": "#ff6600",
        "button.default.background": "#123123",
    },
}


def _sentinel_palettes() -> dict[str, dict[str, QColor]]:
    palettes: dict[str, dict[str, QColor]] = {}
    for name, source in (("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)):
        palette = dict(source)
        palette.update(
            {token: QColor(value) for token, value in _SENTINELS[name].items()}
        )
        palettes[name] = palette
    return palettes


@pytest.fixture(params=THEMES)
def themed(request, qapp):
    """Both palettes carry sentinels; the active theme is ``request.param``."""
    name = request.param
    palettes = _sentinel_palettes()
    tm = ThemeManager.get_instance()
    tm.register_palettes(palettes["light"], palettes["dark"])
    tm.set_theme(name, qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    try:
        yield tm, palettes[name], palettes
    finally:
        tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
        tm.set_theme("light", qapp, await_ripples=False)
        tm._flush_pending_theme()  # type: ignore[attr-defined]


# -- render helpers ----------------------------------------------------------


def _render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        widget.render(painter, QPoint(0, 0))
    finally:
        painter.end()
    return image


def _rgb(image: QImage, x: int, y: int) -> tuple[int, int, int]:
    colour = image.pixelColor(x, y)
    return colour.red(), colour.green(), colour.blue()


def _colour_rgb(colour: QColor) -> tuple[int, int, int]:
    return colour.red(), colour.green(), colour.blue()


def _token_rgb(palette, token: str) -> tuple[int, int, int]:
    return _colour_rgb(palette[token])


# -- widget builders (one sample point each) ---------------------------------


def _edit(qtbot) -> CustomLineEdit:
    edit = CustomLineEdit()
    qtbot.addWidget(edit)
    edit.setFixedSize(200, CustomLineEdit.HEIGHT)
    edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    edit.show()
    qtbot.waitExposed(edit)
    return edit


def _edit_sample(edit: CustomLineEdit) -> tuple[int, int]:
    """Mid-height on the right of the plate (clear of the rounded corner)."""
    return edit.width() - 20, edit.height() // 2


def _checkbox(qtbot) -> CheckBox:
    checkbox = CheckBox("Row text")
    qtbot.addWidget(checkbox)
    checkbox.resize(160, 26)
    checkbox.show()
    qtbot.waitExposed(checkbox)
    return checkbox


def _checkbox_sample(checkbox: CheckBox) -> tuple[int, int]:
    """The outline's own left edge (the pen is centred half a width inwards)."""
    indicator = checkbox._indicator_rect(checkbox.rect())
    return int(indicator.left()), int(indicator.center().y())


def _switch(qtbot) -> Switch:
    switch = Switch()
    qtbot.addWidget(switch)
    switch.resize(switch.sizeHint())
    switch.setEnabled(False)
    switch.show()
    qtbot.waitExposed(switch)
    return switch


def _switch_sample(switch: Switch) -> tuple[int, int]:
    """Right of the resting knob, on the track."""
    x = scaled_px(switch.RING_GUTTER) + scaled_px(switch.TRACK_WIDTH) - 4
    return int(x), switch.height() // 2


def _slider(qtbot) -> Slider:
    slider = Slider()
    qtbot.addWidget(slider)
    slider.resize(200, 40)
    slider.setValue(0)  # no value fill over the groove
    slider.show()
    qtbot.waitExposed(slider)
    return slider


def _slider_sample(slider: Slider) -> tuple[int, int]:
    return 100, int(slider.thumbCenter().y())


def _assert_pair(palette, token, sibling, over, sample) -> None:
    """The overridden widget samples the override, its sibling the family token."""
    image_over = _render(over)
    image_sibling = _render(sibling)
    assert _rgb(image_over, *sample(over)) == _colour_rgb(OVERRIDE), (
        f"the overridden widget does not sample the override for {token!r}"
    )
    assert _rgb(image_sibling, *sample(sibling)) == _token_rgb(palette, token), (
        f"the sibling does not sample the family token {token!r}"
    )


# -- the lookup order --------------------------------------------------------


def test_the_override_wins_over_the_palette_token(qapp, themed):
    _tm, palette, _palettes = themed
    over = CustomLineEdit()
    sibling = CustomLineEdit()
    assert resolve_token(over, "input.background") == palette["input.background"]
    over.set_token_overrides({"input.background": OVERRIDE})
    assert resolve_token(over, "input.background") == OVERRIDE
    assert resolve_token(sibling, "input.background") == palette["input.background"]


def test_clearing_restores_the_family_token(qapp, themed):
    _tm, palette, _palettes = themed
    edit = CustomLineEdit()
    edit.set_token_overrides({"input.background": OVERRIDE})
    assert resolve_token(edit, "input.background") == OVERRIDE
    edit.clear_token_overrides("input.background")
    assert resolve_token(edit, "input.background") == palette["input.background"]
    assert edit.token_overrides() == {}


def test_a_hex_literal_value_is_accepted_and_a_palette_key_is_not(qapp, caplog):
    edit = CustomLineEdit()
    with caplog.at_level(logging.WARNING, logger="TokenOverrides"):
        edit.set_token_overrides(
            {"input.background": OVERRIDE.name(), "input.text": "input.background"}
        )
    assert edit.token_overrides()["input.background"] == OVERRIDE
    assert "input.text" not in edit.token_overrides(), (
        "a palette key is not a colour and must not be stored"
    )
    assert any("input.text" in record.getMessage() for record in caplog.records)


def test_the_returned_map_is_read_only(qapp):
    edit = CustomLineEdit()
    edit.set_token_overrides({"input.background": OVERRIDE})
    with pytest.raises(TypeError):
        edit.token_overrides()["input.background"] = QColor("#000000")  # type: ignore[index]


def test_a_missing_token_logs_once_and_paints_neutral(qapp, caplog):
    reset_miss_warning("checkbox.textt")
    edit = CustomLineEdit()
    with caplog.at_level(logging.WARNING, logger="TokenOverrides"):
        first = resolve_token(edit, "checkbox.textt")
        second = resolve_token(edit, "checkbox.textt")
    assert first == QColor(NEUTRAL_TOKEN_FALLBACK)
    assert second == first
    reported = [
        record
        for record in caplog.records
        if "checkbox.textt" in record.getMessage()
    ]
    assert len(reported) == 1, "a miss must warn once per key, not once per read"


# -- two instances, one overridden -------------------------------------------


def test_two_fields_one_override(qapp, qtbot, themed):
    _tm, palette, _palettes = themed
    sibling = _edit(qtbot)
    over = _edit(qtbot)
    over.set_token_overrides({"input.background": OVERRIDE})
    _assert_pair(palette, "input.background", sibling, over, _edit_sample)


def test_two_boxes_one_override(qapp, qtbot, themed):
    _tm, palette, _palettes = themed
    sibling = _checkbox(qtbot)
    over = _checkbox(qtbot)
    over.set_token_overrides({"checkbox.border": OVERRIDE})
    _assert_pair(palette, "checkbox.border", sibling, over, _checkbox_sample)


def test_two_switches_one_override(qapp, qtbot, themed):
    _tm, palette, _palettes = themed
    sibling = _switch(qtbot)
    over = _switch(qtbot)
    over.set_token_overrides({"switch.track.disabled": OVERRIDE})
    _assert_pair(palette, "switch.track.disabled", sibling, over, _switch_sample)


def test_two_sliders_one_override(qapp, qtbot, themed):
    _tm, palette, _palettes = themed
    sibling = _slider(qtbot)
    over = _slider(qtbot)
    over.set_token_overrides({"slider.track.unfilled": OVERRIDE})
    _assert_pair(palette, "slider.track.unfilled", sibling, over, _slider_sample)


def test_two_buttons_one_override(qapp, qtbot, themed):
    """``background_color`` and ``set_token_overrides`` are one API, one slot."""
    _tm, _palette, _palettes = themed
    sibling = Button()
    over = Button()
    for button in (sibling, over):
        qtbot.addWidget(button)
        button.resize(48, 48)
        button.show()
        qtbot.waitExposed(button)

    over.set_token_overrides({Button.BACKGROUND_TOKEN: OVERRIDE})
    assert over.getBackgroundColor() == OVERRIDE
    assert over._custom_bg_color == OVERRIDE, (
        "the painter's own field must follow the map"
    )
    assert sibling.getBackgroundColor() is None
    assert _render(over) != _render(sibling), (
        "the override never reached the painted fill"
    )

    # The constructor argument is the same slot, and a later override replaces it.
    constructed = Button(background_color=QColor("#00aa00"))
    qtbot.addWidget(constructed)
    assert constructed.getBackgroundColor() == QColor("#00aa00")
    constructed.set_token_overrides({Button.BACKGROUND_TOKEN: OVERRIDE})
    assert constructed.getBackgroundColor() == OVERRIDE
    constructed.clear_token_overrides()
    assert constructed.getBackgroundColor() is None


# -- bridge across a theme switch --------------------------------------------


@pytest.mark.parametrize("target", THEMES)
def test_a_theme_switch_keeps_the_override(qapp, qtbot, themed, target):
    tm, _palette, palettes = themed
    sibling = _edit(qtbot)
    over = _edit(qtbot)
    over.set_token_overrides({"input.background": OVERRIDE})

    tm.set_theme(target, qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]

    assert resolve_token(over, "input.background") == OVERRIDE
    _assert_pair(palettes[target], "input.background", sibling, over, _edit_sample)


# -- the map never becomes a theme write -------------------------------------


def _palette_signature(palette: dict) -> dict[str, object]:
    """Byte-level signature: ``rgba()`` for colours, the raw value otherwise."""
    signature: dict[str, object] = {}
    for key, value in palette.items():
        signature[key] = value.rgba() if isinstance(value, QColor) else value
    return signature


def test_overrides_never_touch_the_theme(qapp, qtbot, themed):
    tm, palette, _palettes = themed
    before = (
        _palette_signature(copy.deepcopy(tm._light_palette)),
        _palette_signature(copy.deepcopy(tm._dark_palette)),
    )

    over = _edit(qtbot)
    over.set_token_overrides(
        {
            "input.background": OVERRIDE,
            "input.text": OVERRIDE,
            "accent": OVERRIDE,
        }
    )
    switch = _switch(qtbot)
    switch.set_token_overrides({"switch.track.disabled": OVERRIDE})
    tm.set_theme("dark" if tm.get_current_theme() == "light" else "light", qapp,
                 await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    over.clear_token_overrides()

    after = (
        _palette_signature(copy.deepcopy(tm._light_palette)),
        _palette_signature(copy.deepcopy(tm._dark_palette)),
    )
    assert after == before, "a per-instance override mutated the theme palettes"
    # And the token every painter reads is still the active theme's sentinel —
    # the switch above changed the theme, never a palette entry.
    active = tm.get_current_theme()
    assert tm.get_color("input.background") == QColor(_SENTINELS[active]["input.background"])


def test_an_unknown_override_key_is_ignored(qapp, qtbot, themed):
    """A typo'd key is stored but no painter reads it: the widget is unchanged."""
    _tm, _palette, _palettes = themed
    edit = _edit(qtbot)
    before = _render(edit)
    edit.set_token_overrides({"input.backround": OVERRIDE})
    assert _render(edit) == before
    assert edit.token_overrides()["input.backround"] == OVERRIDE


# -- the mixin contract on its own -------------------------------------------


class _Probe(TokenOverrideMixin):
    """No Qt: the mixin's contract is a map + a repaint, not a widget."""

    def __init__(self) -> None:
        self.paints = 0

    def update(self) -> None:  # type: ignore[override]
        self.paints += 1


def test_the_map_merges_repaints_and_clears_one_or_all(qapp):
    probe = _Probe()
    probe.set_token_overrides({"a": QColor("#010203")})
    probe.set_token_overrides({"b": "#040506"})
    assert dict(probe.token_overrides()) == {
        "a": QColor("#010203"),
        "b": QColor("#040506"),
    }
    assert probe.paints == 2, "every mutation repaints"

    probe.clear_token_overrides("a")
    assert dict(probe.token_overrides()) == {"b": QColor("#040506")}
    probe.clear_token_overrides()
    assert dict(probe.token_overrides()) == {}
    assert probe.paints == 4

    # Clearing an absent name is a no-op, not a repaint.
    probe.clear_token_overrides("gone")
    assert probe.paints == 4
