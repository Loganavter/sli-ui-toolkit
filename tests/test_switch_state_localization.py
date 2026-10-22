"""The switch's state text must come from the host catalog, not English literals.

Owner report 2026-10-22 (Russian UI, text/font flyout): every label was
translated but the switch still read "On" — and "Off" would have fallen back too,
because the widget asked for ``common.switch.switch_on`` / ``switch_off`` while
the host catalogs carry ``common.switch.off`` (and had no ``on`` at all).

The key names now match the catalog convention: ``common.switch.on`` /
``common.switch.off``. This test configures a host catalog and proves the widget
picks the translated pair up, and follows a language change.
"""

from __future__ import annotations

import json

import pytest

from sli_ui_toolkit import TranslationManager, emit_language_changed, get_current_language
from sli_ui_toolkit.i18n import configure_i18n
from sli_ui_toolkit.widgets import Switch


@pytest.fixture(autouse=True)
def _restore_i18n_backend(qapp):
    mgr = TranslationManager()
    saved = (
        getattr(mgr, "_custom_translator", None),
        getattr(mgr, "_language_provider", None),
        mgr._current_lang,
    )
    yield
    mgr._custom_translator = saved[0]
    mgr._language_provider = saved[1]
    mgr._current_lang = saved[2]


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "app"
    for lang, (on_text, off_text) in {
        "ru": ("Вкл", "Выкл"),
        "en": ("On", "Off"),
    }.items():
        (root / lang).mkdir(parents=True)
        (root / lang / "common.json").write_text(
            json.dumps({"common": {"switch": {"on": on_text, "off": off_text}}}),
            encoding="utf-8",
        )
    configure_i18n(i18n_root=root)
    return root


def test_the_switch_state_text_is_localized(catalog, qtbot):
    emit_language_changed("ru")
    assert get_current_language() == "ru"

    switch = Switch()
    qtbot.addWidget(switch)

    assert (switch._on_text, switch._off_text) == ("Вкл", "Выкл"), (
        "the state text must come from common.switch.on/off, not the English default"
    )


def test_the_switch_follows_a_language_change(catalog, qtbot):
    emit_language_changed("ru")
    switch = Switch()
    qtbot.addWidget(switch)
    assert switch._on_text == "Вкл"

    emit_language_changed("en")

    assert (switch._on_text, switch._off_text) == ("On", "Off")


def test_the_legacy_switch_on_key_is_not_requested(monkeypatch, catalog):
    """Pins the key names: a host that only has common.switch.on must work."""
    seen: list[str] = []
    import sli_ui_toolkit.ui.widgets.atomic.switch as switch_module

    real_tr = switch_module.tr

    def _spy(key, *args, **kwargs):
        seen.append(key)
        return real_tr(key, *args, **kwargs)

    monkeypatch.setattr(switch_module, "tr", _spy)
    emit_language_changed("ru")
    Switch()

    assert "common.switch.on" in seen
    assert not [k for k in seen if k.endswith("switch_on") or k.endswith("switch_off")]
