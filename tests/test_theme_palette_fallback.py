"""A host palette is layered over the bundled defaults, never stored verbatim.

``ThemeManager.register_palettes`` used to keep the host dict exactly as passed,
so any key the host did not know about — a token a newer toolkit release added,
or one it simply left unstyled — resolved to ``None``; ``resolve_token`` then
painted its neutral ``#808080`` and logged ``unknown theme token``. The
documented contract is the opposite ("Required tokens must be present;
optional ones fall back to the bundled defaults", ``docs/dev/DESIGN_LANGUAGE.md``
§ *Palette overrides*), and these tests pin the implementation to it:

- an omitted key resolves to ``FLUENT_LIGHT`` / ``FLUENT_DARK``;
- a host key always wins over the bundled value, at registration and through a
  runtime ``set_color``;
- ``dark_palette=None`` keeps the "dark mirrors light" shorthand, layered over
  ``FLUENT_DARK`` so the dark theme still gets its own defaults;
- a key in neither dict stays ``None`` — that is the signal the "this palette
  predates the token" compatibility paths key on.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtGui import QColor

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager


@pytest.fixture
def tm(qapp):
    """The process-wide singleton, restored to the shipped palettes afterwards."""
    manager = ThemeManager.get_instance()
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme("light", qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]
    yield manager
    manager.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    manager.set_theme("light", qapp, await_ripples=False)
    manager._flush_pending_theme()  # type: ignore[attr-defined]


def _rgba(color: QColor) -> int:
    return color.rgba()


def _set_theme(tm: ThemeManager, app, name: str) -> None:
    tm.set_theme(name, app, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]


def test_omitted_key_keeps_the_bundled_value(tm, qapp):
    """The token a host never heard of resolves to the shipped default."""
    tm.register_palettes({"accent": QColor("#123456")})
    _set_theme(tm, qapp, "light")

    resolved = tm.try_get_color("dialog.text")
    assert resolved is not None, "an omitted key must fall back to the bundled palette"
    assert _rgba(resolved) == _rgba(FLUENT_LIGHT["dialog.text"])


def test_host_key_wins_over_the_bundled_value(tm, qapp):
    host_accent = QColor("#123456")
    tm.register_palettes({"accent": host_accent})
    _set_theme(tm, qapp, "light")

    assert _rgba(tm.try_get_color("accent")) == _rgba(host_accent)


def test_omitted_key_does_not_log_an_unknown_token(tm, qapp, caplog):
    """The symptom this contract exists for: no warning, no neutral fallback."""
    tm.register_palettes({"accent": QColor("#123456")})
    _set_theme(tm, qapp, "light")

    with caplog.at_level(logging.WARNING, logger="ThemeManager"):
        color = tm.get_color("dialog.background")

    assert _rgba(color) == _rgba(FLUENT_LIGHT["dialog.background"])
    assert "unknown theme token" not in caplog.text


def test_dark_shorthand_layers_the_host_over_the_dark_defaults(tm, qapp):
    """``dark_palette=None`` means "mirror light", over ``FLUENT_DARK``."""
    host_accent = QColor("#123456")
    tm.register_palettes({"accent": host_accent})
    _set_theme(tm, qapp, "dark")

    assert _rgba(tm.try_get_color("accent")) == _rgba(host_accent)
    assert _rgba(tm.try_get_color("dialog.text")) == _rgba(FLUENT_DARK["dialog.text"])


def test_dark_palette_is_layered_over_the_dark_defaults(tm, qapp):
    tm.register_palettes({"accent": QColor("#123456")}, {"accent": QColor("#654321")})
    _set_theme(tm, qapp, "dark")

    assert _rgba(tm.try_get_color("accent")) == _rgba(QColor("#654321"))
    assert _rgba(tm.try_get_color("dialog.background")) == _rgba(FLUENT_DARK["dialog.background"])


def test_runtime_set_color_wins_over_the_bundled_default(tm, qapp):
    _set_theme(tm, qapp, "light")
    override = QColor("#010203")

    tm.set_color("dialog.text", override)

    assert _rgba(tm.try_get_color("dialog.text")) == _rgba(override)


def test_key_in_neither_palette_stays_none(tm, qapp):
    """The compatibility signal survives: only invented keys return ``None``."""
    _set_theme(tm, qapp, "light")

    assert tm.try_get_color("__host_only__.missing") is None
