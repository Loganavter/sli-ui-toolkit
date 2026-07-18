from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.popup_surface import bind_popup_transient_parent
from sli_ui_toolkit.ui.widgets.composite.context_menu import (
    ContextMenuAction,
    entries_from_callbacks,
    entries_from_labeled_data,
)


def test_entries_from_labeled_data_marks_current():
    entries = entries_from_labeled_data(
        [("RGB", "rgb"), ("SSIM", "ssim")],
        current="ssim",
    )
    assert len(entries) == 2
    assert entries[0].text == "RGB"
    assert entries[0].data == "rgb"
    assert entries[0].checkable is True
    assert entries[0].checked is False
    assert entries[1].checked is True


def test_entries_from_callbacks_builds_actions():
    entries = entries_from_callbacks([("Save", "save"), ("Quit", "quit")])
    assert len(entries) == 2
    assert isinstance(entries[0], ContextMenuAction)
    assert entries[0].action_id == "action.0"
    assert entries[1].data == "quit"


def test_bind_popup_skips_transient_on_windows_translucent_host(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    host = QWidget()
    host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)

    popup = QWidget(host)
    popup.setWindowFlags(
        Qt.WindowType.Popup
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.NoDropShadowWindowHint
    )
    popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    qtbot.addWidget(popup)

    bind_popup_transient_parent(popup, host)
    handle = popup.windowHandle()
    # Must not force a native handle / transient link against translucent CSD.
    assert handle is None or handle.transientParent() is None
