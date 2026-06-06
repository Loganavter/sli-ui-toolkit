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
from PyQt6.QtGui import QColor

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
]

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
