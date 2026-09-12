"""Negative-path tests: invalid theme/factor/unregister."""
from __future__ import annotations
import pytest
from PySide6.QtGui import QColor
from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.services.dragdrop_service import ToolkitDragDropService
from sli_ui_toolkit.ui.widget_descriptor import WidgetRegistry
def test_invalid_theme_falls_back_to_light(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    for bad in ["invalid", "", "DARK", "Light", "unknown_theme"]:
        tm.set_theme(bad, qapp, await_ripples=False)
        tm._flush_pending_theme()  # type: ignore[attr-defined]
        assert tm.get_current_theme() == "light"
    tm.set_theme("dark", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    assert tm.get_current_theme() == "dark"
@pytest.mark.parametrize("bad_factor", ["bad", None, object(), float("nan"), float("inf"), float("-inf")])
def test_uiscale_garbage_factors_are_ignored(bad_factor, qapp):
    scale = UiScale.get_instance()
    scale.set_factor(1.0)
    before = scale.factor()
    scale.set_factor(bad_factor)  # type: ignore[arg-type]
    assert scale.factor() == before
@pytest.mark.parametrize("clamped_input,expected", [(0.1, 0.5), (10.0, 2.5), (0.5, 0.5), (2.5, 2.5)])
def test_uiscale_clamped_range(clamped_input, expected):
    scale = UiScale.get_instance()
    scale.set_factor(1.0)
    scale.set_factor(clamped_input)
    assert scale.factor() == expected
    scale.set_factor(1.0)
def test_uiscale_no_emit_on_noop(qapp):
    scale = UiScale.get_instance()
    scale.set_factor(1.0)
    calls: list[float] = []
    def _on_change(v: float) -> None:
        calls.append(v)
    scale.scale_changed.connect(_on_change)
    try:
        scale.set_factor(1.0)
        assert calls == []
        scale.set_factor(2.0)
        assert calls == [2.0]
        scale.set_factor(2.0)
        assert calls == [2.0]
    finally:
        try:
            scale.scale_changed.disconnect(_on_change)
        except Exception:
            pass
        scale.set_factor(1.0)
def test_unregister_unknown_family_is_safe():
    reg = WidgetRegistry.get_instance()
    reg.unregister("__nonexistent__")
    assert reg.get("__nonexistent__") is None
def test_unregister_unknown_drop_target_is_safe(qapp):
    svc = ToolkitDragDropService()
    from PySide6.QtWidgets import QWidget
    w = QWidget()
    svc.unregister_drop_target(w)
    svc.register_drop_target(w)
    svc.unregister_drop_target(w)
    svc.unregister_drop_target(w)
def test_get_color_missing_token_returns_fallback_but_does_not_crash(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    bad = tm.get_color("__does_not_exist__")
    assert isinstance(bad, QColor) and bad.isValid()
    assert tm.try_get_color("__does_not_exist__") is None
def test_scaled_px_min_one():
    scale = UiScale.get_instance()
    scale.set_factor(1.0)
    assert scale.scaled_px(0) == 1
    assert scale.scaled_px(0.1) == 1
    scale.set_factor(0.5)
    assert scale.scaled_px(1) == 1
    scale.set_factor(1.0)
