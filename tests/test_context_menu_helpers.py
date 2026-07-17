from __future__ import annotations

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
