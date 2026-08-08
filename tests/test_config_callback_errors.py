from __future__ import annotations

import logging

import pytest

from sli_ui_toolkit import config


@pytest.fixture(autouse=True)
def _reset_config_globals():
    """configure_toolkit-set globals are process-wide; isolate each test."""
    saved = (
        config._overlay_resolver,
        config._rating_gesture_factory,
        config._dragdrop_service_getter,
    )
    yield
    (
        config._overlay_resolver,
        config._rating_gesture_factory,
        config._dragdrop_service_getter,
    ) = saved


def test_resolve_overlay_layer_logs_and_falls_back_on_error(caplog):
    def boom(widget):
        raise RuntimeError("bad overlay resolver")

    config.configure_toolkit(overlay_resolver=boom)

    with caplog.at_level(logging.WARNING, logger="sli_ui_toolkit.config"):
        result = config.resolve_overlay_layer(None)

    assert result is None
    assert any(
        "overlay_resolver raised" in record.message for record in caplog.records
    )
    assert caplog.records[-1].exc_info is not None


def test_create_rating_gesture_logs_and_falls_back_on_error(caplog):
    def boom(**kwargs):
        raise RuntimeError("bad rating gesture factory")

    config.configure_toolkit(rating_gesture_factory=boom)

    with caplog.at_level(logging.WARNING, logger="sli_ui_toolkit.config"):
        result = config.create_rating_gesture()

    assert result is None
    assert any(
        "rating_gesture_factory raised" in record.message for record in caplog.records
    )
    assert caplog.records[-1].exc_info is not None


def test_get_dragdrop_service_logs_and_falls_back_on_error(caplog):
    def boom():
        raise RuntimeError("bad dragdrop service getter")

    config.configure_toolkit(dragdrop_service_getter=boom)

    with caplog.at_level(logging.WARNING, logger="sli_ui_toolkit.config"):
        result = config.get_dragdrop_service()

    assert result is not None  # falls back to ToolkitDragDropService.get_instance()
    assert any(
        "dragdrop_service_getter raised" in record.message for record in caplog.records
    )
    assert caplog.records[-1].exc_info is not None


def test_resolve_overlay_layer_no_log_when_resolver_succeeds(caplog):
    sentinel = object()
    config.configure_toolkit(overlay_resolver=lambda widget: sentinel)

    with caplog.at_level(logging.WARNING, logger="sli_ui_toolkit.config"):
        result = config.resolve_overlay_layer(None)

    assert result is sentinel
    assert caplog.records == []
