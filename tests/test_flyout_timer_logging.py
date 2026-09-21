"""Flyout timer debug logging goes to the toolkit tree, not the host tree.

Regression test for task-toolkit-flyout-timer-hostlog-2026-09-18:
``DecisionJournal.note()`` previously emitted via
``logging.getLogger("ImproveImgSLI")`` — a host-tree logger that has no
handlers unless the host app configured it, so the record never reached the
host log file and misattributed toolkit diagnostics to the host. It now logs
on the module (``sli_ui_toolkit.*``) tree, which ``setup_logging()`` wires
handlers to.
"""

from __future__ import annotations

import logging
import os

import pytest

from sli_ui_toolkit.ui.managers import flyout_timer_service as fts
from sli_ui_toolkit.ui.managers.flyout_timer_service import DecisionJournal

_DEBUG_VARS = ("SLI_FLYOUT_DEBUG", "IMGSLI_FLYOUT_DEBUG", "FLYOUT_DEBUG")


@pytest.fixture()
def debug_on(monkeypatch):
    for var in _DEBUG_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SLI_FLYOUT_DEBUG", "1")
    yield
    # monkeypatch undoes the env change automatically


@pytest.fixture()
def debug_off(monkeypatch):
    for var in _DEBUG_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SLI_FLYOUT_DEBUG", "0")
    yield


def test_note_emits_on_toolkit_tree_not_host_tree(debug_on):
    journal = DecisionJournal("test-owner")
    toolkit_records: list[logging.LogRecord] = []
    host_records: list[logging.LogRecord] = []

    toolkit_logger = logging.getLogger("sli_ui_toolkit")
    host_logger = logging.getLogger("ImproveImgSLI")
    old_level = toolkit_logger.level
    old_propagate_t, old_propagate_h = toolkit_logger.propagate, host_logger.propagate
    toolkit_logger.setLevel(logging.DEBUG)
    toolkit_logger.propagate = False
    host_logger.propagate = False
    toolkit_logger.addHandler(_Sink(toolkit_records))
    host_logger.addHandler(_Sink(host_records))
    try:
        journal.note("schedule", "100ms test")
    finally:
        toolkit_logger.handlers.pop()
        host_logger.handlers.pop()
        toolkit_logger.setLevel(old_level)
        toolkit_logger.propagate = old_propagate_t
        host_logger.propagate = old_propagate_h

    assert len(toolkit_records) == 1
    assert toolkit_records[0].name == fts.__name__
    assert toolkit_records[0].levelno == logging.WARNING
    assert host_records == []


def test_note_silent_without_debug_flag(debug_off):
    journal = DecisionJournal("test-owner")
    records: list[logging.LogRecord] = []
    toolkit_logger = logging.getLogger("sli_ui_toolkit")
    old_level = toolkit_logger.level
    old_propagate = toolkit_logger.propagate
    toolkit_logger.setLevel(logging.DEBUG)
    toolkit_logger.propagate = False
    toolkit_logger.addHandler(_Sink(records))
    try:
        journal.note("schedule", "100ms test")
    finally:
        toolkit_logger.handlers.pop()
        toolkit_logger.setLevel(old_level)
        toolkit_logger.propagate = old_propagate
    # The ring buffer still records; only the logging emission is gated.
    assert journal.snapshot() != []
    assert records == []


def test_note_visible_without_setup_logging(debug_on, caplog):
    """Hosts that skip setup_logging(): record propagates to root handlers."""
    journal = DecisionJournal("test-owner")
    with caplog.at_level(logging.WARNING, logger="sli_ui_toolkit"):
        journal.note("timeout:hide", "cursor=1,2")
    assert any(
        r.name == fts.__name__ and "timeout:hide" in r.getMessage()
        for r in caplog.records
    )


class _Sink(logging.Handler):
    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self._records = records

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)
