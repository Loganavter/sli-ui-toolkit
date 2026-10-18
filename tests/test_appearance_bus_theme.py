"""P3 appearance bus — theme folded into the one coalesced channel.

``ThemeManager`` emits ``{"theme"}`` into ``UiMetrics`` alongside the font
and scale producers; its ``theme_changed`` signal stays a thin alias so
existing subscribers keep working unchanged.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import UiFont
from sli_ui_toolkit.ui.managers.ui_metrics import connect_ui_metrics


@pytest.fixture(autouse=True)
def _light_theme(qapp):
    """Every test starts and ends on a known theme, in a known order."""
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    qapp.processEvents()
    yield tm
    tm.set_theme("light", qapp, await_ripples=False)
    qapp.processEvents()


def test_theme_change_reaches_bus_subscriber_with_theme_axis(qapp, _light_theme):
    widget = QWidget()
    payloads: list[frozenset[str]] = []
    connect_ui_metrics(widget, lambda axes: payloads.append(axes))
    _light_theme.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    assert payloads == [frozenset({"theme"})]


def test_theme_changed_alias_still_fires(qapp, _light_theme):
    """``theme_changed`` stays a thin alias: existing subscribers keep
    working, synchronously, with no payload.
    """
    calls: list[int] = []

    def _on_theme_changed() -> None:
        calls.append(1)

    _light_theme.theme_changed.connect(_on_theme_changed)
    try:
        _light_theme.set_theme("dark", qapp, await_ripples=False)
        assert calls == [1], "theme_changed did not fire on set_theme"
    finally:
        _light_theme.theme_changed.disconnect(_on_theme_changed)


def test_theme_and_font_in_one_turn_coalesce_to_one_emit(qapp, _light_theme):
    """One logical change (theme + font together) reaches the bus as ONE
    emission carrying the union of the axes.
    """
    widget = QWidget()
    payloads: list[frozenset[str]] = []
    connect_ui_metrics(widget, lambda axes: payloads.append(axes))
    _light_theme.set_theme("dark", qapp, await_ripples=False)
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert payloads == [frozenset({"theme", "font"})]


def test_theme_axis_does_not_wake_a_scale_only_subscriber(qapp, _light_theme):
    """Granularity across axes: a ``{"scale"}`` subscriber is not called for
    a theme change.
    """
    widget = QWidget()
    scale_calls: list[frozenset[str]] = []
    connect_ui_metrics(
        widget, lambda axes: scale_calls.append(axes), axes=frozenset({"scale"})
    )
    _light_theme.set_theme("dark", qapp, await_ripples=False)
    qapp.processEvents()
    assert scale_calls == []
