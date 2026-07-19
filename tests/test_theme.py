from __future__ import annotations

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager


def test_palettes_are_dicts():
    assert isinstance(FLUENT_LIGHT, dict) and FLUENT_LIGHT
    assert isinstance(FLUENT_DARK, dict) and FLUENT_DARK


def test_theme_manager_singleton(qapp):
    a = ThemeManager.get_instance()
    b = ThemeManager.get_instance()
    assert a is b


def test_theme_switching(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)

    tm.set_theme("light")
    assert tm.get_current_theme() == "light"
    assert tm.is_dark() is False

    tm.set_theme("dark")
    assert tm.get_current_theme() == "dark"
    assert tm.is_dark() is True


def test_set_theme_suspends_updates_across_emit(qapp, qtbot):
    """QSS + theme_changed must not paint mid-switch (gradual fill-in)."""
    from PySide6.QtWidgets import QWidget

    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)

    host = QWidget()
    host.show()
    qtbot.addWidget(host)

    saw_disabled = {"value": False}

    def _on_theme_changed() -> None:
        if not host.updatesEnabled():
            saw_disabled["value"] = True

    tm.theme_changed.connect(_on_theme_changed)
    try:
        tm.set_theme("light", qapp)
        tm.set_theme("dark", qapp)
    finally:
        tm.theme_changed.disconnect(_on_theme_changed)

    assert saw_disabled["value"] is True
    assert host.updatesEnabled() is True


def test_set_theme_awaits_active_ripple(qapp, qtbot):
    """Blocking theme apply must not start while a button ripple is live."""
    from PySide6.QtCore import QPointF
    from sli_ui_toolkit.widgets import Button

    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)

    btn = Button(text="Apply", variant="surface")
    btn.show()
    qtbot.addWidget(btn)
    btn._ripple.trigger(QPointF(8, 8))
    assert btn._ripple.is_active()

    applied = {"count": 0}

    def _on_theme_changed() -> None:
        applied["count"] += 1

    tm.theme_changed.connect(_on_theme_changed)
    try:
        tm.set_theme("dark", qapp)
        assert tm.get_current_theme() == "light"
        assert applied["count"] == 0
        qtbot.waitUntil(lambda: tm.get_current_theme() == "dark", timeout=1000)
        assert applied["count"] == 1
    finally:
        tm.theme_changed.disconnect(_on_theme_changed)


def test_apply_theme_to_app_has_no_mid_process_events(qapp, monkeypatch):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm._qss_template = "QWidget { color: @WindowText; }"

    calls: list[str] = []
    real_process = qapp.processEvents

    def _spy(*_a, **_k):
        calls.append("processEvents")
        return real_process()

    monkeypatch.setattr(qapp, "processEvents", _spy)
    monkeypatch.setattr(
        "sli_ui_toolkit.ui.managers.theme_manager.QApplication.processEvents",
        _spy,
    )

    tm.apply_theme_to_app(qapp)
    assert calls == []
