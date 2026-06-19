"""Custom-background derivation per variant."""

from __future__ import annotations

from PySide6.QtGui import QColor

from sli_ui_toolkit.ui.widgets.buttons.variants import derive_custom_palette


RED = QColor("#D93025")


def test_default_variant_is_tinted_without_border():
    pal = derive_custom_palette(RED, "default")
    # Tint: normal stays partially transparent — alpha well below 255.
    assert pal.normal.alpha() < 80
    assert pal.hover.alpha() > pal.normal.alpha()
    # Hue is preserved (RGB matches base — only alpha changes).
    assert (pal.normal.red(), pal.normal.green(), pal.normal.blue()) == (
        RED.red(),
        RED.green(),
        RED.blue(),
    )
    # Default with custom bg should not draw its own border — the fill is the
    # message; an automatic border just adds visual noise.
    assert pal.border is None


def test_surface_matches_default_fill_but_keeps_border():
    # Fill must be identical so that toggling between default and surface
    # doesn't visually jump, but surface keeps its own tinted border to
    # delineate the "card" against its surroundings.
    d = derive_custom_palette(RED, "default")
    s = derive_custom_palette(RED, "surface")
    assert d.normal.rgba() == s.normal.rgba()
    assert d.hover.rgba() == s.hover.rgba()
    assert d.pressed.rgba() == s.pressed.rgba()
    assert d.disabled.rgba() == s.disabled.rgba()
    assert d.border is None
    assert s.border is not None
    # Border hue matches the base; only alpha differs.
    assert (s.border.red(), s.border.green(), s.border.blue()) == (
        RED.red(),
        RED.green(),
        RED.blue(),
    )


def test_ghost_variant_starts_transparent():
    pal = derive_custom_palette(RED, "ghost")
    assert pal.normal.alpha() == 0
    assert pal.hover.alpha() > 0
    assert pal.pressed.alpha() > pal.hover.alpha()
    assert pal.border is None


def test_unknown_variant_falls_back_to_tint():
    # New variants (e.g. "warning") should inherit the tint custom-bg behavior.
    pal = derive_custom_palette(RED, "warning")
    tint_default = derive_custom_palette(RED, "default")
    assert pal.normal.rgba() == tint_default.normal.rgba()


def test_none_variant_treated_as_default():
    pal = derive_custom_palette(RED, None)
    default = derive_custom_palette(RED, "default")
    assert pal.normal.rgba() == default.normal.rgba()
