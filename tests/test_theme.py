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


def test_themed_container_order_derived_then_children_then_super(qapp, qtbot, monkeypatch):
    from PySide6.QtWidgets import QWidget
    from sli_ui_toolkit.ui.widgets import ThemedContainer, ThemedWidget

    events: list[str] = []

    class _SampleContainer(ThemedContainer, QWidget):
        def on_theme_derived(self) -> None:
            events.append("derived")

        def on_theme_children(self) -> None:
            events.append("children")

        def update(self, *args) -> None:  # type: ignore[override]
            events.append("super_update")
            super().update(*args)

    w = _SampleContainer()
    qtbot.addWidget(w)
    assert events == ["derived", "children", "super_update"]

    events.clear()
    w.on_theme_changed()
    assert events == ["derived", "children", "super_update"]

    # Existing ThemedWidget subclasses keep their plain update() contract.
    plain_events: list[str] = []

    class _PlainThemed(ThemedWidget, QWidget):
        def update(self, *args) -> None:  # type: ignore[override]
            plain_events.append("plain_update")
            super().update(*args)

    plain = _PlainThemed()
    qtbot.addWidget(plain)
    assert plain_events == ["plain_update"]


def test_refresh_theme_subtree_preorder_and_idempotent(qapp, qtbot):
    from PySide6.QtWidgets import QWidget
    from sli_ui_toolkit.ui.managers.theme_manager import refresh_theme_subtree
    from sli_ui_toolkit.ui.widgets import ThemedContainer, ThemedWidget

    order: list[str] = []

    class _Root(ThemedContainer, QWidget):
        def __init__(self, name: str, parent: QWidget | None = None) -> None:
            self._name = name
            super().__init__(parent)

        def on_theme_derived(self) -> None:
            order.append(f"{self._name}:derived")

        def on_theme_children(self) -> None:
            order.append(f"{self._name}:children")

    class _ThemedLeaf(ThemedWidget, QWidget):
        def __init__(self, name: str, parent: QWidget | None = None) -> None:
            self._name = name
            super().__init__(parent)

        def on_theme_changed(self) -> None:
            order.append(f"{self._name}:theme")
            super().on_theme_changed()

    class _PlainNode(QWidget):
        def __init__(self, name: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._name = name

        def update(self, *args) -> None:  # type: ignore[override]
            order.append(f"{self._name}:update")
            super().update(*args)

    root = _Root("root")
    qtbot.addWidget(root)
    branch_a = _Root("branch_a", root)
    leaf_a1 = _ThemedLeaf("leaf_a1", branch_a)
    leaf_a2 = _PlainNode("leaf_a2", branch_a)
    branch_b = _PlainNode("branch_b", root)
    leaf_b1 = _ThemedLeaf("leaf_b1", branch_b)
    _ = (leaf_a1, leaf_a2, leaf_b1)

    order.clear()
    refresh_theme_subtree(root)
    first_pass = list(order)
    assert first_pass == [
        "root:derived",
        "root:children",
        "branch_a:derived",
        "branch_a:children",
        "leaf_a1:theme",
        "leaf_a2:update",
        "branch_b:update",
        "leaf_b1:theme",
    ]

    order.clear()
    refresh_theme_subtree(root)
    assert order == first_pass
