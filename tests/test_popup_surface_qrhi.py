"""Popup-surface / QRhiWidget coexistence warning.

A ``Qt.Popup`` whose QWidget parent is the host's top-level window breaks that
window's compositing on Wayland/XWayland with NVIDIA (BlinkTable
``inv-2026-10-06-ql-rhi-menu-first``; REAL-Video-Enhancer removed its only
``Qt.Popup`` in ``f471d71f``). The toolkit ships popup mode and two QRhiWidgets,
so the popup path logs one warning per process naming the widgets and the
in-window alternative. The menu still opens in the requested mode.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QRhiWidget, QWidget

from sli_ui_toolkit.config import configure_toolkit, reset_toolkit_config
from sli_ui_toolkit.ui import popup_surface
from sli_ui_toolkit.widgets import ContextMenu, ContextMenuAction

LOGGER_NAME = popup_surface.__name__


class _HostQrhiWidget(QRhiWidget):
    """Stand-in for a host's QRhi-backed surface (StripBand, GPU fill, ...)."""


@pytest.fixture(autouse=True)
def _isolate_warning_flag():
    # One-per-process is the contract; each test starts with a clean slate.
    popup_surface._qrhi_popup_warning_emitted = False
    reset_toolkit_config()
    yield
    popup_surface._qrhi_popup_warning_emitted = False
    reset_toolkit_config()


def _host(qtbot, *, with_qrhi: bool) -> QWidget:
    host = QWidget()
    host.resize(640, 480)
    qtbot.addWidget(host)
    if with_qrhi:
        qtbot.addWidget(_HostQrhiWidget(host))
    host.show()
    return host


def _popup_menu(host: QWidget) -> ContextMenu:
    return ContextMenu(
        host,
        entries=(ContextMenuAction("rename", "Rename"),),
        surface="popup",
    )


def _warnings(caplog) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno >= logging.WARNING
    ]


def test_popup_mode_warns_once_about_qrhi_widgets(qtbot, caplog):
    host = _host(qtbot, with_qrhi=True)
    menu = _popup_menu(host)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        menu.popup_at(host.mapToGlobal(QPoint(40, 40)))
        menu.hide()
        menu.popup_at(host.mapToGlobal(QPoint(80, 80)))
        menu.hide()

    records = _warnings(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert "popup" in message
    assert "_HostQrhiWidget" in message
    assert "Wayland" in message
    assert "in_window" in message


def test_popup_mode_uses_global_config_surface(qtbot, caplog):
    configure_toolkit(context_menu_surface="popup")
    host = _host(qtbot, with_qrhi=True)
    menu = ContextMenu(host, entries=(ContextMenuAction("rename", "Rename"),))
    assert menu.is_popup_surface()

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        menu.popup_at(host.mapToGlobal(QPoint(40, 40)))
        menu.hide()

    assert len(_warnings(caplog)) == 1


def test_in_window_mode_never_warns(qtbot, caplog):
    host = _host(qtbot, with_qrhi=True)
    menu = ContextMenu(
        host,
        entries=(ContextMenuAction("rename", "Rename"),),
        surface="in_window",
    )

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        menu.popup_at(host.mapToGlobal(QPoint(40, 40)))
        menu.hide()

    assert _warnings(caplog) == []


def test_popup_mode_without_qrhi_widgets_never_warns(qtbot, caplog):
    host = _host(qtbot, with_qrhi=False)
    menu = _popup_menu(host)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        menu.popup_at(host.mapToGlobal(QPoint(40, 40)))
        menu.hide()

    assert _warnings(caplog) == []
