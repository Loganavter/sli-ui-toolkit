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


@pytest.fixture(autouse=True)
def _restore_i18n_backend(qapp):
    """configure_i18n state is process-wide; restore it after every test."""
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


def test_add_i18n_root_rebuilds_live_pack(tmp_path):
    """Deferred plugin roots must appear in tr() immediately after registration.

    ``tr(key, language=current)`` reads the live ``_translations`` pack, not
    only the cache. Clearing the cache without rebuilding left export.* keys
    unresolved until the next language switch.
    """
    import json

    from sli_ui_toolkit.i18n import configure_i18n

    app_root = tmp_path / "app"
    (app_root / "en").mkdir(parents=True)
    (app_root / "en" / "app.json").write_text(
        json.dumps({"common": {"ok": "OK"}}), encoding="utf-8"
    )
    plugin_root = tmp_path / "plugin"
    (plugin_root / "en").mkdir(parents=True)
    (plugin_root / "en" / "export.json").write_text(
        json.dumps({"export": {"preview": "Preview"}}), encoding="utf-8"
    )

    mgr = TranslationManager()
    configure_i18n(i18n_root=app_root)
    emit_language_changed("en")
    assert tr("export.preview") == "export.preview"

    mgr.add_i18n_root(plugin_root)
    assert tr("export.preview") == "Preview"
    assert tr("export.preview", language="en") == "Preview"


def test_add_i18n_root_is_idempotent(tmp_path):
    """Re-registering a known root must not rebuild the pack.

    The canvas widget-feature scan re-registers every feature's i18n root on
    each pass (``scene/registry.get_widget_features``), so a duplicate call
    used to clear the pack cache and re-glob + re-parse every JSON file inside a
    reducer dispatch -- measured 2026-10-24 as a 1333 ms GUI-thread stall on the
    Windows build.
    """
    import json

    from sli_ui_toolkit.i18n import configure_i18n

    app_root = tmp_path / "app"
    (app_root / "en").mkdir(parents=True)
    (app_root / "en" / "app.json").write_text(
        json.dumps({"common": {"ok": "OK"}}), encoding="utf-8"
    )
    feat_root = tmp_path / "feature"
    (feat_root / "en").mkdir(parents=True)
    (feat_root / "en" / "feature.json").write_text(
        json.dumps({"feature": {"title": "Title"}}), encoding="utf-8"
    )

    mgr = TranslationManager()
    configure_i18n(i18n_root=app_root)
    emit_language_changed("en")
    mgr.add_i18n_root(feat_root)
    assert tr("feature.title") == "Title"

    builds = {"n": 0}
    original = mgr._build_language_pack

    def _counting(lang_code):
        builds["n"] += 1
        return original(lang_code)

    mgr._build_language_pack = _counting  # type: ignore[method-assign]
    mgr.add_i18n_root(feat_root)  # duplicate registration
    assert builds["n"] == 0, (
        "a duplicate add_i18n_root rebuilt the language pack; it must be a "
        "no-op (each duplicate clears the cache and re-globs every JSON file)"
    )
    assert tr("feature.title") == "Title", "the live pack must survive a duplicate call"

    mgr.add_i18n_root(tmp_path / "another")
    assert builds["n"] == 1, "a NEW root must still invalidate and rebuild"


def test_translatable_defers_when_hidden(qapp, qtbot):
    from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget
    from sli_ui_toolkit.i18n import translatable_callback

    stack = QStackedWidget()
    visible_page = QWidget()
    hidden_page = QWidget()
    label = QLabel("start", hidden_page)
    stack.addWidget(visible_page)
    stack.addWidget(hidden_page)
    stack.setCurrentWidget(visible_page)
    stack.show()
    qtbot.addWidget(stack)

    seen: list[str] = []

    def _on_lang(lang: str) -> None:
        seen.append(lang)
        label.setText(lang)

    translatable_callback(label, _on_lang, defer_when_hidden=True)
    assert seen  # initial apply while binding (may run before hide is noticed)
    initial = label.text()
    seen.clear()

    emit_language_changed("ru")
    assert seen == []
    assert label.text() == initial

    emit_language_changed("zh")
    assert label.text() == initial
    assert seen == []

    stack.setCurrentWidget(hidden_page)
    qtbot.waitUntil(lambda: label.isVisible(), timeout=1000)
    qtbot.waitUntil(lambda: label.text() == "zh", timeout=1000)
    assert "zh" in seen


def test_configure_i18n_wires_custom_translator(qapp):
    """The ``translator=`` backend is no longer ignored (was a silent no-op)."""
    from sli_ui_toolkit.i18n import configure_i18n

    configure_i18n(translator=lambda key, lang: f"<{lang}>{key}")
    assert tr("k", language="ru") == "<ru>k"
    assert tr("k") == f"<{get_current_language()}>k"
    # ``default=`` still applies when the custom backend returns the key.
    assert tr("k", default="fallback", language="ru") == "<ru>k"


def test_configure_i18n_wires_language_provider(qapp):
    """The ``language_provider=`` hook now sources the reported language."""
    from sli_ui_toolkit.i18n import configure_i18n

    configure_i18n(language_provider=lambda: "fr")
    assert get_current_language() == "fr"
    # A falsy provider value falls back to the tracked language.
    configure_i18n(language_provider=lambda: "")
    emit_language_changed("ru")
    assert get_current_language() == "ru"
