from __future__ import annotations

import pytest

from sli_ui_toolkit import (
    I18nStateError,
    TranslationManager,
    emit_language_changed,
    get_current_language,
    tr,
    translation_events,
)


def test_translation_events_singleton():
    a = translation_events()
    b = translation_events()
    assert a is b


def test_tr_falls_back_to_key():
    # With no bundles configured, tr returns the key (or provided default).
    assert tr("nonexistent.key.path") == "nonexistent.key.path"
    assert tr("nonexistent.key.path", default="fallback") == "fallback"


def test_emit_language_changed_updates_current(qapp):
    received: list[str] = []
    translation_events().language_changed.connect(received.append)
    emit_language_changed("en")
    assert get_current_language() == "en"
    assert received == ["en"]


def test_manual_language_signal_emit_is_blocked(qapp):
    with pytest.raises(I18nStateError, match="Use emit_language_changed"):
        translation_events().language_changed.emit("ru")


def test_legacy_load_language_is_blocked():
    with pytest.raises(I18nStateError, match="load_language"):
        TranslationManager().load_language("ru")
