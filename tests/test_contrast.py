"""WCAG 2.1 contrast checks for default palette token pairs.

Targets:
- 4.5:1 for normal body text (foreground/background).
- 3.0:1 for large text, UI components, and focus indicators.

Tokens that carry alpha < 255 in the palette are overlays whose effective
color depends on what is rendered underneath; these are excluded from the
direct ratio assertions and only sanity-checked for opacity.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor

from sli_ui_toolkit.palettes import FLUENT_DARK, FLUENT_LIGHT

WCAG_AA_TEXT = 4.5
WCAG_AA_UI = 3.0


def _linearize(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(color: QColor) -> float:
    r = _linearize(color.red() / 255.0)
    g = _linearize(color.green() / 255.0)
    b = _linearize(color.blue() / 255.0)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: QColor, bg: QColor) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    light, dark = max(l1, l2), min(l1, l2)
    return (light + 0.05) / (dark + 0.05)


# Pairs that must reach WCAG AA for normal text (4.5:1). Each entry is
# (foreground_token, background_token, role_label).
TEXT_PAIRS = [
    ("WindowText", "Window", "default window text"),
    ("Text", "Base", "input text on input background"),
    ("ButtonText", "Button", "button label on button surface"),
    ("HighlightedText", "Highlight", "selected text on highlight"),
    ("dialog.text", "dialog.background", "dialog body text"),
    ("tooltip.text", "tooltip.background", "tooltip text"),
    ("ToolTipText", "ToolTipBase", "Qt tooltip text"),
    ("list_item.text.normal", "list_item.background.normal", "list item idle"),
    ("list_item.text.normal", "list_item.background.hover", "list item hover"),
    ("help.nav.selected.text", "help.nav.selected", "help nav selected"),
    ("color_dialog.text", "color_dialog.background", "color dialog body"),
    ("switch.text", "Window", "switch label on window"),
    # Control-family state keys (P2 colour-token investigation): each pair must read on the plate its own family
    # owns, not on a borrowed one.
    ("input.text", "input.background", "input text on the input plate"),
    ("input.placeholder", "input.background", "input placeholder"),
    ("checkbox.text", "surface.background", "checkbox label on the surface"),
    ("switch.text", "surface.background", "switch label on the surface"),
    ("list_item.text.selected", "list_item.background.selected", "selected list row text"),
    ("menu.text", "menu.background", "menu row text"),
    ("menu.text", "menu.background.hover", "menu row text on the hover plate"),
    ("titlebar.menu.text", "titlebar.background", "title-bar menu label"),
    # The generic ink families (P3b): a flyout body, a progress label, the painted label family and the calendar
    # read their own family's text token instead of borrowing `dialog.text`.
    ("flyout.text", "flyout.background", "flyout body label"),
    ("progress.text", "progress.track.background", "progress label on the trough"),
    ("label.text", "surface.background", "label text on the surface"),
    ("label.text", "flyout.background", "label text on a flyout card"),
]

# Disabled states are allowed below the AA text target - they must instead read as visibly dimmer than the enabled
# token on the same plate, and stay perceivable. Entries: (disabled, enabled, background, role label).
DISABLED_PAIRS = [
    ("input.text.disabled", "input.text", "input.background", "input disabled text"),
    ("checkbox.text.disabled", "checkbox.text", "surface.background", "checkbox disabled label"),
    ("switch.text.disabled", "switch.text", "surface.background", "switch disabled label"),
    ("list_item.text.disabled", "list_item.text.normal", "list_item.background.normal", "disabled list row text"),
    ("menu.text.disabled", "menu.text", "menu.background", "disabled menu row"),
]
DISABLED_FLOOR = 2.0

# Pairs evaluated against the relaxed UI target (3.0:1) — focus rings,
# borders, separators, large-glyph accents.
UI_PAIRS = [
    ("accent", "Window", "accent token vs. window surface"),
    ("accent", "Base", "accent token vs. input surface"),
    ("Highlight", "Window", "highlight vs. window"),
]


def _opaque(palette: dict, key: str) -> QColor:
    color = QColor(palette[key])
    assert color.alpha() == 255, (
        f"token {key!r} carries alpha {color.alpha()} — overlay tokens cannot "
        "be contrast-tested in isolation; resolve them against their backdrop "
        "before measuring."
    )
    return color


@pytest.mark.parametrize("palette_name,palette", [("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)])
@pytest.mark.parametrize("fg_key,bg_key,role", TEXT_PAIRS)
def test_text_pair_meets_aa(palette_name, palette, fg_key, bg_key, role):
    fg = _opaque(palette, fg_key)
    bg = _opaque(palette, bg_key)
    ratio = contrast_ratio(fg, bg)
    assert ratio >= WCAG_AA_TEXT, (
        f"[{palette_name}] {role}: {fg_key}={fg.name()} on {bg_key}={bg.name()} "
        f"= {ratio:.2f}:1, expected ≥ {WCAG_AA_TEXT}:1"
    )


@pytest.mark.parametrize("palette_name,palette", [("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)])
@pytest.mark.parametrize("fg_key,bg_key,role", UI_PAIRS)
def test_ui_pair_meets_aa(palette_name, palette, fg_key, bg_key, role):
    fg = _opaque(palette, fg_key)
    bg = _opaque(palette, bg_key)
    ratio = contrast_ratio(fg, bg)
    assert ratio >= WCAG_AA_UI, (
        f"[{palette_name}] {role}: {fg_key}={fg.name()} on {bg_key}={bg.name()} "
        f"= {ratio:.2f}:1, expected ≥ {WCAG_AA_UI}:1"
    )


def test_known_contrast_anchors():
    # Anchor a couple of expected values so the helper itself doesn't drift.
    black = QColor("#000000")
    white = QColor("#ffffff")
    assert round(contrast_ratio(black, white), 2) == 21.0
    assert round(contrast_ratio(white, white), 2) == 1.0


@pytest.mark.parametrize("palette_name,palette", [("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)])
@pytest.mark.parametrize("disabled_key,enabled_key,bg_key,role", DISABLED_PAIRS)
def test_disabled_text_is_dimmer_than_enabled(palette_name, palette, disabled_key, enabled_key, bg_key, role):
    bg = _opaque(palette, bg_key)
    enabled_ratio = contrast_ratio(_opaque(palette, enabled_key), bg)
    disabled_ratio = contrast_ratio(_opaque(palette, disabled_key), bg)
    assert disabled_ratio < enabled_ratio, (
        f"[{palette_name}] {role}: {disabled_key}={palette[disabled_key].name()} is not dimmer than "
        f"{enabled_key}={palette[enabled_key].name()} ({disabled_ratio:.2f}:1 vs {enabled_ratio:.2f}:1)"
    )
    assert disabled_ratio >= DISABLED_FLOOR, (
        f"[{palette_name}] {role}: {disabled_ratio:.2f}:1 is below the perceivability floor {DISABLED_FLOOR}:1"
    )


@pytest.mark.parametrize("palette_name,palette", [("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)])
def test_input_underline_states_are_ordered(palette_name, palette):
    plate = _opaque(palette, "input.background")
    idle = contrast_ratio(_opaque(palette, "input.underline"), plate)
    disabled = contrast_ratio(_opaque(palette, "input.underline.disabled"), plate)
    focused = contrast_ratio(_opaque(palette, "input.underline.focused"), plate)
    assert disabled < idle, (
        f"[{palette_name}] the disabled underline ({disabled:.2f}:1) must be dimmer than the idle one ({idle:.2f}:1)"
    )
    assert idle < focused, (
        f"[{palette_name}] the focused underline ({focused:.2f}:1) must stand out from the idle one ({idle:.2f}:1)"
    )
    assert palette["input.underline.focused"].rgba() == palette["accent"].rgba(), (
        f"[{palette_name}] the focused underline must be the accent"
    )


@pytest.mark.parametrize("palette_name,palette", [("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)])
def test_control_hover_steps_away_from_the_plate(palette_name, palette):
    # Hover/pressed move one step from the base plate in the direction the shipped `button.*` / `list_item.*` pairs
    # take: light plates darken, dark plates lighten. Menu separators follow the shared separator colour.
    plate = _relative_luminance(_opaque(palette, "surface.background"))
    light = palette_name == "light"
    for key in (
        "checkbox.background.hover",
        "checkbox.background.pressed",
        "menu.background.hover",
    ):
        step = _relative_luminance(_opaque(palette, key))
        assert (step < plate) if light else (step > plate), (
            f"[{palette_name}] {key} does not step away from surface.background as its family does"
        )
    assert palette["menu.separator"].rgba() == palette["separator.color"].rgba(), (
        f"[{palette_name}] menu.separator must follow separator.color"
    )
