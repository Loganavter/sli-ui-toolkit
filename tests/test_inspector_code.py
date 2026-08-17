"""Inspector tests — code section editor (snippet, gaps, gutter, edit/save)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.inspector.contract import (
    FieldKind,
    InspectField,
    InspectLayer,
    InspectRegion,
    WidgetInspection,
)
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Button, ButtonRegion, Label, Switch

from tests.inspector_helpers import _build_button_inspection, _open_probe, _page_labels, _spin_event_loop

def test_code_section_shows_live_config_snippet(qapp, monkeypatch, tmp_path_factory):
    from sli_ui_toolkit.ui.inspector.contract import InspectField

    win = InspectorWindow()
    pane, _source_file, _written = _open_probe(
        win,
        "import x\n\nclass Probe(QWidget):\n    pass\n",
        tmp_path_factory,
        monkeypatch,
        source_start=3,
        config=(InspectField(name="text", value="Probe"),),
    )
    text = pane._code_view.text()
    assert text.startswith("_LocalProbe(")  # the config snippet's synthetic call
    assert "text='Probe'" in text
    assert "class Probe(QWidget)" in text
    # gutter: config is 1-based, the class keeps its real file lines
    gutter = pane._code_view._canvas._line_number_map
    assert gutter is not None
    assert gutter[0] == "·"  # the synthetic config snippet is not a file line
    # the gap row shows the hidden block's last line — the class statement
    # right after it shows its real number, like a VS Code fold
    assert gutter[3] == "2"
    assert gutter[4] == "3"  # class statement = file line 3
    assert gutter[5] == "4"
    # the collapsed gap row is a plain ellipsis with a disclosure arrow
    assert "·····" in text
    assert pane._code_view._canvas._fold_lines == {3}
    assert pane._code_config_view is None


def test_code_section_gap_row_expands_on_click_and_toggle_btn(qapp, monkeypatch, tmp_path_factory):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    win = InspectorWindow()
    pane, _source_file, _written = _open_probe(
        win,
        "import x\n\n\nclass _LocalProbe(QWidget):\n    pass\n\n# tail\n",
        tmp_path_factory,
        monkeypatch,
        source_start=4,
    )
    assert "·····" in pane._code_view.text()
    page = pane.pages["Code"]
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in page.content_widget.findChildren(Button)
    }
    assert not buttons["Full"].isHidden()
    # click the gap row: no config snippet here, so the marker is display 0
    canvas = pane._code_view._canvas
    line_y = 8 + canvas._line_height // 2
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(60, line_y))
    text = pane._code_view.text()
    assert "import x" in text  # the "before" gap expanded inline
    assert "·····" not in text  # it was the only gap -> nothing left
    assert pane._code_view._canvas._fold_lines == set()
    # the toggle label flipped: re-query the buttons
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in page.content_widget.findChildren(Button)
    }
    assert "Compact" in buttons and not buttons["Compact"].isHidden()
    # Compact -> collapses everything back
    buttons["Compact"].click()
    assert "·····" in pane._code_view.text()
    assert pane._code_view._canvas._fold_lines == {0}
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in page.content_widget.findChildren(Button)
    }
    assert "Full" in buttons and not buttons["Full"].isHidden()


def test_code_section_toggle_preserves_edits(qapp, monkeypatch, tmp_path_factory):
    """Toggling Full/Compact must never discard user edits: the live
    buffer (snippet, class region, expanded gap sections) is re-seeded on
    every rebuild instead of the loaded state."""
    win = InspectorWindow()
    pane, _source_file, _written = _open_probe(
        win,
        "import x\n\n\nclass _LocalProbe(QWidget):\n    pass\n\n# tail\n",
        tmp_path_factory,
        monkeypatch,
        source_start=4,
        config=(InspectField(name="title", value="Hi"),),
    )
    page = pane.pages["Code"]

    def find_buttons():
        return {
            str(getattr(b, "_text", "")): b
            for b in page.content_widget.findChildren(Button)
        }

    buttons = find_buttons()
    buttons["Edit"].click()
    editor = pane._code_view.editor()
    # edit the config snippet (display line 0)
    editor._cursor = (0, 0)
    editor.insert_text("# snip\n")
    # edit the class region — locate the class line in the live buffer
    lines = pane._code_view.text().split("\n")
    cls = next(i for i, line in enumerate(lines) if line.startswith("class "))
    editor._cursor = (cls, 0)
    editor.insert_text("# edited\n")
    assert "# snip" in pane._code_view.text()
    assert "# edited" in pane._code_view.text()
    # Full (expand both gaps) -> Compact (collapse) -> Full again: the
    # edits must survive every rebuild
    find_buttons()["Full"].click()
    text = pane._code_view.text()
    assert "# snip" in text
    assert "# edited" in text
    assert "import x" in text  # before-gap expanded
    find_buttons()["Compact"].click()
    text = pane._code_view.text()
    assert "# snip" in text
    assert "# edited" in text
    assert "·····" in text  # collapsed again
    find_buttons()["Full"].click()
    text = pane._code_view.text()
    assert "# snip" in text
    assert "# edited" in text
    assert "import x" in text
    # edits inside an EXPANDED gap section survive a collapse cycle too
    # (the collapsed content is stashed, not dropped)
    editor = pane._code_view.editor()
    editor._cursor = (1, 0)  # "import x" is display line 0 of the expanded before-gap
    editor.insert_text("# before-edit\n")
    assert "# before-edit" in pane._code_view.text()
    find_buttons()["Compact"].click()
    find_buttons()["Full"].click()
    assert "# before-edit" in pane._code_view.text()
    # the edits are still real edits: Save/Apply stay enabled
    assert pane._code_section.snippet_dirty()
    assert pane._code_section.is_dirty()
    buttons = find_buttons()
    assert buttons["Save"].isEnabled()
    assert buttons["Apply"].isEnabled()


def test_code_section_gutter_matches_real_file_lines(qapp, monkeypatch, tmp_path_factory):
    from PySide6.QtWidgets import QWidget

    win = InspectorWindow()
    pane, _source_file, _written = _open_probe(
        win,
        "import x\n\n\nclass _LocalProbe(QWidget):\n    pass\n",
        tmp_path_factory,
        monkeypatch,
        source_start=4,
    )
    # the class-source gutter starts at the class's line in the actual file
    gutter = pane._code_view._canvas._line_number_map
    assert gutter is not None
    assert gutter[1] == "4"  # marker row sits at display 1, class at 2
    assert gutter[2] == "5"
    assert pane._code_view._canvas._gutter_width() > 0
    assert pane._code_config_view is None


def test_code_section_edit_revert_save(qapp, monkeypatch, tmp_path_factory):
    from PySide6.QtWidgets import QWidget

    win = InspectorWindow()
    pane, source_file, written = _open_probe(
        win,
        "import x\n\nclass _LocalProbe:\n    pass\n",
        tmp_path_factory,
        monkeypatch,
        source_start=3,
    )
    page = pane.pages["Code"]
    buttons = {
        str(getattr(b, "_text", "")): b
        for b in page.content_widget.findChildren(Button)
    }
    assert "Edit" in buttons and "Revert" in buttons and "Save" in buttons
    assert buttons["Save"].isEnabled() is False
    # read mode: not editing
    assert pane._code_view.is_editing() is False
    buttons["Edit"].click()
    assert pane._code_view.is_editing() is True
    editor = pane._code_view.editor()
    # the buffer starts with the collapsed gap row; place the caret at the
    # start of the class region so the edit lands on saveable content
    editor._cursor = (1, 0)
    editor.insert_text("# edited\n")
    assert buttons["Save"].isEnabled() is True
    buttons["Revert"].click()
    assert pane._code_view.is_editing() is False
    assert "class _LocalProbe" in pane._code_view.text()
    assert "# edited" not in pane._code_view.text()
    assert buttons["Save"].isEnabled() is False
    buttons["Edit"].click()
    editor = pane._code_view.editor()
    editor._cursor = (1, 0)
    editor.insert_text("# edited\n")
    buttons["Save"].click()
    assert written and written[0][0] == str(source_file)
    # save reconstructs the whole file: surrounding code preserved, the
    # config snippet and markers never written to disk
    saved = written[0][1]
    assert "import x" in saved
    assert "# edited" in saved
    assert "class _LocalProbe" in saved
    assert "·····" not in saved
    assert buttons["Save"].isEnabled() is False


def test_source_row_opens_file_via_system_editor(qapp, monkeypatch):
    from PySide6.QtWidgets import QWidget

    class _LocalProbe(QWidget):
        def __init__(self):
            super().__init__()

    opened = []

    def fake_open(url):
        opened.append(url.toLocalFile())
        return True

    monkeypatch.setattr(
        "PySide6.QtGui.QDesktopServices.openUrl",
        staticmethod(fake_open),
    )
    win = InspectorWindow()
    win.set_inspection(
        WidgetInspection(family="QWidget"), widget=_LocalProbe()
    )
    page = win.active_pane().pages["Object"]
    buttons = page.content_widget.findChildren(Button)

    def _button_text(b):
        text = str(getattr(b, "_text", "") or "")
        for row in getattr(b, "_rows", ()) or ():
            text += str(getattr(row, "text", "") or "")
        return text

    source_button = next(b for b in buttons if ":" in _button_text(b))
    source_button.click()
    assert opened and opened[0].endswith(".py")


