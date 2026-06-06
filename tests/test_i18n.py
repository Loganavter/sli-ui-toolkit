from __future__ import annotations

from sli_ui_toolkit import (
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
