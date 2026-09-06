"""Guard: theme token remapping (alias machinery) must not be reintroduced.

Tokens always resolve to themselves — ``get_color(key)`` must equal the
palette entry for ``key`` verbatim. Any future alias/remap table breaks
``test_tokens_resolve_to_themselves``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QColor

import sli_ui_toolkit.ui.managers.theme_manager as tm_module
from sli_ui_toolkit.palettes import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.theme import ThemeManager

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLKIT_SRC = _REPO_ROOT / "src" / "sli_ui_toolkit"

# The exact file name is referenced here as a string literal for the
# file-walk assertion only — the resource itself must not exist.
_ALIAS_RESOURCE_NAME = "theme_aliases.json"


def test_no_alias_resource_file():
    """No ``theme_aliases.json`` anywhere under ``src/sli_ui_toolkit/``."""
    found = [
        str(p)
        for p in _TOOLKIT_SRC.rglob("*")
        if p.is_file() and p.name == _ALIAS_RESOURCE_NAME
    ]
    assert found == [], f"alias resource still present: {found}"


@pytest.mark.parametrize(
    "symbol",
    [
        "ALIAS",
        "_THEME_ALIASES",
        "register_aliases",
        "_resolve_alias",
        "_load_alias_table",
        "_lookup_raw_with_alias",
    ],
)
def test_no_alias_symbols(symbol):
    """Alias machinery symbols must not exist on the theme manager module."""
    assert not hasattr(tm_module, symbol), f"alias symbol reintroduced: {symbol}"


_DERIVE_RE = re.compile(
    r"^\s*(lighten|darken|alpha)\s*\(\s*([^,]+?)\s*,\s*([^)]+?)\s*\)\s*$",
    re.IGNORECASE,
)


def _expected_color(value) -> QColor:
    """Expected color for a palette entry, computed WITHOUT ThemeManager.

    QColor entries and plain color literals map via ``QColor`` directly;
    derive entries are resolved only when the base is a color literal
    (hex/named) — never via another token name.
    """
    if isinstance(value, QColor):
        return QColor(value)
    assert isinstance(value, str), f"palette entry must be QColor or str, got {type(value).__name__}"
    text = value.strip()
    plain = QColor(text)
    if plain.isValid():
        return plain
    m = _DERIVE_RE.match(text)
    assert m is not None, f"palette entry is neither a color nor a derive literal: {value!r}"
    func, base_token, amount = m.group(1).lower(), m.group(2).strip().strip("'\""), m.group(3).strip()
    base = QColor(base_token)
    assert base.isValid(), f"derive base must be a color literal, got {base_token!r}"
    if func in ("lighten", "darken"):
        pct = float(amount.rstrip("%").strip())
        if 0 < pct < 1:
            pct *= 100.0
        factor = max(100, int(round(100 + pct)))
        return base.lighter(factor) if func == "lighten" else base.darker(factor)
    assert func == "alpha", f"unknown derive func: {func!r}"
    raw = amount
    if raw.endswith("%"):
        alpha = int(round(255 * float(raw[:-1].strip()) / 100.0))
    else:
        v = float(raw)
        if 0 <= v <= 1:
            alpha = int(round(255 * v))
        elif 1 < v <= 100:
            alpha = int(round(255 * (v / 100.0)))
        else:
            alpha = int(round(v))
    base.setAlpha(max(0, min(255, alpha)))
    return base


@pytest.fixture(params=["light", "dark"])
def themed_manager(request, qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme(request.param, qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield tm, request.param
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]


def test_tokens_resolve_to_themselves(themed_manager):
    """Every palette key resolves to its own entry — no remapping."""
    tm, theme_name = themed_manager
    palette = FLUENT_DARK if theme_name == "dark" else FLUENT_LIGHT
    assert palette, f"[{theme_name}] palette is empty"
    for key, value in palette.items():
        expected = _expected_color(value)
        assert expected.isValid(), f"[{theme_name}] palette entry {key!r} is not a valid color"
        resolved = tm.get_color(key)
        assert resolved.isValid(), f"[{theme_name}] token {key!r} resolved to invalid color"
        assert resolved.name() == expected.name(), (
            f"[{theme_name}] token {key!r} remapped: got {resolved.name()}, "
            f"palette holds {expected.name()}"
        )
        direct = tm.try_get_color(key)
        assert direct is not None, f"[{theme_name}] try_get_color({key!r}) returned None"
        assert direct.name() == expected.name(), (
            f"[{theme_name}] try_get_color({key!r}) remapped: got {direct.name()}, "
            f"palette holds {expected.name()}"
        )
